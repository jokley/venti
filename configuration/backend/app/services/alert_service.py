from influxdb_client import Point
from influxdb_client.client.write_api import SYNCHRONOUS

from app.config import Config
from app.db.influx_client import get_influxdb_client
from app.utils.logger import logger

RECOVERY_SUFFIXES = ("_RECOVERY",)
INFO_ALERTS = {
    "FAN_RO1_RECOVERY",
    "FAN_RELAY_RECOVERY",
    "FAN_DO1_RECOVERY",
    "FAN_DI1_RECOVERY",
    "PROBE_RECOVERY",
    "OUTDOOR_RECOVERY",
    "RSSI_RECOVER",
    "RSSI_RECOVERY",
    "BATTERY_RECOVERY",
}
CRITICAL_ALERTS = {
    "PROBE_MISSING",
    "OUTDOOR_MISSING",
    "FAN_DO1_CONTACTOR_FAULT",
    "FAN_DI1_CONTACTOR_FAULT",
    "RSSI_CRITICAL",
}
WARNING_ALERTS = {
    "BATTERY_LOW",
    "BATTERY_ALERT",
    "RSSI_LOW",
    "RSSI_WEAK",
    "RSSI_DEGRADED",
    "FAN_RO1_NO_FEEDBACK",
    "FAN_RELAY_NO_FEEDBACK",
    "HARDWARE_FAILSAFE_RECOMMEND_MANUAL_ON",
    "HARDWARE_FAILSAFE_WARN_ONLY",
}


def get_alert_group(alert_type):
    if alert_type.startswith("BATTERY"):
        return "battery"
    if alert_type.startswith("RSSI"):
        return "rssi"
    if alert_type.startswith("PROBE") or alert_type.startswith("OUTDOOR"):
        return "sensor"
    if alert_type.startswith("FAN"):
        return "fan"
    if alert_type.startswith("HARDWARE_FAILSAFE"):
        return "failsafe"
    return "system"


def get_alert_severity(alert_type):
    if alert_type in INFO_ALERTS or alert_type.endswith(RECOVERY_SUFFIXES):
        return "info"
    if alert_type in CRITICAL_ALERTS:
        return "critical"
    if alert_type in WARNING_ALERTS:
        return "warning"
    return "info"


def is_alert_active(alert_type):
    return not (alert_type in INFO_ALERTS or alert_type.endswith(RECOVERY_SUFFIXES))


def get_alert_device(alert):
    if len(alert) > 1 and alert[1] is not None:
        return str(alert[1])
    return "system"


def _add_numeric_field(point, name, value):
    if value is None:
        return point
    try:
        return point.field(name, float(value))
    except (TypeError, ValueError):
        return point


def _add_string_field(point, name, value):
    if value is None:
        return point
    return point.field(name, str(value))


def _add_alert_fields(point, alert):
    alert_type = alert[0]

    if alert_type in ("BATTERY_LOW", "BATTERY_ALERT") and len(alert) >= 4:
        point = _add_numeric_field(point, "value", alert[2])
        point = _add_numeric_field(point, "threshold", alert[3])
    elif alert_type in ("RSSI_LOW", "RSSI_WEAK", "RSSI_DEGRADED", "RSSI_CRITICAL", "RSSI_RECOVER", "RSSI_RECOVERY") and len(alert) >= 3:
        point = _add_numeric_field(point, "value", alert[2])
    elif alert_type in ("PROBE_MISSING", "OUTDOOR_MISSING") and len(alert) >= 3:
        point = _add_numeric_field(point, "age", alert[2])
    elif alert_type in ("FAN_RO1_NO_FEEDBACK", "FAN_RELAY_NO_FEEDBACK") and len(alert) >= 3:
        point = _add_numeric_field(point, "duration", alert[2])
    elif alert_type in ("FAN_DI1_CONTACTOR_FAULT", "FAN_DO1_CONTACTOR_FAULT") and len(alert) >= 5:
        point = _add_numeric_field(point, "duration", alert[2])
        point = _add_string_field(point, "status", alert[3])
        point = _add_numeric_field(point, "age", alert[4])
    elif alert_type.startswith("HARDWARE_FAILSAFE") and len(alert) >= 4:
        point = _add_string_field(point, "reason", alert[1])
        point = _add_numeric_field(point, "ts_diff", alert[2])
        point = _add_numeric_field(point, "threshold", alert[3])

    return point


def build_system_alert_point(alert, message):
    alert_type = alert[0]
    active = is_alert_active(alert_type)
    severity = get_alert_severity(alert_type)
    group = get_alert_group(alert_type)
    device = get_alert_device(alert)

    point = (
        Point("system_alert")
        .tag("alert_type", alert_type)
        .tag("device", device)
        .tag("group", group)
        .tag("severity", severity)
        .field("active", active)
        .field("message", message)
    )

    return _add_alert_fields(point, alert)


def write_system_alert(alert, message):
    try:
        client = get_influxdb_client()
        write_api = client.write_api(write_options=SYNCHRONOUS)
        write_api.write(
            bucket=Config.INFLUX_BUCKET,
            org=Config.INFLUX_ORG,
            record=build_system_alert_point(alert, message),
        )
    except Exception as e:
        logger.error("System alert could not be written to InfluxDB: %s", e, exc_info=True)
