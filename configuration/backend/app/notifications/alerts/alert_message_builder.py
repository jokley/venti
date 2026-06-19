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
        return f"⚠️ Lüfter Relay RO1 antwortet nicht\nRO1 passt seit {fmt_minutes(duration)}min nicht zum Soll-Zustand."

    if etype in ("FAN_RO1_RECOVERY", "FAN_RELAY_RECOVERY"):
        return "✅ Lüfter Relay RO1 meldet wieder korrekt"

    if etype == "FAN_DI1_CONTACTOR_FAULT":
        _, _device, duration, status, age, expected, ro1_status = (
            alert + (None, None)
        )[:7]
        return (
            "⚠️ Lüfter Schütz-Kombination meldet nicht OK\n"
            f"RO1={ro1_status}, DI1={status}, erwartet DI1={expected}. "
            f"Abweichung seit {fmt_minutes(duration)}min "
            f"(DI1-Alter: {fmt_minutes(age)}min)."
        )

    if etype == "FAN_DI1_RECOVERY":
        return "✅ Lüfter Schütz-Kombination / DI1 wieder OK"

    if etype == "HEIZUNG_RO2_NO_FEEDBACK":
        _, _device, duration, status, expected = alert
        return (
            "⚠️ Heizung Relay RO2 antwortet nicht\n"
            f"RO2={status}, erwartet RO2={expected}. "
            f"Abweichung seit {fmt_minutes(duration)}min."
        )

    if etype == "HEIZUNG_RO2_RECOVERY":
        return "✅ Heizung Relay RO2 meldet wieder korrekt"

    if etype == "HEIZUNG_RO1_FORCED_FAN_NO_FEEDBACK":
        _, _device, duration, status, expected = alert
        return (
            "⚠️ Heizung erzwingt Lüfter, aber RO1 passt nicht\n"
            f"RO1={status}, erwartet RO1={expected}. "
            f"Abweichung seit {fmt_minutes(duration)}min."
        )

    if etype == "HEIZUNG_RO1_FORCED_FAN_RECOVERY":
        return "✅ Heizung/Lüfter-Kopplung RO1 wieder korrekt"

    if etype == "HEIZUNG_DI2_CONTACTOR_FAULT":
        _, _device, duration, status, age, expected, ro2_status = (
            alert + (None, None)
        )[:7]
        return (
            "⚠️ Heizung Schütz/Rückmeldung meldet nicht OK\n"
            f"RO2={ro2_status}, DI2={status}, erwartet DI2={expected}. "
            f"Abweichung seit {fmt_minutes(duration)}min "
            f"(DI2-Alter: {fmt_minutes(age)}min)."
        )

    if etype == "HEIZUNG_DI2_RECOVERY":
        return "✅ Heizung DI2 Rückmeldung wieder OK"

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
