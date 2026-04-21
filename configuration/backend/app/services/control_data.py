from .influx_service import (
    get_venti_control_values,
    get_min_max_values,
    get_outdoor_values,
    get_venti_lastTimeOn,
    get_venti_control_param_values,
    get_battery_data,
    get_rssi_data,
    get_sensor_age,
    get_fan_runtime_today,
    get_last_auto_start,
    get_fan_runtime_since,
    get_temperature_change_over_hours,
    get_sdef_change_over_hours,
    get_ts_change_over_hours,
    get_outdoor_temperature_change_over_hours
)

from datetime import timedelta, timezone
from app.utils.time_utils import (
    get_timestamp_now_epoche,
    get_timestamp_now_offset
)

def battery_mv_to_percent(mv):
    if mv is None:
        return None

    try:
        mv = float(mv)

        MIN_V = 3500
        MAX_V = 4200

        pct = (mv - MIN_V) / (MAX_V - MIN_V) * 100

        # clamp 0–100
        pct = max(0, min(100, pct))

        return round(pct, 1)

    except:
        return None


def build_control_data():

    dataVenti = get_venti_control_values()

    startTime = dataVenti[0]['mode'][0]
    mode = dataVenti[0]['mode'][1]

    tsSoll = dataVenti[0]['trockenMasseSoll'][1]
    stock = int(dataVenti[0]['stockaufbau'][1]) * 3600

    data = get_min_max_values()
    dataOut = get_outdoor_values()
    dataLastTime = get_venti_lastTimeOn()
    params = get_venti_control_param_values()
    
    raw_battery = get_battery_data()
    battery = {
        device: battery_mv_to_percent(value)
        for device, value in raw_battery.items()
}
    rssi = get_rssi_data()
    sensor_age = get_sensor_age()
    fan_runtime = get_fan_runtime_today()
    auto_start = get_last_auto_start()
    fan_runtime_auto = get_fan_runtime_since(auto_start)

    # Duration-based changes
    temp_change_2h = get_temperature_change_over_hours(2)
    sdef_change_2h = get_sdef_change_over_hours(2)
    ts_change_2h = get_ts_change_over_hours(2)
    outdoor_temp_change_2h = get_outdoor_temperature_change_over_hours(2)

    # =========================
    # ⏱ TIME
    # =========================
    DST = get_timestamp_now_offset()
    now = get_timestamp_now_epoche()

    startTimeStock = (
        startTime + timedelta(seconds=DST)
    ).replace(tzinfo=timezone.utc).timestamp()

    lastOn = (
        dataLastTime[0]['lastTimeOn'] + timedelta(seconds=DST)
    ).replace(tzinfo=timezone.utc).timestamp()

    lastOff = (
        dataLastTime[0]['lastTimeOff'] + timedelta(seconds=DST)
    ).replace(tzinfo=timezone.utc).timestamp()

    # =========================
    # 📦 CONTEXT DATA
    # =========================
    return {
        "mode": mode,

        "tempMax": data[0]['temperatureMax'],

        "sDefOut": dataOut[0]['sDefOut'],
        "sDefMin": data[0]['sDefMin'],

        "tsMin": data[0]['trockenMasseMin'],
        "tsSoll": tsSoll,

        "stock": stock,
        "remainingTimeStock": int(now - startTimeStock),

        "humMax": data[0]['humidityMax'],

        "remainingTimeInterval": int(now - lastOn),
        "remainingTimeIntervalOn": int(now - lastOff),
        "remainingTimeIntervalDiff": int(lastOn - lastOff),

        "now": now,

        # =========================
        # ⚙️ PARAMETERS
        # =========================
        "sdef_on": params[0]['sdef_on'][1] / 10,
        "sdef_hys_half": (params[0]['sdef_hys'][1] / 10) / 2,
        "sdefMinThreshold": data[0]['sDefMin'] + (params[0]['sdef_min_offset'][1] / 10),

        "ts_hys_half": (params[0]['ts_hys'][1] / 10) / 2,

        "intervall_on": params[0]['intervall_on'][1] / 10,
        "intervall_time": (params[0]['intervall_time'][1] / 10) * 3600,
        "intervall_duration": (params[0]['intervall_duration'][1] / 10) * 60,

        "uschutz_on": params[0]['uschutz_on'][1] / 10,
        "uschutz_hys": params[0]['uschutz_hys'][1] / 10,


        # =========================
        # 🧠 SYSTEM HEALTH (NEW LAYER)
        # =========================
        "battery": battery,
        "rssi": rssi,
        "sensor_age": sensor_age,

        # =========================
        # 🧠 FAN Runtime 
        # =========================

        "fan_runtime_today": fan_runtime,
        "fan_runtime_auto": fan_runtime_auto,
        "auto_start": auto_start,

        # =========================
        # 📈 Duration Changes (2 hours)
        # =========================
        "temp_change_2h": temp_change_2h,
        "sdef_change_2h": sdef_change_2h,
        "ts_change_2h": ts_change_2h,
        "outdoor_temp_change_2h": outdoor_temp_change_2h,

    }