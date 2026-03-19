from ..rule_engine import rule
from ..decision import Decision

@rule(priority=10)
def overheating(ctx):

    if ctx.tempMax >= ctx.uschutz_on:
        return Decision(
            "on",
            "OVERHEAT",
            {
                "tempMax": ctx.tempMax,
                "threshold": ctx.uschutz_on,
                "diff": ctx.tempMax - ctx.uschutz_on
            }
        )