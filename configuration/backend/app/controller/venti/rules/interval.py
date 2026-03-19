from ..rule_engine import rule
from ..decision import Decision

@rule(priority=40)
def interval(ctx):

    if ctx.mode != "auto":
        return None

    if ctx.humMax > ctx.intervall_on:

        if (
            ctx.remainingTimeInterval >= ctx.intervall_time
            or (
                ctx.remainingTimeIntervalOn <= ctx.intervall_duration
                and ctx.remainingTimeIntervalDiff > 0
            )
        ):
            return Decision(
                "on",
                "INTERVAL",
                {
                    "humMax": ctx.humMax,
                    "threshold": ctx.intervall_on,
                    "interval_time": ctx.intervall_time,
                    "since_last_on": ctx.remainingTimeInterval
                }
            )