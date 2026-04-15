class BatteryEngine:
    def __init__(self):
        pass


def check_battery_alerts(data, state):
    """
    data = {"battery": {"probe01": 23, ...}}
    """

    events = []
    battery_map = data.get("battery", {})

    for device, value in battery_map.items():

        if value is None:
            continue

        level = int(value)

        # -------------------------
        # BAND LOGIC
        # -------------------------
        if level <= 10:
            band = "CRITICAL"
        elif level <= 20:
            band = "LOW"
        elif level <= 30:
            band = "WARNING"
        else:
            band = "OK"

        last = state.level_band.get(device)

        # -------------------------
        # ALERT
        # -------------------------
        if band != last and band != "OK":
            events.append((
                "BATTERY_ALERT",
                device,
                level,
                band
            ))

        # -------------------------
        # RECOVERY
        # -------------------------
        if last in ["CRITICAL", "LOW", "WARNING"] and band == "OK":
            events.append((
                "BATTERY_RECOVERY",
                device,
                level
            ))

        state.level_band[device] = band

    return events