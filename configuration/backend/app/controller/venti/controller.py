from .rule_engine import rules
from .decision import Decision
from .context import VentiContext
from app.services.control_data import build_control_data
from app.services.venti_service import venti_cmd
from app.notifications.transitions import TransitionDetector
from app.notifications.message_builder import build_event_message,build_message
from app.notifications.notifier import send_notification
from app.notifications.alerts.state import alert_state
from app.notifications.alerts.battery_engine import check_battery_alerts
from app.notifications.alerts.rssi_engine import check_rssi_alerts
from app.notifications.alerts.message_builder import build_system_alert_message

from app.utils.logger import logger

# IMPORTANT: load rules
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
            # attach trace to decision
            result.details["trace"] = trace
            return result

    # fallback if no rule matches
    return Decision(
        "off",
        "NO_CONDITION",
        {
            "trace": trace
        }
    )

def log_decision(ctx, decision):

    logger.info("****************************************")
    logger.info(f"Mode: {ctx.mode}")
    logger.info(f"Command: {decision.command}")
    logger.info(f"Reason: {decision.reason}")

    d = decision.details or {}

    # --- OVERHEAT ---
    if decision.reason == "OVERHEAT":
        logger.info("Überhitzungsschutz aktiv!")
        logger.info(f"Temperatur: {d.get('tempMax')} | Schwelle: {d.get('threshold')}")
        logger.info(f"Differenz: {d.get('diff')}")

    # --- STOCK BUILD ---
    elif decision.reason == "STOCK_BUILD":
        logger.info("Stockaufbau")
        logger.info(f"Restzeit aktuell: {d.get('remaining')}")
        logger.info(f"Stock-Ziel: {d.get('stock')}")
        logger.info(f"Restzeit bis Ende: {d.get('restzeit')}")

    # --- DRYING (Lüfter ein) ---
    elif decision.reason == "DRYING":
        logger.info("Lüfter ein")
        logger.info(f"SDef min: {d.get('sDefMin')} | SDef out: {d.get('sDefOut')}")
        logger.info(f"SDef diff: {d.get('sDefDiff')}")
        logger.info(f"TS ist: {d.get('tsMin')} | TS soll: {d.get('tsSoll')}")
        logger.info(f"TS diff: {d.get('tsDiff')}")

    # --- INTERVAL ---
    elif decision.reason == "INTERVAL":
        logger.info("Intervall Belüftung")
        logger.info(f"Hum max: {d.get('humMax')} | Schwelle: {d.get('threshold')}")
        logger.info(f"Intervall Zeit: {d.get('interval_time')}")
        logger.info(f"Seit letztem Einschalten: {d.get('since_last_on')}")

    # --- DRYING STOP / Lüfter aus ---
    elif decision.reason == "DRYING_STOP":
        logger.info("Lüfter aus (Trockenphase beendet / Bedingungen nicht erfüllt)")
        logger.info(f"SDef out: {d.get('sDefOut')} | Schwelle: {d.get('threshold')}")
        logger.info(f"TS diff: {d.get('tsDiff')}")

    # --- AUTO DISABLED ---
    elif decision.reason == "AUTO_DISABLED":
        logger.info("Automatik deaktiviert")
        logger.info(f"Laufzeit Intervall: {d.get('runtime')}")
        logger.info(f"TS diff: {d.get('tsDiff')}")

    # --- DEFAULT OFF ---
    elif decision.reason == "DEFAULT_OFF":
        logger.info("Standardzustand: Lüfter aus")
        logger.info(f"Mode: {d.get('mode')}")

detector = TransitionDetector()


def venti_control():
    # =========================
    # 1. BUILD CONTEXT
    # =========================
    data = build_control_data()
    ctx = VentiContext(data)

    # =========================
    # 2. RULE ENGINE
    # =========================
    decision = evaluate(ctx)

    # =========================
    # 3. EXECUTE CONTROL
    # =========================
    venti_cmd(decision.command)

    # =========================
    # 4. LOGGING
    # =========================
    log_decision(ctx, decision)

    # =========================
    # 5. TRANSITION EVENTS
    # =========================
    events = detector.detect(decision, data)

    for event in events:
        msg = build_event_message(event)

        if msg:
            send_notification(
                title=event[0],
                message=msg
            )

    # =========================
    # 6. SYSTEM ALERTS (NEW LAYER)
    # =========================
   

    battery_events = check_battery_alerts(data, alert_state.battery)
    rssi_events = check_rssi_alerts(data, alert_state.rssi)

    system_events = battery_events + rssi_events

    for alert in system_events:
        msg = build_system_alert_message(alert)

        send_notification(
            title=alert[0],
            message=msg
        )