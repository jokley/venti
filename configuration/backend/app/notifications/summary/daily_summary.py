def build_daily_summary(influx_data, alert_history, runtime_stats):

    return {
        "fan_runtime": runtime_stats.get("fan_runtime"),
        "stock_cycles": runtime_stats.get("stock_cycles"),
        "interval_cycles": runtime_stats.get("interval_cycles"),

        "battery_min": influx_data.get("battery_min"),
        "rssi_avg": influx_data.get("rssi_avg"),

        "alerts": {
            "battery": alert_history.get("battery", 0),
            "rssi": alert_history.get("rssi", 0),
        }
    }