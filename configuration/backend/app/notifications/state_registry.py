from app.notifications.alerts.battery_engine import BatteryAlertState
from app.notifications.alerts.rssi_engine import RSSIAlertState
from app.notifications.summary.summary_state import SummaryState


class AlertState:
    def __init__(self):
        self.battery = BatteryAlertState()
        self.rssi = RSSIAlertState()
        self.summary = SummaryState()


# 🔥 SINGLETON (VERY IMPORTANT)
alert_state = AlertState()