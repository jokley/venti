SENSOR_MISSING_AFTER_SECONDS = 15 * 60
HARDWARE_MISMATCH_AFTER_SECONDS = 4 * 60
DEFAULT_ENDPHASE_TS_MARGIN = 3.0


class HardwareAlertState:
    def __init__(self):
        self.device_state = {}  # device -> "OK" / "MISSING"
        self.ro1_mismatch_since = None
        self.ro1_mismatch_alert_active = False
        self.di1_fault_since = None
        self.di1_fault_alert_active = False
        self.ro2_mismatch_since = None
        self.ro2_mismatch_alert_active = False
        self.heizung_ro1_mismatch_since = None
        self.heizung_ro1_mismatch_alert_active = False
        self.di2_fault_since = None
        self.di2_fault_alert_active = False
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
    if duration < HARDWARE_MISMATCH_AFTER_SECONDS or getattr(state, active_attr):
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
    ro1_is_on = bool(getattr(ctx, "is_fan_on", False))

    if command not in ("on", "off") or ro1_is_on == ro1_should_be_on:
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


def _check_di1_feedback(ctx, state, decision):
    # DI1 ist die echte Rueckmeldung der Stern-Dreieck-Schuetzkombination:
    # Bei RO1=ON muss DI1=L melden. Bei RO1=OFF muss DI1=H melden.
    # Andere Kombinationen bedeuten: die Stern-Dreieck-Kombination hat
    # hardwareseitig nicht passend ein- oder ausgeschaltet. Ein echter
    # mechanischer Luefterausfall braucht separate Sensorik.
    if decision is None:
        return []

    if not getattr(ctx, "fan_di1_check_enabled", False):
        return _reset_timed_alert(
            state,
            "di1_fault_since",
            "di1_fault_alert_active",
            ("FAN_DI1_RECOVERY", "fan"),
        )

    fan_di1_status = getattr(ctx, "fan_di1_status", {}) or {}
    di1_status = str(fan_di1_status.get("status") or "").strip().upper()
    di1_age = fan_di1_status.get("age")
    now = getattr(ctx, "now", None)
    ro1_on = bool(getattr(ctx, "is_fan_on", False))
    di1_stale = _is_missing(di1_age)
    expected_di1 = "L" if ro1_on else "H"

    if di1_status == expected_di1:
        return _reset_timed_alert(
            state,
            "di1_fault_since",
            "di1_fault_alert_active",
            ("FAN_DI1_RECOVERY", "fan"),
        )

    if not di1_status and not di1_stale:
        # Keine DI1-Daten im Context und auch kein explizit veralteter Wert:
        # nichts behaupten.
        return []

    return _check_timed_alert(
        state,
        now,
        "di1_fault_since",
        "di1_fault_alert_active",
        lambda duration: (
            "FAN_DI1_CONTACTOR_FAULT",
            "fan",
            duration,
            fan_di1_status.get("status"),
            di1_age,
            expected_di1,
            "ON" if ro1_on else "OFF",
        ),
    )


def _status_value(status):
    return str((status or {}).get("status") or "").strip().upper()


def _status_age(status):
    return (status or {}).get("age")


def _check_ro2_feedback(ctx, state, decision):
    if decision is None:
        return []

    if not getattr(ctx, "heizung_di2_check_enabled", False):
        return _reset_timed_alert(
            state,
            "ro2_mismatch_since",
            "ro2_mismatch_alert_active",
            ("HEIZUNG_RO2_RECOVERY", "fan"),
        )

    now = getattr(ctx, "now", None)
    command = getattr(decision, "command", None)
    ro2_should_be_on = command == "on"
    ro2_status = _status_value(getattr(ctx, "heizung_ro2_status", {}))
    ro2_is_on = ro2_status == "ON"

    if command not in ("on", "off") or (ro2_status and ro2_is_on == ro2_should_be_on):
        return _reset_timed_alert(
            state,
            "ro2_mismatch_since",
            "ro2_mismatch_alert_active",
            ("HEIZUNG_RO2_RECOVERY", "fan"),
        )

    if not ro2_status and not _is_missing(_status_age(getattr(ctx, "heizung_ro2_status", {}))):
        return []

    return _check_timed_alert(
        state,
        now,
        "ro2_mismatch_since",
        "ro2_mismatch_alert_active",
        lambda duration: (
            "HEIZUNG_RO2_NO_FEEDBACK",
            "fan",
            duration,
            ro2_status or None,
            "ON" if ro2_should_be_on else "OFF",
        ),
    )


def _check_heizung_ro1_feedback(ctx, state, decision):
    if decision is None:
        return []

    if not getattr(ctx, "heizung_di2_check_enabled", False):
        return _reset_timed_alert(
            state,
            "heizung_ro1_mismatch_since",
            "heizung_ro1_mismatch_alert_active",
            ("HEIZUNG_RO1_FORCED_FAN_RECOVERY", "fan"),
        )

    # Heizung und Nachlauf erzwingen RO1=Luefter EIN. Wenn die Heizung RO1
    # nicht mehr erzwingt, uebernimmt wieder der normale venti_control().
    forced_fan_on = getattr(decision, "reason", None) in (
        "HEIZUNG_ACTIVE",
        "HEIZUNG_MANUAL_ON",
        "HEIZUNG_NACHLAUF",
    )
    if not forced_fan_on:
        return _reset_timed_alert(
            state,
            "heizung_ro1_mismatch_since",
            "heizung_ro1_mismatch_alert_active",
            ("HEIZUNG_RO1_FORCED_FAN_RECOVERY", "fan"),
        )

    now = getattr(ctx, "now", None)
    ro1_status = _status_value(getattr(ctx, "heizung_ro1_status", {}))
    ro1_is_on = ro1_status == "ON"

    if ro1_status and ro1_is_on:
        return _reset_timed_alert(
            state,
            "heizung_ro1_mismatch_since",
            "heizung_ro1_mismatch_alert_active",
            ("HEIZUNG_RO1_FORCED_FAN_RECOVERY", "fan"),
        )

    if not ro1_status and not _is_missing(_status_age(getattr(ctx, "heizung_ro1_status", {}))):
        return []

    return _check_timed_alert(
        state,
        now,
        "heizung_ro1_mismatch_since",
        "heizung_ro1_mismatch_alert_active",
        lambda duration: (
            "HEIZUNG_RO1_FORCED_FAN_NO_FEEDBACK",
            "fan",
            duration,
            ro1_status or None,
            "ON",
        ),
    )


def _check_di2_feedback(ctx, state, decision):
    if decision is None:
        return []

    if not getattr(ctx, "heizung_di2_check_enabled", False):
        return _reset_timed_alert(
            state,
            "di2_fault_since",
            "di2_fault_alert_active",
            ("HEIZUNG_DI2_RECOVERY", "fan"),
        )

    heizung_di2_status = getattr(ctx, "heizung_di2_status", {}) or {}
    heizung_ro2_status = getattr(ctx, "heizung_ro2_status", {}) or {}
    di2_status = _status_value(heizung_di2_status)
    ro2_status = _status_value(heizung_ro2_status)
    di2_age = _status_age(heizung_di2_status)
    now = getattr(ctx, "now", None)

    if not ro2_status and not _is_missing(_status_age(heizung_ro2_status)):
        return []

    ro2_on = ro2_status == "ON"
    expected_di2 = "L" if ro2_on else "H"

    if di2_status == expected_di2:
        return _reset_timed_alert(
            state,
            "di2_fault_since",
            "di2_fault_alert_active",
            ("HEIZUNG_DI2_RECOVERY", "fan"),
        )

    if not di2_status and not _is_missing(di2_age):
        return []

    return _check_timed_alert(
        state,
        now,
        "di2_fault_since",
        "di2_fault_alert_active",
        lambda duration: (
            "HEIZUNG_DI2_CONTACTOR_FAULT",
            "fan",
            duration,
            heizung_di2_status.get("status"),
            di2_age,
            expected_di2,
            "ON" if ro2_on else "OFF",
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
        + _check_di1_feedback(ctx, state, decision)
        + _check_failsafe_recommendation(ctx, state, decision)
    )


def check_heizung_hardware_alerts(ctx, state, decision=None):
    return (
        _check_heizung_ro1_feedback(ctx, state, decision)
        + _check_ro2_feedback(ctx, state, decision)
        + _check_di2_feedback(ctx, state, decision)
    )
