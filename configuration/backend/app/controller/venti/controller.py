from .decision import Decision
from .context import VentiContext
from .efficiency.drying_efficiency_engine import DryingEfficiencyEngine
from .efficiency.drying_decision_engine import DryingDecisionEngine

from app.services.control_data import build_control_data
from app.services.venti_service import venti_cmd, venti_auto

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


def evaluate(ctx):
    metrics = efficiency_engine.compute(ctx)

    if ctx.self_learning_enabled:
        ctx.min_efficiency_threshold = state_manager.get_adaptive_threshold(
            ctx.base_min_efficiency_threshold
        )
    else:
        ctx.min_efficiency_threshold = ctx.base_min_efficiency_threshold

    decision = decision_engine.decide(ctx, metrics)

    if ctx.self_learning_enabled and decision.reason == "INEFFICIENT_DRYING":
        state_manager.remember_bad_drying(ctx, metrics, decision.details)

    if ctx.self_learning_enabled and decision.reason == "DRYING_ACTIVE":
        state_manager.clear_bad_drying()

    if ctx.self_learning_enabled:
        updated_threshold = state_manager.update_adaptive_threshold(
            metrics["efficiency"],
            ctx,
            has_history=metrics["has_history"],
        )
    else:
        updated_threshold = ctx.min_efficiency_threshold

    auto_disable_triggered = (
        ctx.mode == "auto"
        and decision.command == "off"
        and ctx.remainingTimeStock > ctx.stock
        and ctx.remainingTimeInterval >= 7200
        and ctx.tsSoll is not None
        and ctx.tsMin is not None
        and (ctx.tsSoll - ctx.tsMin) <= 0.5
    )

    if auto_disable_triggered:
        venti_auto("off", ctx.tsSoll, "0")
        decision = Decision(
            "off",
            "MANUAL_MODE",
            {
                "runtime": ctx.remainingTimeInterval,
                "tsDiff": ctx.tsSoll - ctx.tsMin,
                "reason": "auto_disabled",
                "mode_override": "off",
            },
        )

    decision.details.setdefault("efficiency", metrics["efficiency"])
    decision.details.setdefault("adaptive_threshold", updated_threshold)
    decision.details.setdefault("sdef_change_2h", metrics["sdef_gain"])
    decision.details.setdefault("ts_change_2h", metrics["ts_gain"])
    decision.details.setdefault("window_hours", metrics["window_hours"])
    return decision


# =========================
# 🔁 RUNTIME STATE
# =========================
detector = TransitionDetector()
previous_mode = None
previous_state = None


def restore_controller_runtime_state():
    global previous_mode, previous_state

    if (
        previous_mode is not None
        or previous_state is not None
        or detector.state_start_ts is not None
    ):
        return

    restored = state_manager.restore()

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
        return

    # 3. BUILD CONTEXT
    data = build_control_data()
    ctx = VentiContext(data)
    ctx.venti_auto_lockout_remaining = (
        state_manager.get_venti_auto_lockout_remaining(ctx.now)
    )

    # 4. DECISION ENGINE
    decision = evaluate(ctx)
    effective_mode = decision.details.get("mode_override", ctx.mode)

    if (
        ctx.mode == "auto"
        and previous_state in ("DRYING_ACTIVE", "INTERVAL_ACTIVE")
        and decision.reason in ("AUTO_IDLE", "INEFFICIENT_DRYING")
        and (decision.details or {}).get("reason") != "auto_lockout"
    ):
        state_manager.start_venti_auto_lockout(ctx, decision)
        decision.details["lockout_remaining"] = (
            state_manager.get_venti_auto_lockout_remaining(ctx.now)
        )

    mode_changed = previous_mode != effective_mode
    state_changed = previous_state != decision.reason
    threshold_changed = (
        (state_manager.last_details or {}).get("adaptive_threshold")
        != decision.details.get("adaptive_threshold")
    )

    # 5. EXECUTE CONTROL
    venti_cmd(decision.command)

    # Persist only on relevant state changes to avoid noisy writes.
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
