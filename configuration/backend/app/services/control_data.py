from .influx_service import (
    get_venti_control_values,
    get_min_max_values,
    get_outdoor_values,
    get_venti_lastTimeOn,
    get_venti_control_param_actual_values,
    get_battery_data,
    get_rssi_data,
    get_sensor_age,
    get_fan_runtime_today,
    get_last_auto_start,
    get_fan_runtime_since,
    get_2h_values,
    get_heizung_control_values,
    get_heizung_param_actual_values,
)

from datetime import datetime, timedelta, timezone
from app.utils.time_utils import (
    get_timestamp_now_epoche,
    get_timestamp_now_offset
)

from ..controller.venti.control.state_manager import state_manager


def _elapsed_seconds_since(start_time, now_epoch):
    if start_time is None:
        return 999999

    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)

    return max(0, int(now_epoch - start_time.timestamp()))


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

    # =========================
    # 📡 DATA FETCH
    # =========================
    dataVenti = get_venti_control_values()
    dataHeizung = get_heizung_control_values()

    startTime = dataVenti.startTime
    mode = dataVenti.mode
    tsSoll = dataVenti.trockenmasse
    stock = int(dataVenti.stockaufbau) * 3600

    data = get_min_max_values()
    dataOut = get_outdoor_values()
    dataLastTime = get_venti_lastTimeOn()
    params = get_venti_control_param_actual_values()
    heizung_params = get_heizung_param_actual_values()

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
    history_2h = get_2h_values(params["efficiency_window_hours"])

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
    # 🔥 HEIZUNG – Timing
    # =========================
    heizung_mode = dataHeizung.mode
    heizung_dauer = dataHeizung.heizung_dauer * 3600   # h → s
    now_utc = datetime.now(timezone.utc).timestamp()

    # startTime der Heizung – None wenn noch nie gesetzt (Erstinbetriebnahme)
    remainingTimeHeizung = _elapsed_seconds_since(dataHeizung.startTime, now_utc)

    # Nachlauf: wie viele Sekunden seit Heizung abging
    # Quelle: state_manager, wird gesetzt wenn heizung_active EIN→AUS kippt
    heizung_off_since = (
        int(now - state_manager.heizung_off_ts)
        if state_manager.heizung_off_ts is not None
        else 999999   # nie abgegangen → kein Nachlauf aktiv
    )

    # nachlauf in Sekunden (Param ist in Minuten, ganzzahlig)
    heizung_nachlauf_s = heizung_params["heizung_nachlauf"] * 60

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
        "sdef_on": params["sdef_on"],
        "sdef_hys_half": params["sdef_hys"] / 2,
        "sdefMinThreshold": data[0]['sDefMin'] + params["sdef_min_offset"],

        "ts_hys_half": params["ts_hys"] / 2,

        "intervall_on": params["intervall_on"],
        "intervall_time": params["intervall_time"] * 3600,
        "intervall_duration": params["intervall_duration"] * 60,

        "is_fan_on": lastOn > lastOff,
        "fan_runtime_current": int(now - lastOff),

        "uschutz_on": params["uschutz_on"],
        "uschutz_hys": params["uschutz_hys"],

        # =========================
        # 🔥 HEIZUNG
        # =========================
        "heizung_enabled":        heizung_params["heizung_enabled"],
        "heizung_mode":           heizung_mode,
        "heizung_dauer":          heizung_dauer,
        "remainingTimeHeizung":   remainingTimeHeizung,
        "heizung_nachlauf":       heizung_nachlauf_s,
        "heizung_off_since":      heizung_off_since,

        # =========================
        # 🧠 SYSTEM HEALTH
        # =========================
        "battery": battery,
        "rssi": rssi,
        "sensor_age": sensor_age,

        # =========================
        # 🧠 FAN RUNTIME
        # =========================
        "fan_runtime_today": fan_runtime,
        "fan_runtime_auto": fan_runtime_auto,
        "auto_start": auto_start,

        # =========================
        # 🧠 EFFICIENCY ENGINE INPUTS
        # =========================
        "sDef_2h_ago": history_2h["sDef_2h_ago"],
        "ts_2h_ago": history_2h["ts_2h_ago"],
        "efficiency_window": history_2h["window_seconds"],
        "self_learning_enabled": params["self_learning_enabled"],
        "base_min_efficiency_threshold": params["base_min_efficiency_threshold"],
        "good_drying_level": params["good_drying_level"],
        "efficiency_learning_up": params["efficiency_learning_up"],
        "efficiency_learning_down": params["efficiency_learning_down"],
        "ts_weight": params["ts_weight"],
    }
