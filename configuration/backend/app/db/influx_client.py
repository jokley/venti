from influxdb_client import InfluxDBClient
from ..config import Config

def get_influxdb_client():
    return InfluxDBClient(
        url=Config.INFLUX_URL,
        token=Config.INFLUX_TOKEN,
        org=Config.INFLUX_ORG
    )