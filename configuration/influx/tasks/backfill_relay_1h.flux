relay_measurements = [
  "device_frmpayload_data_RO1_status",
  "device_frmpayload_data_RO2_status",
]

from(bucket: "__SOURCE_BUCKET__")
  |> range(start: time(v: "__BACKFILL_START__"), stop: time(v: "__BACKFILL_STOP__"))
  |> filter(fn: (r) => r.device_name == "fan")
  |> filter(fn: (r) => contains(value: r._measurement, set: relay_measurements))
  |> map(fn: (r) => ({
      r with
      _value: if r._value == "ON" then 1.0 else 0.0,
      relay: if r._measurement == "device_frmpayload_data_RO1_status" then "RO1" else "RO2",
      name: if r._measurement == "device_frmpayload_data_RO1_status" then "fan" else "heizung",
  }))
  |> aggregateWindow(every: 1h, fn: mean, createEmpty: false)
  |> map(fn: (r) => ({
      r with
      _measurement:
        if r.relay == "RO1" then "device_frmpayload_data_RO1_runtime_hours"
        else "device_frmpayload_data_RO2_runtime_hours",
      _field: "value",
      _value: r._value,
  }))
  |> set(key: "agg", value: "sum")
  |> to(bucket: "__BUCKET_1H__", tagColumns: ["device_name", "relay", "name", "agg"])
