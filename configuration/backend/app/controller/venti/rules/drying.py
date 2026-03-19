from ..rule_engine import rule
from ..decision import Decision

@rule(priority=30)
def drying(ctx):

    if ctx.mode != "auto":
        return None

    if (
        ctx.sDefOut >= ctx.sdefMinThreshold + ctx.sdef_hys_half
        and ctx.sDefOut >= ctx.sdef_on + ctx.sdef_hys_half
        and ctx.tsSoll >= ctx.tsMin + ctx.ts_hys_half
    ):
        return Decision(
            "on",
            "DRYING",
            {
                "sDefOut": ctx.sDefOut,
                "sDefMin": ctx.sDefMin,
                "sDefDiff": ctx.sDefOut - ctx.sDefMin,
                "tsMin": ctx.tsMin,
                "tsSoll": ctx.tsSoll,
                "tsDiff": ctx.tsSoll - ctx.tsMin
            }
        )