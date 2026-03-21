from ..rule_engine import rule
from ..decision import Decision

@rule(priority=20)
def stock_build(ctx):

    if ctx.mode != "auto":
        return None

    if ctx.remainingTimeStock <= ctx.stock and ctx.stock > 0:
        return Decision(
            "on",
            "STOCK_BUILD",
            {
                "remaining": ctx.remainingTimeStock,
                "stock": ctx.stock,
                "restzeit": ctx.stock - ctx.remainingTimeStock
            }
        )