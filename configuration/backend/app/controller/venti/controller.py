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


def venti_control():

    data = build_control_data()
    ctx = VentiContext(data)

    decision = evaluate(ctx)

    venti_cmd(decision.command)

    logger.info(
        f"VENTI | mode={ctx.mode} | cmd={decision.command} | reason={decision.reason}"
    )

    # 🔥 detailed debug logging
    if decision.details:
        logger.debug(f"DETAILS | {decision.details}")