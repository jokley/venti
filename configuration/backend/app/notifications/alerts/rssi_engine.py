RSSI_LOW = -85
RSSI_CRITICAL = -95
RSSI_RECOVER = -75


class RSSIAlertState:
    def __init__(self):
        self.state = {}  # device -> "OK / LOW / CRITICAL"


def check_rssi_alerts(ctx, state):

    events = []

    for device, value in ctx.rssi.items():

        if value is None:
            continue

        prev = state.state.get(device, "OK")

        # -------------------------
        # CRITICAL
        # -------------------------
        if value <= RSSI_CRITICAL and prev != "CRITICAL":
            state.state[device] = "CRITICAL"
            events.append(("RSSI_CRITICAL", device, value))
            continue

        # -------------------------
        # LOW
        # -------------------------
        if value <= RSSI_LOW and prev == "OK":
            state.state[device] = "LOW"
            events.append(("RSSI_LOW", device, value))
            continue

        # -------------------------
        # RECOVERY (hysteresis)
        # -------------------------
        if value >= RSSI_RECOVER and prev != "OK":
            state.state[device] = "OK"
            events.append(("RSSI_RECOVER", device, value))

    return events