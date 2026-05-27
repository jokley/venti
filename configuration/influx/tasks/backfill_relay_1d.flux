relay_runtime_measurements = [
  "device_frmpayload_data_RO1_runtime_hours",
  "device_frmpayload_data_RO2_runtime_hours",
]

from(bucket: "__BUCKET_1H__")
  |> range(start: time(v: "__BACKFILL_START__"), stop: time(v: "__BACKFILL_STOP__"))
  |> filter(fn: (r) => r.device_name == "fan")
  |> filter(fn: (r) => contains(value: r._measurement, set: relay_runtime_measurements))
  |> filter(fn: (r) => r.agg == "sum")
  |> aggregateWindow(every: 1d, fn: sum, createEmpty: false)
  |> set(key: "agg", value: "sum")
  |> to(bucket: "__BUCKET_1D__", tagColumns: ["device_name", "relay", "name", "agg"])
