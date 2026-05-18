VENTI_CONTROL_INTERVAL_SECONDS = 4 * 60
INTERVAL_END_TOLERANCE_SECONDS = 5


def get_interval_scheduler_delay(
    decision,
    base_interval_seconds=VENTI_CONTROL_INTERVAL_SECONDS,
    tolerance_seconds=INTERVAL_END_TOLERANCE_SECONDS,
):
    if decision is None or decision.reason != "INTERVAL_ACTIVE":
        return None

    remaining = (decision.details or {}).get("remaining")

    if remaining is None:
        return None

    try:
        remaining = int(remaining)
    except (TypeError, ValueError):
        return None

    if remaining >= base_interval_seconds:
        return None

    return max(tolerance_seconds, remaining + tolerance_seconds)
