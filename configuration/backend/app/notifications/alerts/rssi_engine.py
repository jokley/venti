class RSSIEngine:
    pass


def check_rssi_alerts(data, state):

    events = []
    rssi_map = data.get("rssi", {})

    for device, value in rssi_map.items():

        if value is None:
            continue

        # -------------------------
        # STATES (with hysteresis)
        # -------------------------
        if value <= -85:
            status = "WEAK"
        elif value <= -75:
            status = "DEGRADED"
        else:
            status = "OK"

        last = state.signal_state.get(device)

        # -------------------------
        # ALERTS
        # -------------------------
        if status != last:

            if status == "WEAK":
                events.append(("RSSI_WEAK", device, value))

            elif status == "DEGRADED":
                events.append(("RSSI_DEGRADED", device, value))

            elif status == "OK" and last in ["WEAK", "DEGRADED"]:
                events.append(("RSSI_RECOVERY", device, value))

        state.signal_state[device] = status

    return events