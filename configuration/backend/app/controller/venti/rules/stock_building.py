from ..rule_engine import rule
from ..decision import Decision

@rule(priority=20)
def stock_building(ctx):

    if ctx.mode != "auto":
        return None

    if ctx.remainingTimeStock <= ctx.stock and ctx.stock > 0:
        return Decision(
            "on",
            "STOCK_BUILDING",
            {
                "remaining": ctx.remainingTimeStock,
                "stock": ctx.stock,
                "restzeit": ctx.stock - ctx.remainingTimeStock
            }
        )