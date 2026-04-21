from ..rule_engine import rule
from ..decision import Decision

@rule(priority=40)
def interval_active(ctx):

    if ctx.mode != "auto":
        return None

    # Check if temperature has risen more than 2°C in the last 2 hours
    temp_rising_condition = ctx.temp_change_2h > 2.0

    if ctx.humMax > ctx.intervall_on or temp_rising_condition:

        if (
            ctx.remainingTimeInterval >= ctx.intervall_time
            or (
                ctx.remainingTimeIntervalOn <= ctx.intervall_duration
                and ctx.remainingTimeIntervalDiff > 0
            )
        ):
            reason = "INTERVAL_ACTIVE"
            details = {
                "humMax": ctx.humMax,
                "threshold": ctx.intervall_on,
                "interval_time": ctx.intervall_time,
                "since_last_on": ctx.remainingTimeInterval
            }
            
            if temp_rising_condition:
                reason = "TEMPERATURE_RISING"
                details["temp_change_2h"] = ctx.temp_change_2h
            
            return Decision("on", reason, details)