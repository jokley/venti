from ..rule_engine import rule
from ..decision import Decision

@rule(priority=25)
def inefficient_drying(ctx):

    if ctx.mode != "auto":
        return None

    # Stop drying if SDEF or TS has not risen enough (less than 0.5) in the last 2 hours, indicating inefficiency
    if ctx.sdef_change_2h < 0.5 or ctx.ts_change_2h < 0.5:
        return Decision(
            "off",
            "INEFFICIENT_DRYING",
            {
                "sdef_change_2h": ctx.sdef_change_2h,
                "ts_change_2h": ctx.ts_change_2h,
                "reason": "drying_inefficient_due_to_insufficient_rise"
            }
        )