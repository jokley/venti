class BatteryState:
    def __init__(self):
        self.level_band = {}  # device → band


class RSSIState:
    def __init__(self):
        self.signal_state = {}  # device → state


class AlertState:
    def __init__(self):
        self.battery = BatteryState()
        self.rssi = RSSIState()


# 🔥 singleton (IMPORTANT)
alert_state = AlertState()