from .event_bus import event_bus, EventType, Event
from app.notifications.event_message_builder import (
    build_event_message,
    pretty_reason
)
from app.notifications.notifier import send_notification
from app.notifications.alerts.alert_message_builder import build_system_alert_message
from app.utils.logger import logger

INFO_DECISION_REASONS = {
    "OVERHEAT",
    "STOCK_BUILDING",
    "DRYING_ACTIVE",
    "INTERVAL_ACTIVE",
    "INEFFICIENT_DRYING",
    "MANUAL_MODE",
    "VENTI_MANUAL_ON",
    "VENTI_MANUAL_OFF",
    "HEIZUNG_ACTIVE",
    "HEIZUNG_MANUAL_ON",
    "HEIZUNG_NACHLAUF",
}

_last_decision_log_signature = None


def handle_transition_event(event: Event):
    """Handle state transitions"""
    try:
        event_data = event.data
        # logger.debug(f"Transition event data: {event_data}")
        
        # Extract the actual event tuple from event_data
        actual_event = event_data.get("event")
        
        msg = build_event_message(actual_event)
        # logger.debug(f"Built message: {msg}")
        
        if msg:
            send_notification(
                title=event_data.get("name", "STATE_CHANGE"),
                message=msg
            )
    except Exception as e:
        logger.error(f"Error in handle_transition_event: {e}", exc_info=True)

def handle_system_alert(event: Event):
    """Handle system alerts (battery, rssi)"""
    try:
        alert = event.data
        logger.debug(f"System alert data: {alert}")
        
        msg = build_system_alert_message(alert)
        # logger.debug(f"Built alert message: {msg}")
        
        send_notification(
            title=alert[0],
            message=msg
        )
    except Exception as e:
        logger.error(f"Error in handle_system_alert: {e}", exc_info=True)

def handle_daily_summary(event: Event):
    """Handle daily summary"""
    msg = event.data["message"]
    
    send_notification(
        title="Tagesübersicht",
        message=msg
    )

def handle_decision_log(event: Event):
    """Handle decision logging for debugging (not user notifications)"""
    global _last_decision_log_signature

    decision = event.data["decision"]
    ctx = event.data["ctx"]
    details = decision.details or {}
    signature = (ctx.mode, decision.command, decision.reason)
    state_changed = signature != _last_decision_log_signature
    log_at_info = (
        state_changed
        and (
            decision.reason in INFO_DECISION_REASONS
            or decision.reason == "AUTO_IDLE"
        )
    )
    log = logger.info if log_at_info else logger.debug

    _last_decision_log_signature = signature

    log("****************************************")
    log(f"Mode: {ctx.mode}")
    log(f"Command: {decision.command}")
    log(f"Reason: {decision.reason}")

    if decision.reason == "OVERHEAT":
        log("Überhitzungsschutz aktiv!")
        log(f"Temperatur: {details.get('tempMax')} | Schwelle: {details.get('threshold')}")
        log(f"Differenz: {details.get('diff')}")

    elif decision.reason == "STOCK_BUILDING":
        log("Stockaufbau")
        log(f"Restzeit aktuell: {details.get('remaining')}")
        log(f"Stock-Ziel: {details.get('stock')}")
        log(f"Restzeit bis Ende: {details.get('restzeit')}")

    # --- DRYING_ACTIVE (Lüfter ein) ---
    elif decision.reason == "DRYING_ACTIVE":
        log("Lüfter ein")
        log(f"SDef min: {details.get('sDefMin')} | SDef out: {details.get('sDefOut')}")
        log(f"SDef diff: {details.get('sDefDiff')}")
        log(f"TS ist: {details.get('tsMin')} | TS soll: {details.get('tsSoll')}")
        log(f"TS diff: {details.get('tsDiff')}")
        log(f"Effizienz: {details.get('efficiency')} | Limit: {details.get('adaptive_threshold')}")

    # --- INTERVAL_ACTIVE ---
    elif decision.reason == "INTERVAL_ACTIVE":
        log("Intervall Belüftung")
        log(f"Hum max: {details.get('humMax')} | Schwelle: {details.get('threshold')}")
        log(f"Intervall Zeit: {details.get('interval_time')}")
        log(f"Dauer aus: {details.get('remaining_off_time')}")
        log(f"Restzeit: {details.get('remaining')}")

    # --- INEFFICIENT_DRYING ---
    elif decision.reason == "INEFFICIENT_DRYING":
        log("Ineffiziente Trocknung erkannt")
        log(f"SDEF Change 2h: {details.get('sdef_change_2h')}")
        log(f"TS Change 2h: {details.get('ts_change_2h')}")
        log(f"Effizienz: {details.get('efficiency')} | Limit: {details.get('adaptive_threshold')}")

    # --- MANUAL STATES ---
    elif decision.reason in ("MANUAL_MODE", "VENTI_MANUAL_ON", "VENTI_MANUAL_OFF"):
        log("Automatik deaktiviert")
        log(f"State: {decision.reason}")
        log(f"Laufzeit Intervall: {details.get('runtime')}")
        log(f"TS diff: {details.get('tsDiff')}")

    # --- AUTO_IDLE ---
    elif decision.reason == "AUTO_IDLE":
        log("Automatik im Leerlauf")
        log(f"Reason: {details.get('reason')}")
        log(
            f"sDefOut: {details.get('sDefOut')} | "
            f"EIN ab sdef_on: {details.get('sdef_ein_schwelle')} | "
            f"EIN ab MinThreshold: {details.get('sdefMinThreshold_ein')}"
        )
        log(f"tsDiff: {details.get('tsDiff')}")
        logger.debug(f"Effizienz: {details.get('efficiency')} | Limit: {details.get('adaptive_threshold')}")
        logger.debug(f"Intervall Feuchte: {details.get('humMax')} / {details.get('intervall_on')}")
        logger.debug(f"Dauer aus: {details.get('remainingTimeIntervalOn')}")
        logger.debug(f"Intervall Zeit: {details.get('intervall_time')}")
        logger.debug(f"Lüfter Hardware EIN: {details.get('is_fan_on')}")
        logger.debug(f"Laufzeit aktuell: {details.get('fan_runtime_current')}")

    # --- HEIZUNG ACTIVE ---
    elif decision.reason in ("HEIZUNG_ACTIVE", "HEIZUNG_MANUAL_ON"):
        log("Heizung aktiv")
        log(f"Modus: {details.get('heizung_mode')}")
        log(f"Restzeit: {details.get('remaining')}")

    # --- HEIZUNG NACHLAUF ---
    elif decision.reason == "HEIZUNG_NACHLAUF":
        log("Heizung Nachlauf")
        log(f"Noch: {details.get('nachlauf_remaining')}")

    elif decision.reason in ("HEIZUNG_IDLE", "HEIZUNG_DISABLED", "HEIZUNG_MANUAL_OFF"):
        log("Heizung inaktiv")
        log(f"Modus: {details.get('heizung_mode')}")
        log(f"Grund: {details.get('reason')}")

def handle_mode_change(event: Event):
    """Handle mode changes (Manual -> Auto, etc)"""
    try:
        old_mode = event.data["old_mode"]
        new_mode = event.data["new_mode"]
        decision = event.data["decision"]
        ctx = event.data["ctx"]
        
        d = decision.details or {}
        
        if new_mode == "auto":
            msg = f"🤖 Automatik ein\n➡️ {pretty_reason(decision.reason)}"
            
            send_notification(
                title="MODE CHANGE",
                message=msg
            )
        
        elif old_mode == "auto" and new_mode != "auto":
            msg = "🛑 Automatik aus"
            send_notification(
                title="MODE CHANGE",
                message=msg
            )
    
    except Exception as e:
        logger.error(f"Error in handle_mode_change: {e}", exc_info=True)


def register_handlers():
    event_bus.subscribe(EventType.TRANSITION, handle_transition_event)
    event_bus.subscribe(EventType.MODE_CHANGE, handle_mode_change)
    event_bus.subscribe(EventType.DECISION_LOG, handle_decision_log)
    event_bus.subscribe(EventType.SYSTEM_ALERT, handle_system_alert)
    event_bus.subscribe(EventType.DAILY_SUMMARY, handle_daily_summary)
