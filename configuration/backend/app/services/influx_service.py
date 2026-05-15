from ..db.influx_client import get_influxdb_client
from datetime import datetime
import json

VENTI_PARAM_DEFAULTS = {
    "sdef_on": 4.0,
    "sdef_min_offset": 2.0,
    "sdef_hys": 1.0,
    "uschutz_on": 35.0,
    "uschutz_hys": 2.5,
    "ts_hys": 0.4,
    "intervall_on": 95.0,
    "intervall_time": 12.0,
    "intervall_duration": 12.0,
    "notifications_enabled": True,
    "self_learning_enabled": False,
    "efficiency_window_hours": 2.0,
    "base_min_efficiency_threshold": 0.25,
    "good_drying_level": 0.35,
    "efficiency_learning_up": 1.01,
    "efficiency_learning_down": 0.99,
    "ts_weight": 0.30,
}

VENTI_PARAM_SCALES = {
    "sdef_on": 10,
    "sdef_min_offset": 10,
    "sdef_hys": 10,
    "uschutz_on": 10,
    "uschutz_hys": 10,
    "ts_hys": 10,
    "intervall_on": 10,
    "intervall_time": 10,
    "intervall_duration": 10,
    "efficiency_window_hours": 10,
    "base_min_efficiency_threshold": 100,
    "good_drying_level": 100,
    "efficiency_learning_up": 100,
    "efficiency_learning_down": 100,
    "ts_weight": 100,
}

VENTI_PARAM_BOOL_FIELDS = {"self_learning_enabled", "notifications_enabled"}

# =============================================================================
# 🔥 HEIZUNG – influx_service.py Ergänzungen
# =============================================================================
# Diese Funktionen und Konstanten in influx_service.py einfügen,
# analog zu den bestehenden venti_* Funktionen.
# =============================================================================

from collections import namedtuple


# -----------------------------------------------------------------------------
# 📐 DEFAULTS & SCALES
# -----------------------------------------------------------------------------

HEIZUNG_PARAM_DEFAULTS = {
    "heizung_enabled": False,
    "heizung_nachlauf": 20,         # Minuten, ganzzahlig, keine Skalierung
    # Zukunft auto_sdef:
    # "heizung_sdef_on":  8.0,      # g/kg – Heizung EIN wenn SDef < dieser Wert
    # "heizung_sdef_off": 10.0,     # g/kg – Heizung AUS wenn SDef > dieser Wert
    # Zukunft auto_time:
    # "heizung_time_from": "06:00",
    # "heizung_time_to":   "18:00",
}

HEIZUNG_PARAM_BOOL_FIELDS = {
    "heizung_enabled",
}

# Nur Felder die einen Scale brauchen – nachlauf ist nicht dabei
HEIZUNG_PARAM_SCALES = {
    "heizung_nachlauf": 10,
    # Zukunft auto_sdef:
    # "heizung_sdef_on":  10,
    # "heizung_sdef_off": 10,
}


# -----------------------------------------------------------------------------
# 📦 get_heizung_control_values()
# Liest letzten Eintrag aus Measurement "heizung"
# Gibt zurück: startTime, mode, heizung_dauer (in Stunden, float)
# -----------------------------------------------------------------------------

def get_heizung_control_values():
    client = get_influxdb_client()
    query = '''
        from(bucket: "jokley_bucket")
            |> range(start: -1y)
            |> filter(fn: (r) => r["_measurement"] == "heizung")
            |> last()
    '''
    result = client.query_api().query(query=query)

    startTime = None
    mode = None
    heizung_dauer = 0.0

    for table in result:
        for r in table.records:
            field = r.get_field()
            value = r.get_value()
            if field == "mode":
                startTime = r.get_time()
                mode = value
            elif field == "heizung_dauer":
                heizung_dauer = float(value) / 10.0

    client.close()

    if mode is None:
        mode = "off"

    Heizung = namedtuple("Heizung", ["startTime", "mode", "heizung_dauer"])
    return Heizung(startTime, mode, heizung_dauer)


# -----------------------------------------------------------------------------
# 📦 get_heizung_param_values()
# Rohdaten aus Measurement "heizung_param"
# -----------------------------------------------------------------------------

def get_heizung_param_values():
    client = get_influxdb_client()
    query = '''
        from(bucket: "jokley_bucket")
            |> range(start: 1970-01-01T00:00:00Z)
            |> filter(fn: (r) => r["_measurement"] == "heizung_param")
            |> last()
    '''
    result = client.query_api().query(query=query)

    values = {}
    for table in result:
        for r in table.records:
            values[r.get_field()] = (r.get_time(), r.get_value())

    client.close()
    return [values]


# -----------------------------------------------------------------------------
# 📦 get_heizung_param_actual_values()
# Aufbereitetes Dict – fehlende Felder nutzen DEFAULTS.
#
# nachlauf wird direkt als int gelesen, keine Division.
# Nur Felder in HEIZUNG_PARAM_SCALES werden skaliert (aktuell keine).
# -----------------------------------------------------------------------------

def get_heizung_param_actual_values():
    raw = get_heizung_param_values()[0]
    params = dict(HEIZUNG_PARAM_DEFAULTS)

    for key, record in raw.items():
        if key not in params:
            continue

        value = record[1]

        if key in HEIZUNG_PARAM_BOOL_FIELDS:
            params[key] = bool(value)
            continue

        scale = HEIZUNG_PARAM_SCALES.get(key, 1)  # default scale 1 = kein Umbau
        if scale == 1:
            params[key] = int(value)
        else:
            params[key] = float(value) / scale

    return params


def _hours_to_flux_duration(hours):
    seconds = max(0, int(round(float(hours) * 3600)))
    return f"{seconds}s"

from collections import namedtuple

def get_venti_control_values():
    client = get_influxdb_client()

    query = '''
        from(bucket: "jokley_bucket")
            |> range(start: -1y)
            |> filter(fn: (r) => r["_measurement"] == "venti")
            |> last()
    '''

    result = client.query_api().query(query=query)

    startTime = None
    mode = None
    stockaufbau = None
    trockenmasse = None

    for table in result:
        for r in table.records:

            field = r.get_field()
            value = r.get_value()

            if field == "mode":
                startTime = r.get_time()
                mode = value

            elif field == "stockaufbau":
                stockaufbau = value

            elif field == "trockenmasse":
                trockenmasse = float(value) / 10.0   # ✅ ONLY HERE

    client.close()

    Venti = namedtuple("Venti", ["startTime", "mode", "stockaufbau", "trockenmasse"])

    return Venti(startTime, mode, stockaufbau, trockenmasse)


def get_last_controller_state():
    client = get_influxdb_client()
    query = '''
    from(bucket: "jokley_bucket")
      |> range(start: -30d)
      |> filter(fn: (r) => r["_measurement"] == "venti_state")
      |> last()
    '''

    try:
        result = client.query_api().query(query=query)

        state_data = {
            "started_at": None,
            "state": None,
            "command": None,
            "mode": None,
            "details": None,
        }

        for table in result:
            for record in table.records:
                field_name = record.get_field()
                field_value = record.get_value()

                if state_data["started_at"] is None:
                    state_data["started_at"] = record.get_time().timestamp()

                if field_name == "details_json" and field_value:
                    try:
                        state_data["details"] = json.loads(field_value)
                    except Exception:
                        state_data["details"] = {"raw": field_value}
                elif field_name in ("state", "command", "mode"):
                    state_data[field_name] = field_value

        if state_data["state"] is None:
            return None

        return state_data
    finally:
        client.close()


def get_last_heizung_controller_state():
    client = get_influxdb_client()
    query = '''
    from(bucket: "jokley_bucket")
      |> range(start: -30d)
      |> filter(fn: (r) => r["_measurement"] == "heizung_state")
      |> last()
    '''

    try:
        result = client.query_api().query(query=query)

        state_data = {
            "started_at": None,
            "state": None,
            "command": None,
            "mode": None,
            "details": None,
        }

        for table in result:
            for record in table.records:
                field_name = record.get_field()
                field_value = record.get_value()

                if state_data["started_at"] is None:
                    state_data["started_at"] = record.get_time().timestamp()

                if field_name == "details_json" and field_value:
                    try:
                        state_data["details"] = json.loads(field_value)
                    except Exception:
                        state_data["details"] = {"raw": field_value}
                elif field_name in ("state", "command", "mode"):
                    state_data[field_name] = field_value

        if state_data["state"] is None:
            return None

        return state_data
    finally:
        client.close()

def get_venti_control_param_values():
    client = get_influxdb_client()
    query = ''' from(bucket: "jokley_bucket")
                |> range(start: 1970-01-01T00:00:00Z)
                |> filter(fn: (r) => r["_measurement"] == "venti_param")
                |> last()
            '''
    result = client.query_api().query(query=query)

    values = {}
    for table in result:
        for r in table.records:
            values[r.get_field()] = (r.get_time(), r.get_value())

    client.close()
    return [values]


def get_venti_control_param_actual_values():
    raw = get_venti_control_param_values()[0]
    params = dict(VENTI_PARAM_DEFAULTS)

    for key, record in raw.items():
        if key not in params:
            continue

        value = record[1]

        if key in VENTI_PARAM_BOOL_FIELDS:
            params[key] = bool(value)
            continue

        scale = VENTI_PARAM_SCALES.get(key, 1)
        params[key] = float(value) / scale

    return params

def get_outdoor_values():
    client = get_influxdb_client()

    query = '''
    outdoor = from(bucket: "jokley_bucket")
      |> range(start: -1h)
      |> filter(fn: (r) => r["device_name"] =~ /^outdoor/)
      |> filter(fn: (r) =>
          r["_measurement"] == "device_frmpayload_data_sdef" or
          r["_measurement"] == "device_frmpayload_data_temperature" or
          r["_measurement"] == "device_frmpayload_data_humidity" or
          r["_measurement"] == "device_frmpayload_data_trockenmasse"
      )
      |> filter(fn: (r) => r._value <= 150 and r._value >= -150)
      |> last()
      |> pivot(rowKey: ["device_name"], columnKey: ["_measurement"], valueColumn: "_value")

    best = outdoor
      |> sort(columns: ["device_frmpayload_data_sdef"], desc: true)
      |> limit(n: 1)

    best
    '''

    result = client.query_api().query(query=query)

    values = {}

    for table in result:
        for r in table.records:
            values = {
                "device": r.values.get("device_name"),
                "humidityOut": r.values.get("device_frmpayload_data_humidity"),
                "sDefOut": r.values.get("device_frmpayload_data_sdef"),
                "temperatureOut": r.values.get("device_frmpayload_data_temperature"),
                "trockenMasseOut": r.values.get("device_frmpayload_data_trockenmasse"),
            }

    client.close()

    return [values] if values else []

def get_min_max_values():
    client = get_influxdb_client()
    query = '''
        tmin = from(bucket: "jokley_bucket")
            |> range(start: -1h)
            |> filter(fn: (r) => r["device_name"] == "probe01" or r["device_name"] == "probe02")
            |> filter(fn: (r) =>  r["_measurement"] == "device_frmpayload_data_temperature" or r["_measurement"] == "device_frmpayload_data_humidity"  or r["_measurement"] == "device_frmpayload_data_trockenmasse" or r["_measurement"] == "device_frmpayload_data_sdef" )
            |> filter(fn: (r) => r._value <= 150 and r._value >= -150)
            |> last()
            |> group(columns: ["_measurement"])
            |> min()

        tmax = from(bucket: "jokley_bucket")
            |> range(start: -1h)
            |> filter(fn: (r) => r["device_name"] == "probe01" or r["device_name"] == "probe02")
            |> filter(fn: (r) =>  r["_measurement"] == "device_frmpayload_data_temperature" or r["_measurement"] == "device_frmpayload_data_humidity"  or r["_measurement"] == "device_frmpayload_data_trockenmasse" or r["_measurement"] == "device_frmpayload_data_sdef" )
            |> filter(fn: (r) => r._value <= 150 and r._value >= -150)
            |> last()
            |> group(columns: ["_measurement"])
            |> max()

        union(tables: [tmin, tmax])
            |> sort(columns: ["_measurement", "_value"])
    '''
    result = client.query_api().query(query=query)

    records = []
    for table in result:
        for r in table.records:
            records.append(r.get_value())

    names = ['humidityMin','humidityMax','sDefMin','sDefMax','temperatureMin','temperatureMax','trockenMasseMin','trockenMasseMax']
    values = [dict(zip(names, records))]
    client.close()
    return values

def get_venti_lastTimeOn():
    client = get_influxdb_client()
    query = '''
        on = from(bucket: "jokley_bucket")
            |> range(start: -1y)
            |> filter(fn: (r) => r["device_name"] == "fan")
            |> filter(fn: (r) => r["_measurement"] == "device_frmpayload_data_RO1_status")
            |> filter(fn: (r) => r["_value"] == "ON")
            |> last()

        off = from(bucket: "jokley_bucket")
            |> range(start: -1y)
            |> filter(fn: (r) => r["device_name"] == "fan")
            |> filter(fn: (r) => r["_measurement"] == "device_frmpayload_data_RO1_status")
            |> filter(fn: (r) => r["_value"] == "OFF")
            |> last()

        union(tables: [on, off])
            |> sort(columns: ["_measurement", "_value"])
    '''
    result = client.query_api().query(query=query)
    times = [r.get_time() for table in result for r in table.records]
    names = ['lastTimeOff','lastTimeOn']
    client.close()
    return [dict(zip(names, times))]

def get_battery_data():
    client = get_influxdb_client()
    query = '''
    from(bucket: "jokley_bucket")
    |> range(start: -1h)
    |> filter(fn: (r) => r["_measurement"] == "device_frmpayload_data_battery")
    |> filter(fn: (r) => r["device_name"] == "outdoor00" or r["device_name"] == "fan" or r["device_name"] == "probe01" or r["device_name"] == "probe02")
    |> last()
    '''

    result = client.query_api().query(query=query)

    battery = {}

    for table in result:
        for record in table.records:
            device = record["device_name"]
            battery[device] = record.get_value()

    return battery


def get_rssi_data():
    client = get_influxdb_client()
    query = '''
    from(bucket: "jokley_bucket")
      |> range(start: -2h)
      |> filter(fn: (r) => r["_field"] == "rssi")
      |> filter(fn: (r) => r["device_name"] == "outdoor00" or r["device_name"] == "fan" or r["device_name"] == "probe01" or r["device_name"] == "probe02")
      |> last()
    '''

    result = client.query_api().query(query=query)

    rssi = {}

    for table in result:
        for record in table.records:
            device = record["device_name"]
            rssi[device] = record.get_value()

    return rssi

def get_sensor_age():
    client = get_influxdb_client()
    query = '''
    from(bucket: "jokley_bucket")
            |> range(start: -6h)
            |> filter(fn: (r) =>
                r["device_name"] == "outdoor00" or
                r["device_name"] == "probe01" or
                r["device_name"] == "probe02"
            )
            |> filter(fn: (r) =>
                r["_measurement"] == "device_frmpayload_data_temperature"
            )
            |> group(columns: ["device_name"])
            |> last()
    '''

    result = client.query_api().query(query=query)

    now = datetime.utcnow().timestamp()
    age = {}

    for table in result:
        for record in table.records:
            device = record["device_name"]
            ts = record.get_time().timestamp()
            age[device] = int(now - ts)

    return age

def get_fan_runtime_today():
    client = get_influxdb_client()

    query = '''
    import "date"

    from(bucket: "jokley_bucket")
      |> range(start: date.truncate(t: now(), unit: 1d))
      |> filter(fn: (r) =>
          r["_measurement"] == "device_frmpayload_data_RO1_status" and
          r["device_name"] == "fan"
      )
      |> elapsed(unit: 1s)
      |> map(fn: (r) => ({
          r with elapsedHours: float(v: r.elapsed) / 3600.0
      }))
      |> filter(fn: (r) => r["_value"] == "ON")
      |> sum(column: "elapsedHours")
      |> map(fn: (r) => ({ r with _value: r.elapsedHours }))
    '''

    result = client.query_api().query(query=query)

    for table in result:
        for record in table.records:
            return round(record.get_value(), 2)

    return 0


def get_last_auto_start():
    client = get_influxdb_client()

    query = '''
    from(bucket: "jokley_bucket")
      |> range(start: -7d)
      |> filter(fn: (r) =>
          r["_measurement"] == "venti" and
          r["_field"] == "mode" and
          r["_value"] == "auto"
      )
      |> last()
    '''

    result = client.query_api().query(query=query)

    for table in result:
        for record in table.records:
            return record.get_time()

    return None

def get_last_auto_start():
    client = get_influxdb_client()

    query = '''
    from(bucket: "jokley_bucket")
      |> range(start: -7d)
      |> filter(fn: (r) =>
          r["_measurement"] == "venti" and
          r["_field"] == "mode" and
          r["_value"] == "auto"
      )
      |> last()
    '''

    result = client.query_api().query(query=query)

    for table in result:
        for record in table.records:
            return record.get_time()

    return None

def get_fan_runtime_since(start_time):
    client = get_influxdb_client()

    if start_time is None:
        return 0

    start_iso = start_time.isoformat()

    query = f'''
    from(bucket: "jokley_bucket")
      |> range(start: {start_iso})
      |> filter(fn: (r) =>
          r["_measurement"] == "device_frmpayload_data_RO1_status" and
          r["device_name"] == "fan"
      )
      |> elapsed(unit: 1s)
      |> filter(fn: (r) => exists r.elapsed)
      |> filter(fn: (r) => r["_value"] == "ON")
      |> map(fn: (r) => ({{
          r with _value: float(v: r.elapsed) / 3600.0
      }}))
      |> sum()
    '''

    result = client.query_api().query(query=query)

    for table in result:
        for record in table.records:
            return round(record.get_value(), 2)

    return 0

def get_measurement_change_over_hours(measurement, device_filter, hours, use_min=True):
    """
    Get the change in a measurement over the last 'hours' hours.
    Returns current_value - past_value
    """
    client = get_influxdb_client()
    start_offset = _hours_to_flux_duration(hours + 1)
    stop_offset = _hours_to_flux_duration(hours)
    
    # Get current value
    query_current = f'''
    from(bucket: "jokley_bucket")
    |> range(start: -1h)
    |> filter(fn: (r) => {device_filter})
    |> filter(fn: (r) => r["_measurement"] == "{measurement}")
    |> filter(fn: (r) => r._value <= 150 and r._value >= -150)
    |> last()
    '''
    
    if use_min:
        query_current += '|> group(columns: ["_measurement"]) |> min()'
    else:
        query_current += '|> group(columns: ["_measurement"]) |> max()'
    
    # Get past value
    query_past = f'''
    from(bucket: "jokley_bucket")
    |> range(start: -{start_offset}, stop: -{stop_offset})
    |> filter(fn: (r) => {device_filter})
    |> filter(fn: (r) => r["_measurement"] == "{measurement}")
    |> filter(fn: (r) => r._value <= 150 and r._value >= -150)
    |> last()
    '''
    
    if use_min:
        query_past += '|> group(columns: ["_measurement"]) |> min()'
    else:
        query_past += '|> group(columns: ["_measurement"]) |> max()'
    
    try:
        result_current = client.query_api().query(query=query_current)
        result_past = client.query_api().query(query=query_past)
        
        current_value = None
        past_value = None
        
        for table in result_current:
            for r in table.records:
                current_value = r.get_value()
                break
        
        for table in result_past:
            for r in table.records:
                past_value = r.get_value()
                break
        
        if current_value is not None and past_value is not None:
            return current_value - past_value
        else:
            return 0.0
    except Exception as e:
        print(f"Error getting change for {measurement}: {e}")
        return 0.0
    finally:
        client.close()

def get_temperature_change_over_hours(hours):
    device_filter = 'r["device_name"] == "probe01" or r["device_name"] == "probe02"'
    return get_measurement_change_over_hours("device_frmpayload_data_temperature", device_filter, hours, use_min=True)

def get_sdef_change_over_hours(hours):
    device_filter = 'r["device_name"] == "probe01" or r["device_name"] == "probe02"'
    return get_measurement_change_over_hours("device_frmpayload_data_sdef", device_filter, hours, use_min=True)

def get_ts_change_over_hours(hours):
    device_filter = 'r["device_name"] == "probe01" or r["device_name"] == "probe02"'
    return get_measurement_change_over_hours("device_frmpayload_data_trockenmasse", device_filter, hours, use_min=True)

def get_outdoor_temperature_change_over_hours(hours):
    device_filter = 'r["device_name"] == "outdoor00"'
    return get_measurement_change_over_hours("device_frmpayload_data_temperature", device_filter, hours, use_min=False)


def get_measurement_value_hours_ago(measurement, device_filter, hours, use_min=True):
    client = get_influxdb_client()
    start_offset = _hours_to_flux_duration(hours + 1)
    stop_offset = _hours_to_flux_duration(hours)

    query = f'''
    from(bucket: "jokley_bucket")
    |> range(start: -{start_offset}, stop: -{stop_offset})
    |> filter(fn: (r) => {device_filter})
    |> filter(fn: (r) => r["_measurement"] == "{measurement}")
    |> filter(fn: (r) => r._value <= 150 and r._value >= -150)
    |> last()
    '''

    if use_min:
        query += '|> group(columns: ["_measurement"]) |> min()'
    else:
        query += '|> group(columns: ["_measurement"]) |> max()'

    try:
        result = client.query_api().query(query=query)

        for table in result:
            for record in table.records:
                return record.get_value()

        return None
    finally:
        client.close()


def get_2h_values(hours=2):
    device_filter = 'r["device_name"] == "probe01" or r["device_name"] == "probe02"'
    return {
        "sDef_2h_ago": get_measurement_value_hours_ago(
            "device_frmpayload_data_sdef",
            device_filter,
            hours,
            use_min=True,
        ),
        "ts_2h_ago": get_measurement_value_hours_ago(
            "device_frmpayload_data_trockenmasse",
            device_filter,
            hours,
            use_min=True,
        ),
        "window_seconds": int(hours * 3600),
    }
