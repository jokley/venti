from app.notifications.notifier import send_notification

last_state = {}

def process_system_alerts(ctx, decision):

    global last_state

    alerts = []

    # 🔋 Battery low
    if ctx.battery1 is not None and ctx.battery1 < 20:
        alerts.append(("BATTERY_LOW", "🔋 Sonde 1 Batterie niedrig"))

    # ❌ Sensor offline
    if ctx.sensor1_missing:
        alerts.append(("SENSOR_DOWN", "⚠️ Sonde 1 offline"))

    # 🌪 Fan mismatch (VERY IMPORTANT)
    if ctx.fan_feedback != decision.command:
        alerts.append(("FAN_MISMATCH", "⚠️ Lüfter reagiert nicht auf Befehl"))

    # 🌾 Drying finished (nice UX alert)
    if decision.reason == "AUTO_DISABLED":
        alerts.append(("DRYING_DONE", "✅ Trocknung abgeschlossen"))

    # 🚨 send only on change
    for key, message in alerts:

        if not last_state.get(key):
            send_notification(title=key, message=message, priority="high")
            last_state[key] = True

    # reset state if resolved
    for key in list(last_state.keys()):
        still_active = any(a[0] == key for a in alerts)
        if not still_active:
            last_state[key] = False