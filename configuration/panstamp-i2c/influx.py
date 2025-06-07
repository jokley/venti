import os
import logging
from influxdb_client import InfluxDBClient, WritePrecision

logger = logging.getLogger("influx")

url = "http://172.16.238.16:8086"
token = os.getenv("DOCKER_INFLUXDB_INIT_ADMIN_TOKEN")
org = os.getenv("DOCKER_INFLUXDB_INIT_ORG")
bucket = os.getenv("DOCKER_INFLUXDB_INIT_BUCKET")

# Create a single client and write_api at module load
client = InfluxDBClient(url=url, token=token, org=org)
write_api = client.write_api()

def write_to_influx(line_protocol: str):
    try:
        write_api.write(
            bucket=bucket,
            org=org,
            record=line_protocol,
            write_precision=WritePrecision.S,
        )
        logger.info("[influx] ✅ Data written to InfluxDB")
    except Exception as e:
        logger.error(f"[influx] ❌ Failed to write to InfluxDB: {e}")

def close_influx():
    write_api.close()
    client.close()
