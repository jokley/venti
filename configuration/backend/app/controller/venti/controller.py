from .context import VentiContext
from .efficiency.drying_efficiency_engine import DryingEfficiencyEngine
from .efficiency.drying_decision_engine import DryingDecisionEngine
from .interval_scheduler import get_interval_scheduler_delay
from datetime import datetime, timedelta

from app.services.control_data import build_control_data
from app.services.venti_service import venti_cmd, venti_auto
from app.extensions.extensions import scheduler

from .control.state_manager import state_manager

from app.notifications.transitions import TransitionDetector
from app.notifications.alerts.battery_engine import check_battery_alerts
from app.notifications.alerts.rssi_engine import check_rssi_alerts
from app.notifications.state_registry import alert_state

from app.notifications.summary.daily_summary import (
    build_daily_summary,
    should_send_summary
)
from app.notifications.summary.auto_summary import build_auto_summary

from app.events.event_bus import event_bus, EventType, Event
from app.utils.logger import logger

efficiency_engine = DryingEfficiencyEngine()
decision_engine = DryingDecisionEngine()


def evaluate(ctx, previous_state=None):
    # Die Effizienz ist nur ein Eingangssignal. Es gibt kein Self-Learning mehr:
    # die Schwelle bleibt der konfigurierte Basiswert und wird nicht adaptiv
    # nachgefuehrt.
    metrics = efficiency_engine.compute(ctx)
    ctx.min_efficiency_threshold = ctx.base_min_efficiency_threshold

    decision = decision_engine.decide(ctx, metrics, previous_state=previous_state)

    decision.details.setdefault("efficiency", metrics["efficiency"])
    decision.details.setdefault("min_efficiency_threshold", ctx.min_efficiency_threshold)
    decision.details.setdefault("sdef_change_2h", metrics["sdef_gain"])
    decision.details.setdefault("ts_change_2h", metrics["ts_gain"])
    decision.details.setdefault("window_hours", metrics["window_hours"])
    return decision


def sync_interval_end_scheduler(decision):
    delay_seconds = get_interval_scheduler_delay(decision)

    if delay_seconds is None:
        return False

    next_run_time = datetime.now(scheduler.timezone) + timedelta(seconds=delay_seconds)

    try:
        scheduler.modify_job(
            "venti_control",
            next_run_time=next_run_time,
        )
        decision.details["scheduler_next_delay"] = delay_seconds
        logger.debug(
            "venti_control auf Intervall-Ende synchronisiert – nächster Lauf: %s",
            next_run_time,
        )
        return True
    except Exception:
        logger.warning("venti_control konnte nicht auf Intervall-Ende synchronisiert werden")
        return False


# =========================
# 🔁 RUNTIME STATE
# =========================
detector = TransitionDetector()
previous_mode = None
previous_state = None


def restore_controller_runtime_state():
    global previous_mode, previous_state

    # Restore laeuft nur einmal nach Prozessstart. Danach ist der
    # StateManager die In-Memory-Quelle fuer Persistenz- und Transition-Vergleiche.
    if (
        previous_mode is not None
        or previous_state is not None
        or detector.state_start_ts is not None
    ):
        return

    try:
        restored = state_manager.restore()
    except Exception:
        # Influx may still be starting or temporarily unavailable. Keep the
        # backend alive so /healthz can answer and retry restoring next cycle.
        logger.exception("Unable to restore controller state from InfluxDB; continuing without persisted state.")
        return

    if not restored:
        return

    previous_mode = restored.get("mode")
    previous_state = restored.get("state")

    detector.restore(
        command=restored.get("command"),
        reason=restored.get("state"),
        details=restored.get("details"),
        state_start_ts=restored.get("started_at"),
    )

    logger.info(
        "Restored controller state: mode=%s state=%s",
        previous_mode,
        previous_state,
    )


# =========================
# 🚀 MAIN CONTROL LOOP
# =========================
def venti_control():
    global previous_mode, previous_state

    # 1. RESTORE STATE
    restore_controller_runtime_state()

    # 2. HEIZUNG VERRIEGELUNG
    # heizung_control() läuft als eigenständiger Job und setzt den Lock.
    # Solange Heizung oder Nachlauf aktiv übernimmt heizung_control()
    # den Lüfter – venti_control() bleibt komplett draußen.
    if state_manager.heizung_lock:
        logger.info("venti_control gesperrt – Heizung Lock aktiv")
        return None

    # 3. BUILD CONTEXT
    # build_control_data() sammelt Influx-/Parameter-/Hardwarewerte; VentiContext
    # macht daraus die einheitliche Entscheidungsgrundlage fuer diesen Zyklus.
    data = build_control_data()
    ctx = VentiContext(data)
    ctx.venti_drying_delay_remaining = (
        state_manager.get_venti_drying_delay_remaining(ctx.now)
    )

    # 4. DECISION ENGINE
    decision = evaluate(ctx, previous_state=previous_state)

    if ctx.mode == "auto" and decision.details.get("mode_override") == "off":
        venti_auto("off", ctx.tsSoll, "0")

    effective_mode = decision.details.get("mode_override", ctx.mode)

    mode_changed = previous_mode != effective_mode
    state_changed = previous_state != decision.reason
    previous_details = state_manager.last_details or {}
    previous_threshold = previous_details.get("min_efficiency_threshold")
    if previous_threshold is None:
        # Backward compatibility for states persisted before the Self-Learning
        # cleanup, where the static threshold was stored under this old name.
        previous_threshold = previous_details.get("adaptive_threshold")
    threshold_changed = previous_threshold != decision.details.get("min_efficiency_threshold")

    # 5. EXECUTE CONTROL
    venti_cmd(decision.command)

    # Persistenz ist die State-Timeline fuer Frontend/Grafana. Wiederholte
    # gleiche Entscheidungen werden nicht erneut geschrieben, ausser die
    # adaptive Schwelle hat sich veraendert.
    if mode_changed or state_changed or threshold_changed:
        state_manager.persist(
            state=decision.reason,
            command=decision.command,
            mode=effective_mode,
            details=decision.details,
            ctx=ctx
        )

    # 6. DECISION EVENT
    event_bus.publish(Event(
        type=EventType.DECISION_LOG,
        data={"decision": decision, "ctx": ctx}
    ))

    # Bei Intervall-Lueftung wird der naechste Lauf ans berechnete Ende gelegt,
    # damit 4-Minuten-Intervalle nicht bis zum normalen Basistakt ueberziehen.
    sync_interval_end_scheduler(decision)

    # 7. MODE CHANGE HANDLING
    if mode_changed:

        if previous_mode == "auto" and effective_mode != "auto":
            logger.info("🛑 AUTO disabled -> sending summary")

            event_bus.publish(Event(
                type=EventType.DAILY_SUMMARY,
                data={"message": build_auto_summary(ctx)}
            ))

        event_bus.publish(Event(
            type=EventType.MODE_CHANGE,
            data={
                "old_mode": previous_mode,
                "new_mode": effective_mode,
                "ctx": ctx,
                "decision": decision
            }
        ))

        previous_mode = effective_mode

    # 8. TRANSITIONS
    events = detector.detect(decision, data)

    for event in events:
        event_bus.publish(Event(
            type=EventType.TRANSITION,
            data={
                "name": event[0],
                "event": event,
                "ctx": ctx
            }
        ))

    previous_state = decision.reason

    # 9. ALERTS
    for alert in (
        check_battery_alerts(ctx, alert_state.battery)
        + check_rssi_alerts(ctx, alert_state.rssi)
    ):
        event_bus.publish(Event(
            type=EventType.SYSTEM_ALERT,
            data=alert
        ))

    # 10. DAILY SUMMARY
    if should_send_summary(ctx, alert_state.summary):
        event_bus.publish(Event(
            type=EventType.DAILY_SUMMARY,
            data={
                "message": build_daily_summary(ctx)
            }
        ))

    return decision
