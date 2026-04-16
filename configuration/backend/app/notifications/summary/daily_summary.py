from datetime import datetime

def fmt_float(v):
    try:
        return round(float(v), 1)
    except:
        return "-"

def fmt_percent(v):
    return f"{fmt_float(v)}%" if v is not None else "-"

def fmt_temp(v):
    return f"{fmt_float(v)}°C" if v is not None else "-"

def fmt_duration(seconds):
    try:
        if seconds is None:
            return "-"
        seconds = int(seconds)

        if seconds < 3600:
            return f"{round(seconds/60)}min"
        else:
            h = seconds // 3600
            return f"{h}h"
    except:
        return "-"


def safe_min(values):
    vals = [v for v in values.values() if v is not None]
    return min(vals) if vals else None


def safe_max(values):
    vals = [v for v in values.values() if v is not None]
    return max(vals) if vals else None


def format_devices_block(title, data, unit="", convert_seconds_to_minutes=False):
    lines = [title]

    for device, value in data.items():
        if value is None:
            lines.append(f"{device}: -")
            continue

        try:
            value = float(value)

            # convert seconds → minutes if needed
            if convert_seconds_to_minutes:
                value = round(value / 60, 1)
            else:
                value = round(value, 1)

        except:
            pass

        lines.append(f"{device}: {value}{unit}")

    return "\n".join(lines)


def build_daily_summary(ctx):

    # =========================
    # 🔋 SYSTEM DATA (SAFE AGGREGATION)
    # =========================
    # battery_min = safe_min(ctx.battery)
    # battery_max = safe_max(ctx.battery)

    # rssi_min = safe_min(ctx.rssi)
    # rssi_max = safe_max(ctx.rssi)

    # sensor_max_age = safe_max(ctx.sensor_age)

    # =========================
    # 📡 DEVICE BLOCKS
    # =========================
    battery_block = format_devices_block("🔋 Batterie", ctx.battery, "%")
    rssi_block = format_devices_block("📶 RSSI", ctx.rssi, " dBm")
    age_block = format_devices_block( "⏱ Sensor Alter",ctx.sensor_age," min",convert_seconds_to_minutes=True)

    # =========================
    # 🧾 MAIN SUMMARY
    # =========================
    msg = (
        f"📊 Tagesübersicht\n\n"

        f"🌡 Temp max: {fmt_temp(ctx.tempMax)}\n"
        f"💧 Feuchte max: {fmt_percent(ctx.humMax)}\n\n"

        f"🌾 TS min: {fmt_float(ctx.tsMin)}%\n"
        f"🎯 TS target: {fmt_float(ctx.tsSoll)}%\n\n"

        f"🌀 Fan runtime: {fmt_float(ctx.fan_runtime_today)}h\n\n"

        f"{battery_block}\n\n"

        f"{rssi_block}\n\n"

        f"{age_block}\n"
    )

    return msg


def should_send_summary(ctx, state):
    now = ctx.now

    if not now:
        return False

    dt = datetime.fromtimestamp(now)

    # 👉 only after 20:00
    if dt.hour < 20:
        return False

    today = dt.date()

    if state.last_sent_day == today:
        return False

    # 👉 ONLY in AUTO MODE
    if ctx.mode != "auto":
        return False

    state.last_sent_day = today
    return True