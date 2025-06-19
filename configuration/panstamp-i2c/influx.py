import os
import logging
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

logger = logging.getLogger("influx")

url = "http://172.16.238.16:8086"
token = os.getenv("DOCKER_INFLUXDB_INIT_ADMIN_TOKEN")
org = os.getenv("DOCKER_INFLUXDB_INIT_ORG")
bucket = os.getenv("DOCKER_INFLUXDB_INIT_BUCKET")

client = InfluxDBClient(url=url, token=token, org=org)
write_api = client.write_api(write_options=SYNCHRONOUS)

def write_combined_point(
    node_name: str,
    tmp: float,
    hum: float,
    trockenmasse: float,
    sdef: float,
    battery: float,
    rssi: float,
    timestamp_s: int,
):
    try:
        point = (
            Point("device_frmpayload_data")
            .tag("device_name", node_name)
            .field("temperature", tmp)
            .field("humidity", hum)
            .field("trockenmasse", trockenmasse)
            .field("sdef", sdef)
            .field("battery", battery)
            .field("rssi", rssi)
            .time(timestamp_s, WritePrecision.S)
        )
        write_api.write(bucket=bucket, org=org, record=point)
        logger.info(f"[influx] ✅ Wrote combined point for {node_name}")
    except Exception as e:
        logger.error(f"[influx] ❌ Failed to write point: {e}")

def close_influx():
    write_api.close()
    client.close()
