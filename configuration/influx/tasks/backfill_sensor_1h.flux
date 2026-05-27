sensor_measurements = [
  "device_frmpayload_data_temperature",
  "device_frmpayload_data_humidity",
  "device_frmpayload_data_trockenmasse",
  "device_frmpayload_data_sdef",
]

base =
  from(bucket: "__SOURCE_BUCKET__")
    |> range(start: time(v: "__BACKFILL_START__"), stop: time(v: "__BACKFILL_STOP__"))
    |> filter(fn: (r) => contains(value: r._measurement, set: sensor_measurements))

mean =
  base
    |> aggregateWindow(every: 1h, fn: mean, createEmpty: false)
    |> set(key: "agg", value: "mean")

min =
  base
    |> aggregateWindow(every: 1h, fn: min, createEmpty: false)
    |> set(key: "agg", value: "min")

max =
  base
    |> aggregateWindow(every: 1h, fn: max, createEmpty: false)
    |> set(key: "agg", value: "max")

union(tables: [mean, min, max])
  |> to(bucket: "__BUCKET_1H__", tagColumns: ["device_name", "agg"])
