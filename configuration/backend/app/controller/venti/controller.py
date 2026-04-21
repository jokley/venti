from .rule_engine import rules
from .decision import Decision
from .context import VentiContext

from app.services.control_data import build_control_data
from app.services.venti_service import venti_cmd

from app.notifications.transitions import TransitionDetector
from app.notifications.alerts.battery_engine import check_battery_alerts
from app.notifications.alerts.rssi_engine import check_rssi_alerts
from app.notifications.state_registry import alert_state
from app.notifications.summary.daily_summary import build_daily_summary, should_send_summary
from app.notifications.summary.auto_summary import build_auto_summary

from app.events.event_bus import event_bus, EventType, Event
from app.utils.logger import logger

from .rules import *

def evaluate(ctx):
    trace = []
    for priority, rule_func in rules:
        result = rule_func(ctx)
        trace.append({
            "rule": rule_func.__name__,
            "priority": priority,
            "matched": result is not None,
            "decision": result.command if result else None,
            "reason": result.reason if result else None
        })
        if result:
            result.details["trace"] = trace
            return result

    return Decision("off", "NO_CONDITION", {"trace": trace})

detector = TransitionDetector()
previous_mode = None
previous_state = None

def venti_control():
    global previous_mode, previous_state
    
    # 1. BUILD CONTEXT
    data = build_control_data()
    ctx = VentiContext(data)

    # 2. RULE ENGINE
    decision = evaluate(ctx)

    # 3. EXECUTE CONTROL
    venti_cmd(decision.command)

    # 4. PUBLISH DECISION LOG EVENT
    event_bus.publish(Event(
        type=EventType.DECISION_LOG,
        data={"decision": decision, "ctx": ctx}
    ))

    # 5. DETECT MODE CHANGES
    if previous_mode != ctx.mode:
        # AUTO MODE DISABLED -> send summary
        if previous_mode == "auto" and ctx.mode == "manual":
            logger.info("🛑 AUTO mode disabled -> sending summary")
            msg = build_auto_summary(ctx)
            event_bus.publish(Event(
                type=EventType.DAILY_SUMMARY,
                data={"message": msg}
            ))
        
        event_bus.publish(Event(
            type=EventType.MODE_CHANGE,
            data={"old_mode": previous_mode, "new_mode": ctx.mode, "ctx": ctx, "decision": decision}
        ))
        previous_mode = ctx.mode

    # 6. PUBLISH TRANSITION EVENTS
    events = detector.detect(decision, data)
    
    for event in events:
        event_bus.publish(Event(
            type=EventType.TRANSITION,
            data={"name": event[0], "event": event, "ctx": ctx}
        ))
        
        if event[0] == "STATE_CHANGE" and event[2] == "AUTO_DISABLED":
            event_bus.publish(Event(
                type=EventType.TRANSITION,
                data={"name": "AUTO_SUMMARY", "ctx": ctx}
            ))

    # 7. SYSTEM ALERTS
    battery_events = check_battery_alerts(ctx, alert_state.battery)
    rssi_events = check_rssi_alerts(ctx, alert_state.rssi)

    for alert in battery_events + rssi_events:
        event_bus.publish(Event(
            type=EventType.SYSTEM_ALERT,
            data=alert
        ))

    # 8. DAILY SUMMARY
    if should_send_summary(ctx, alert_state.summary):
        msg = build_daily_summary(ctx)
        event_bus.publish(Event(
            type=EventType.DAILY_SUMMARY,
            data={"message": msg}
        ))
