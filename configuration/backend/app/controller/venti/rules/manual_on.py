from ..rule_engine import rule
from ..decision import Decision

@rule(priority=5)
def manual_on(ctx):
    if ctx.mode == "on":
        return Decision("on", "MANUAL_ON")