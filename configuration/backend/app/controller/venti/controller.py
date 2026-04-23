from .decision import Decision
from .context import VentiContext
from .efficiency.drying_efficiency_engine import DryingEfficiencyEngine
from .efficiency.drying_decision_engine import DryingDecisionEngine

from app.services.control_data import build_control_data
from app.services.venti_service import venti_cmd

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
    ctx.min_efficiency_threshold = state_manager.get_adaptive_threshold(
        ctx.base_min_efficiency_threshold
    )

    decision = decision_engine.decide(ctx, metrics)
    updated_threshold = state_manager.update_adaptive_threshold(
        metrics["efficiency"],
        ctx,
        has_history=metrics["has_history"],
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

    # 2. BUILD CONTEXT
    data = build_control_data()
    ctx = VentiContext(data)

    # 3. RULE ENGINE
    decision = evaluate(ctx)

    mode_changed = previous_mode != ctx.mode
    state_changed = previous_state != decision.reason
    threshold_changed = (
        (state_manager.last_details or {}).get("adaptive_threshold")
        != decision.details.get("adaptive_threshold")
    )

    # 4. EXECUTE CONTROL
    venti_cmd(decision.command)

    # 5. PERSIST STATE (ONLY STATE MANAGER)
    if mode_changed or state_changed or threshold_changed:
        state_manager.persist(
            state=decision.reason,
            command=decision.command,
            mode=ctx.mode,
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

        if previous_mode == "auto" and ctx.mode == "manual":
            logger.info("🛑 AUTO disabled -> sending summary")

            event_bus.publish(Event(
                type=EventType.DAILY_SUMMARY,
                data={"message": build_auto_summary(ctx)}
            ))

        event_bus.publish(Event(
            type=EventType.MODE_CHANGE,
            data={
                "old_mode": previous_mode,
                "new_mode": ctx.mode,
                "ctx": ctx,
                "decision": decision
            }
        ))

        previous_mode = ctx.mode

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

        if event[0] == "STATE_CHANGE" and event[2] == "MANUAL_MODE":
            event_bus.publish(Event(
                type=EventType.TRANSITION,
                data={
                    "name": "AUTO_SUMMARY",
                    "ctx": ctx
                }
            ))

    previous_state = decision.reason

    # 9. SYSTEM ALERTS
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
