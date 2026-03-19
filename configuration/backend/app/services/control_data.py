from .influx_service import (
    get_venti_control_values,
    get_min_max_values,
    get_outdoor_values,
    get_venti_lastTimeOn,
    get_venti_control_param_values
)

from datetime import timedelta, timezone
from app.utils.time_utils import (
    get_timestamp_now_epoche,
    get_timestamp_now_offset
)


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

    # --- time ---
    DST = get_timestamp_now_offset()
    now = get_timestamp_now_epoche()

    startTimeStock = (startTime + timedelta(seconds=DST)).replace(tzinfo=timezone.utc).timestamp()
    lastOn = (dataLastTime[0]['lastTimeOn'] + timedelta(seconds=DST)).replace(tzinfo=timezone.utc).timestamp()
    lastOff = (dataLastTime[0]['lastTimeOff'] + timedelta(seconds=DST)).replace(tzinfo=timezone.utc).timestamp()

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

        # params
        "sdef_on": params[0]['sdef_on'][1] / 10,
        "sdef_hys_half": (params[0]['sdef_hys'][1] / 10) / 2,
        "sdefMinThreshold": data[0]['sDefMin'] + (params[0]['sdef_min_offset'][1] / 10),

        "ts_hys_half": (params[0]['ts_hys'][1] / 10) / 2,

        "intervall_on": params[0]['intervall_on'][1] / 10,
        "intervall_time": (params[0]['intervall_time'][1] / 10) * 3600,
        "intervall_duration": (params[0]['intervall_duration'][1] / 10) * 60,

        "uschutz_on": params[0]['uschutz_on'][1] / 10,
        "uschutz_hys": params[0]['uschutz_hys'][1] / 10,
    }