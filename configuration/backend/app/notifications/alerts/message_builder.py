def build_system_alert_message(alert):

    etype = alert[0]

    # =========================
    # BATTERY
    # =========================
    if etype == "BATTERY_ALERT":
        _, device, level, band = alert
        return f"🔋 {device}\nBattery: {level}%\nStatus: {band}"

    if etype == "BATTERY_RECOVERY":
        _, device, level = alert
        return f"🔋 {device}\nBattery recovered: {level}%"

    # =========================
    # RSSI
    # =========================
    if etype == "RSSI_WEAK":
        _, device, value = alert
        return f"📡 {device}\nSignal weak: {value} dBm"

    if etype == "RSSI_DEGRADED":
        _, device, value = alert
        return f"📡 {device}\nSignal degraded: {value} dBm"

    if etype == "RSSI_RECOVERY":
        _, device, value = alert
        return f"📡 {device}\nSignal recovered: {value} dBm"

    return f"ℹ️ {etype}"