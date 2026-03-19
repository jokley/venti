from ..rule_engine import rule
from ..decision import Decision

@rule(priority=6)
def manual_off(ctx):
    if ctx.mode == "off":
        return Decision("off", "MANUAL_OFF")