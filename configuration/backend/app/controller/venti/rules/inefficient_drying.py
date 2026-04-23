from ..rule_engine import rule
from ..decision import Decision
from ..control.state_manager import state_manager


@rule(priority=28)
def inefficient_drying(ctx):

    if ctx.mode != "auto":
        return None

    MIN_RUNTIME = 2 * 3600
    COOLDOWN = 2 * 3600

    # =========================
    # 1. MINIMUM RUNTIME GATE
    # =========================
    if ctx.fan_runtime_current < MIN_RUNTIME:
        return None

    # =========================
    # 2. COOLDOWN CHECK (STATE MANAGER)
    # =========================
    last_stop = state_manager.last_inefficient_stop

    if last_stop is not None and (ctx.now - last_stop < COOLDOWN):
        return None

    # =========================
    # 3. INEFFICIENCY DETECTION
    # =========================
    if ctx.sdef_change_2h < 0.5 and ctx.ts_change_2h < 0.5:

        # store state in controller memory
        state_manager.last_inefficient_stop = ctx.now

        return Decision(
            "off",
            "INEFFICIENT_DRYING",
            {
                "sdef_change_2h": ctx.sdef_change_2h,
                "ts_change_2h": ctx.ts_change_2h,
                "runtime": ctx.fan_runtime_current
            }
        )

    return None