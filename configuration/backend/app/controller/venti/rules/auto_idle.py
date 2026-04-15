from ..rule_engine import rule
from ..decision import Decision

@rule(priority=50)
def auto_idle(ctx):

    if ctx.mode != "auto":
        return None

    if (
        ctx.remainingTimeStock > ctx.stock
        and (
            ctx.sDefOut < ctx.sdefMinThreshold - ctx.sdef_hys_half
            or ctx.sDefOut < ctx.sdef_on - ctx.sdef_hys_half
            or ctx.tsSoll < ctx.tsMin - ctx.ts_hys_half
        )
    ):
        return Decision(
            "off",
            "AUTO_IDLE",
            {
                "reason": "drying_conditions_not_met",
                "sDefOut": ctx.sDefOut,
                "threshold": ctx.sdefMinThreshold,
                "tsDiff": ctx.tsSoll - ctx.tsMin
            }
        )