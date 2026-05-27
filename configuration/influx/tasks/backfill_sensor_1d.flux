sensor_measurements = [
  "device_frmpayload_data_temperature",
  "device_frmpayload_data_humidity",
  "device_frmpayload_data_trockenmasse",
  "device_frmpayload_data_sdef",
]

base =
  from(bucket: "__BUCKET_1H__")
    |> range(start: time(v: "__BACKFILL_START__"), stop: time(v: "__BACKFILL_STOP__"))
    |> filter(fn: (r) => contains(value: r._measurement, set: sensor_measurements))

mean =
  base
    |> filter(fn: (r) => r.agg == "mean")
    |> aggregateWindow(every: 1d, fn: mean, createEmpty: false)
    |> set(key: "agg", value: "mean")

min =
  base
    |> filter(fn: (r) => r.agg == "min")
    |> aggregateWindow(every: 1d, fn: min, createEmpty: false)
    |> set(key: "agg", value: "min")

max =
  base
    |> filter(fn: (r) => r.agg == "max")
    |> aggregateWindow(every: 1d, fn: max, createEmpty: false)
    |> set(key: "agg", value: "max")

union(tables: [mean, min, max])
  |> to(bucket: "__BUCKET_1D__", tagColumns: ["device_name", "agg"])
