SENSOR_MISSING_AFTER_SECONDS = 15 * 60
RELAY_MISMATCH_AFTER_SECONDS = 15 * 60
DEFAULT_ENDPHASE_TS_MARGIN = 3.0


class HardwareAlertState:
    def __init__(self):
        self.device_state = {}  # device -> "OK" / "MISSING"
        self.ro1_mismatch_since = None
        self.ro1_mismatch_alert_active = False
        self.do1_fault_since = None
        self.do1_fault_alert_active = False
        self.failsafe_state = None


def _is_missing(age, max_age=SENSOR_MISSING_AFTER_SECONDS):
    return age is not None and age > max_age


def _fmt_reason(reason):
    if reason == "all_probes_missing":
        return "Alle Innensonden ausgefallen"
    if reason == "outdoor_missing":
        return "Außensensor ausgefallen"
    if reason == "all_probes_and_outdoor_missing":
        return "Alle Innensonden und Außensensor ausgefallen"
    return reason


def _extract_ts_diff(decision):
    details = getattr(decision, "details", None) or {}
    value = details.get("tsDiff", details.get("ts_diff"))
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _endphase_ts_margin(ctx):
    value = getattr(ctx, "efficiency_endphase_ts_margin", None)
    try:
        return float(value) if value is not None else DEFAULT_ENDPHASE_TS_MARGIN
    except (TypeError, ValueError):
        return DEFAULT_ENDPHASE_TS_MARGIN


def _check_device_alerts(ctx, state):
    events = []

    for device, age in sorted((ctx.sensor_age or {}).items()):
        if device.startswith("probe"):
            missing_event = "PROBE_MISSING"
            recovery_event = "PROBE_RECOVERY"
        elif device.startswith("outdoor"):
            missing_event = "OUTDOOR_MISSING"
            recovery_event = "OUTDOOR_RECOVERY"
        else:
            continue

        current = "MISSING" if _is_missing(age) else "OK"
        previous = state.device_state.get(device, "OK")

        if current == previous:
            continue

        state.device_state[device] = current

        if current == "MISSING":
            events.append((missing_event, device, age))
        else:
            events.append((recovery_event, device, age))

    return events


def _reset_timed_alert(state, since_attr, active_attr, recovery_event):
    setattr(state, since_attr, None)
    if getattr(state, active_attr):
        setattr(state, active_attr, False)
        return [recovery_event]
    return []


def _check_timed_alert(state, now, since_attr, active_attr, alert_event):
    if now is None:
        return []

    if getattr(state, since_attr) is None:
        setattr(state, since_attr, now)
        return []

    duration = int(now - getattr(state, since_attr))
    if duration < RELAY_MISMATCH_AFTER_SECONDS or getattr(state, active_attr):
        return []

    setattr(state, active_attr, True)
    return [alert_event(duration)]


def _check_ro1_feedback(ctx, state, decision):
    # RO1 ist nur die Dragino/LT22222-Relay-Rueckmeldung. Sie sagt, ob das
    # Relais gesetzt ist, aber nicht, ob die Stern-Dreieck-Schuetzkette
    # tatsaechlich angezogen hat oder der Luefter wirklich laeuft.
    if decision is None:
        return []

    now = getattr(ctx, "now", None)
    command = getattr(decision, "command", None)
    ro1_should_be_on = command == "on"
    ro1_reports_off = not getattr(ctx, "is_fan_on", False)

    if not ro1_should_be_on or not ro1_reports_off:
        return _reset_timed_alert(
            state,
            "ro1_mismatch_since",
            "ro1_mismatch_alert_active",
            ("FAN_RO1_RECOVERY", "fan"),
        )

    return _check_timed_alert(
        state,
        now,
        "ro1_mismatch_since",
        "ro1_mismatch_alert_active",
        lambda duration: ("FAN_RO1_NO_FEEDBACK", "fan", duration),
    )


def _check_do1_feedback(ctx, state, decision):
    # DO1 ist die echte Rueckmeldung der Stern-Dreieck-Schuetzkombination:
    # 12V laufen ueber einen Oeffner. Wenn die Kombination nicht anzieht oder
    # eine Stoerung oeffnet, ist DO1 false. Nur DO1=true bestaetigt die
    # Schuetzkette; ein echter mechanischer Luefterausfall braucht separate
    # Sensorik.
    if decision is None:
        return []

    if not getattr(ctx, "fan_do1_check_enabled", False):
        return _reset_timed_alert(
            state,
            "do1_fault_since",
            "do1_fault_alert_active",
            ("FAN_DO1_RECOVERY", "fan"),
        )

    fan_do1_status = getattr(ctx, "fan_do1_status", {}) or {}
    do1_ok = fan_do1_status.get("ok")
    do1_age = fan_do1_status.get("age")
    now = getattr(ctx, "now", None)
    command = getattr(decision, "command", None)
    fan_should_run = command == "on"
    do1_stale = _is_missing(do1_age)

    if not fan_should_run or do1_ok is True:
        return _reset_timed_alert(
            state,
            "do1_fault_since",
            "do1_fault_alert_active",
            ("FAN_DO1_RECOVERY", "fan"),
        )

    if do1_ok is None and not do1_stale:
        # Keine DO1-Daten im Context und auch kein explizit veralteter Wert:
        # nichts behaupten.
        return []

    return _check_timed_alert(
        state,
        now,
        "do1_fault_since",
        "do1_fault_alert_active",
        lambda duration: (
            "FAN_DO1_CONTACTOR_FAULT",
            "fan",
            duration,
            fan_do1_status.get("status"),
            do1_age,
        ),
    )


def _check_failsafe_recommendation(ctx, state, decision):
    if getattr(ctx, "mode", None) != "auto":
        state.failsafe_state = None
        return []

    sensor_age = ctx.sensor_age or {}
    probes = {device: age for device, age in sensor_age.items() if device.startswith("probe")}
    outdoors = {device: age for device, age in sensor_age.items() if device.startswith("outdoor")}

    has_probe_ok = any(not _is_missing(age) for age in probes.values())
    has_outdoor_ok = any(not _is_missing(age) for age in outdoors.values())
    all_probes_missing = bool(probes) and not has_probe_ok
    outdoor_missing = bool(outdoors) and not has_outdoor_ok

    if all_probes_missing and outdoor_missing:
        reason = "all_probes_and_outdoor_missing"
    elif all_probes_missing:
        reason = "all_probes_missing"
    elif outdoor_missing:
        reason = "outdoor_missing"
    else:
        state.failsafe_state = None
        return []

    ts_diff = _extract_ts_diff(decision)
    threshold = _endphase_ts_margin(ctx)
    recommend_manual_on = ts_diff is not None and ts_diff > threshold
    event_type = (
        "HARDWARE_FAILSAFE_RECOMMEND_MANUAL_ON"
        if recommend_manual_on
        else "HARDWARE_FAILSAFE_WARN_ONLY"
    )
    signature = (event_type, reason)

    if state.failsafe_state == signature:
        return []

    state.failsafe_state = signature
    return [(event_type, _fmt_reason(reason), ts_diff, threshold)]


def check_hardware_alerts(ctx, state, decision=None):
    return (
        _check_device_alerts(ctx, state)
        + _check_ro1_feedback(ctx, state, decision)
        + _check_do1_feedback(ctx, state, decision)
        + _check_failsafe_recommendation(ctx, state, decision)
    )
