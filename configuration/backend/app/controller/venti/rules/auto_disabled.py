from ..rule_engine import rule
from ..decision import Decision

@rule(priority=25)
def auto_disable(ctx):

    if ctx.mode != "auto":
        return None

    if (
        ctx.remainingTimeInterval >= 7200
        and (ctx.tsSoll - ctx.tsMin) <= 0.5
    ):
        from app.services.venti_service import venti_auto

        venti_auto("off", ctx.tsSoll, "0")

        return Decision(
            "off",
            "AUTO_DISABLED",
            {
                "runtime": ctx.remainingTimeInterval,
                "tsDiff": ctx.tsSoll - ctx.tsMin
            }
        )