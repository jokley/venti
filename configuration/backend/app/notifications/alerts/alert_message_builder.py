def build_system_alert_message(alert):

    etype = alert[0]

    def fmt_minutes(seconds):
        try:
            return max(1, int(seconds) // 60)
        except (TypeError, ValueError):
            return "?"

    def fmt_percent(value):
        if value is None:
            return "unbekannt"
        try:
            return f"{float(value):.1f}%"
        except (TypeError, ValueError):
            return f"{value}%"

    # =========================
    # BATTERY
    # =========================
    if etype in ("BATTERY_ALERT", "BATTERY_LOW"):
        _, device, level, band = alert
        return f"🔋 {device}\nBattery: {level}%\nStatus: {band}"

    if etype == "BATTERY_RECOVERY":
        _, device, level = alert
        return f"🔋 {device}\nBattery recovered: {level}%"

    # =========================
    # RSSI
    # =========================
    if etype in ("RSSI_WEAK", "RSSI_LOW"):
        _, device, value = alert
        return f"📡 {device}\nSignal weak: {value} dBm"

    if etype in ("RSSI_DEGRADED", "RSSI_CRITICAL"):
        _, device, value = alert
        return f"📡 {device}\nSignal degraded: {value} dBm"

    if etype in ("RSSI_RECOVERY", "RSSI_RECOVER"):
        _, device, value = alert
        return f"📡 {device}\nSignal recovered: {value} dBm"

    # =========================
    # HARDWARE / SENSOR HEALTH
    # =========================
    if etype == "PROBE_MISSING":
        _, device, age = alert
        return f"⚠️ {device} ausgefallen – seit {fmt_minutes(age)}min kein Signal"

    if etype == "OUTDOOR_MISSING":
        _, device, age = alert
        return f"⚠️ {device} ausgefallen – seit {fmt_minutes(age)}min kein Signal"

    if etype == "PROBE_RECOVERY":
        _, device, _age = alert
        return f"✅ {device} wieder aktiv"

    if etype == "OUTDOOR_RECOVERY":
        _, device, _age = alert
        return f"✅ {device} wieder aktiv"

    if etype in ("FAN_RO1_NO_FEEDBACK", "FAN_RELAY_NO_FEEDBACK"):
        _, _device, duration = alert
        return f"⚠️ Lüfter Relay RO1 antwortet nicht\nRO1 meldet seit {fmt_minutes(duration)}min nicht EIN."

    if etype in ("FAN_RO1_RECOVERY", "FAN_RELAY_RECOVERY"):
        return "✅ Lüfter Relay RO1 meldet wieder korrekt"

    if etype == "FAN_DI1_CONTACTOR_FAULT":
        _, _device, duration, status, age = alert
        return (
            "⚠️ Lüfter Schütz-Kombination meldet nicht OK\n"
            f"DI1 ist seit {fmt_minutes(duration)}min nicht TRUE "
            f"(Status: {status}, Alter: {fmt_minutes(age)}min). "
            "Stern-Dreieck / Motorschutz prüfen."
        )

    if etype == "FAN_DI1_RECOVERY":
        return "✅ Lüfter Schütz-Kombination / DI1 wieder OK"

    if etype == "HARDWARE_FAILSAFE_RECOMMEND_MANUAL_ON":
        _, reason, ts_diff, threshold = alert
        return (
            f"⚠️ {reason} bei TS-Abstand {fmt_percent(ts_diff)}\n"
            f"Endphase-Grenze: {fmt_percent(threshold)}\n"
            "Empfehlung: Lüfter manuell EIN schalten"
        )

    if etype == "HARDWARE_FAILSAFE_WARN_ONLY":
        _, reason, ts_diff, threshold = alert
        return (
            f"⚠️ {reason} bei TS-Abstand {fmt_percent(ts_diff)}\n"
            f"Endphase-Grenze: {fmt_percent(threshold)}\n"
            "Automatik läuft weiter – bitte Sensorik prüfen"
        )

    return f"ℹ️ {etype}"
