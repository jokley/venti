from ..db.influx_client import get_influxdb_client
from datetime import datetime

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
    query = '''from(bucket: "jokley_bucket")
                |> range(start: -1h)
                |> filter(fn: (r) => r["device_name"] == "outdoor00")
                |> filter(fn: (r) =>  r["_measurement"] == "device_frmpayload_data_temperature" or r["_measurement"] == "device_frmpayload_data_humidity"  or r["_measurement"] == "device_frmpayload_data_trockenmasse" or r["_measurement"] == "device_frmpayload_data_sdef" )
                |> filter(fn: (r) => r._value <= 150 and r._value >= -150)
                |> last()
            '''
    result = client.query_api().query(query=query)

    records = []
    for table in result:
        for r in table.records:
            records.append(r.get_value())

    names = ['humidityOut','sDefOut','temperatureOut','trockenMasseOut']
    values = [dict(zip(names, records))]
    client.close()
    return values

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


