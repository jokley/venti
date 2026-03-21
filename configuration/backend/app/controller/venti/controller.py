from .rule_engine import rules
from .decision import Decision
from .context import VentiContext
from app.services.control_data import build_control_data
from app.services.venti_service import venti_cmd
from app.utils.logger import logger

# IMPORTANT: load rules
from .rules import *


def evaluate(ctx):
    for priority, rule_func in rules:
        decision = rule_func(ctx)
        if decision:
            return decision
    return Decision("off", "NO_CONDITION")

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


def venti_control():

    data = build_control_data()
    ctx = VentiContext(data)

    decision = evaluate(ctx)

    venti_cmd(decision.command)

    log_decision(ctx, decision)

    # logger.info(
    #     f"VENTI | mode={ctx.mode} | cmd={decision.command} | reason={decision.reason}"
    # )

    # # 🔥 detailed debug logging
    # if decision.details:
    #     logger.debug(f"DETAILS | {decision.details}")