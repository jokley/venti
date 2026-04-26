from ..db.influx_client import get_influxdb_client
from datetime import datetime
import json

def get_venti_control_values():
    client = get_influxdb_client()
    query = ''' from(bucket: "jokley_bucket")
                    |> range(start: -1y)
                    |> filter(fn: (r) => r["_measurement"] == "venti")
		            |> last()
                '''
    result = client.query_api().query(query=query)

    records = []
    for table in result:
        for r in table.records:
            records.append((r.get_time(), r.get_value()))
    
    names = ['mode', 'stockaufbau', 'trockenMasseSoll']
    values = [dict(zip(names, records))]
    client.close()
    return values


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

def get_venti_control_param_values():
    client = get_influxdb_client()
    query = ''' from(bucket: "jokley_bucket")
                |> range(start: 1970-01-01T00:00:00Z)
                |> filter(fn: (r) => r["_measurement"] == "venti_param")
                |> last()
            '''
    result = client.query_api().query(query=query)

    records = []
    for table in result:
        for r in table.records:
            records.append((r.get_time(), r.get_value()))

    names = [
        'intervall_duration', 'intervall_enable', 'intervall_on', 'intervall_time',
        'sdef_hys', 'sdef_min_offset', 'sdef_on',
        'ts_hys', 'uschutz_hys', 'uschutz_on'
    ]
    values = [dict(zip(names, records))]
    client.close()
    return values

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
    |> range(start: -{hours + 1}h, stop: -{hours}h)
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

    query = f'''
    from(bucket: "jokley_bucket")
    |> range(start: -{hours + 1}h, stop: -{hours}h)
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
