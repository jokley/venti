from ..rule_engine import rule
from ..decision import Decision

@rule(priority=90)
def auto_idle_default(ctx):
    return Decision(
        "off",
        "AUTO_IDLE",
        {
            "mode": ctx.mode
        }
    )