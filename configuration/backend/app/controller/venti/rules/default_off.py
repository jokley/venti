from ..rule_engine import rule
from ..decision import Decision

@rule(priority=90)
def default_off(ctx):
    return Decision(
        "off",
        "DEFAULT_OFF",
        {
            "mode": ctx.mode
        }
    )