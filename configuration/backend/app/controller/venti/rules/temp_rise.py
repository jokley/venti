from ..rule_engine import rule
from ..decision import Decision


@rule(priority=30)  # higher than interval
def temp_rise(ctx):

    if ctx.mode != "auto":
        return None

    # Only when fan is OFF
    if not ctx.is_fan_on:
        return None

    # temperature must be rising
    if ctx.temp_change_2h <= 2.0:
        return None

    return Decision(
        "on",
        "TEMP_RISE",
        {
            "temp_change_2h": ctx.temp_change_2h,
            "reason": "fan_off_temp_rising_start"
        }
    )