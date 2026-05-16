from .event_bus import event_bus, EventType, Event
from app.notifications.event_message_builder import (
    build_event_message,
    fmt_duration,
    fmt_percent,
    fmt_float,
    pretty_reason
)
from app.notifications.notifier import send_notification
from app.notifications.alerts.alert_message_builder import build_system_alert_message
from app.utils.logger import logger

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
    decision = event.data["decision"]
    ctx = event.data["ctx"]
    details = decision.details or {}

    logger.info("****************************************")
    logger.info(f"Mode: {ctx.mode}")
    logger.info(f"Command: {decision.command}")
    logger.info(f"Reason: {decision.reason}")

    if decision.reason == "OVERHEAT":
        logger.info("Überhitzungsschutz aktiv!")
        logger.info(f"Temperatur: {details.get('tempMax')} | Schwelle: {details.get('threshold')}")
        logger.info(f"Differenz: {details.get('diff')}")

    elif decision.reason == "STOCK_BUILDING":
        logger.info("Stockaufbau")
        logger.info(f"Restzeit aktuell: {details.get('remaining')}")
        logger.info(f"Stock-Ziel: {details.get('stock')}")
        logger.info(f"Restzeit bis Ende: {details.get('restzeit')}")

    # --- DRYING_ACTIVE (Lüfter ein) ---
    elif decision.reason == "DRYING_ACTIVE":
        logger.info("Lüfter ein")
        logger.info(f"SDef min: {details.get('sDefMin')} | SDef out: {details.get('sDefOut')}")
        logger.info(f"SDef diff: {details.get('sDefDiff')}")
        logger.info(f"TS ist: {details.get('tsMin')} | TS soll: {details.get('tsSoll')}")
        logger.info(f"TS diff: {details.get('tsDiff')}")
        logger.info(f"Effizienz: {details.get('efficiency')} | Limit: {details.get('adaptive_threshold')}")

    # --- INTERVAL_ACTIVE ---
    elif decision.reason == "INTERVAL_ACTIVE":
        logger.info("Intervall Belüftung")
        logger.info(f"Hum max: {details.get('humMax')} | Schwelle: {details.get('threshold')}")
        logger.info(f"Intervall Zeit: {details.get('interval_time')}")
        logger.info(f"Seit letztem Einschalten: {details.get('since_last_on')}")

    # --- INEFFICIENT_DRYING ---
    elif decision.reason == "INEFFICIENT_DRYING":
        logger.info("Ineffiziente Trocknung erkannt")
        logger.info(f"SDEF Change 2h: {details.get('sdef_change_2h')}")
        logger.info(f"TS Change 2h: {details.get('ts_change_2h')}")
        logger.info(f"Effizienz: {details.get('efficiency')} | Limit: {details.get('adaptive_threshold')}")

    # --- MANUAL STATES ---
    elif decision.reason in ("MANUAL_MODE", "VENTI_MANUAL_ON", "VENTI_MANUAL_OFF"):
        logger.info("Automatik deaktiviert")
        logger.info(f"State: {decision.reason}")
        logger.info(f"Laufzeit Intervall: {details.get('runtime')}")
        logger.info(f"TS diff: {details.get('tsDiff')}")

    # --- AUTO_IDLE ---
    elif decision.reason == "AUTO_IDLE":
        logger.info("Automatik im Leerlauf")
        logger.info(f"Reason: {details.get('reason')}")
        logger.info(f"Effizienz: {details.get('efficiency')} | Limit: {details.get('adaptive_threshold')}")

    # --- HEIZUNG ACTIVE ---
    elif decision.reason in ("HEIZUNG_ACTIVE", "HEIZUNG_MANUAL_ON"):
        logger.info("Heizung aktiv")
        logger.info(f"Modus: {details.get('heizung_mode')}")
        logger.info(f"Restzeit: {details.get('remaining')}")

    # --- HEIZUNG NACHLAUF ---
    elif decision.reason == "HEIZUNG_NACHLAUF":
        logger.info("Heizung Nachlauf")
        logger.info(f"Noch: {details.get('nachlauf_remaining')}")

    elif decision.reason in ("HEIZUNG_IDLE", "HEIZUNG_DISABLED", "HEIZUNG_MANUAL_OFF"):
        logger.info("Heizung inaktiv")
        logger.info(f"Modus: {details.get('heizung_mode')}")
        logger.info(f"Grund: {details.get('reason')}")

def handle_mode_change(event: Event):
    """Handle mode changes (Manual -> Auto, etc)"""
    try:
        old_mode = event.data["old_mode"]
        new_mode = event.data["new_mode"]
        decision = event.data["decision"]
        ctx = event.data["ctx"]
        
        d = decision.details or {}
        
        if new_mode == "auto":
            state = decision.reason
            
            if state == "STOCK_BUILDING":
                msg = (
                    f"🤖 Automatik ein\n"
                    f"🌾 Stockaufbau gestartet\n"
                    f"🌾 Ziel: {fmt_duration(d.get('stock'))}\n"
                    f"⏳ Restzeit: {fmt_duration(d.get('restzeit'))}"
                )
            elif state == "INTERVAL_ACTIVE":
                msg = (
                    f"🤖 Automatik ein\n"
                    f"⏱ Intervallbelüftung gestartet\n"
                    f"💧 Feuchte: {fmt_percent(d.get('humMax'))}\n"
                    f"📉 Limit: {fmt_percent(d.get('threshold'))}"
                )
            elif state == "DRYING_ACTIVE":
                msg = (
                    f"🤖 Automatik ein\n"
                    f"💨 Trocknung gestartet\n"
                    f"🌬 SDef: {fmt_float(d.get('sDefOut'))}"
                )
            else:
                msg = f"🤖 Automatik ein\n➡️ {pretty_reason(state)}"
            
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
