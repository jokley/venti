import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'hi')
    MQTT_BROKER_URL = os.getenv('MQTT_BROKER_URL', '172.16.238.15')
    MQTT_BROKER_PORT = int(os.getenv('MQTT_BROKER_PORT', 1883))
    MQTT_KEEPALIVE = int(os.getenv('MQTT_KEEPALIVE', 20))

    INFLUX_URL = os.getenv('INFLUX_URL', 'http://172.16.238.16:8086')
    INFLUX_TOKEN = os.getenv('DOCKER_INFLUXDB_INIT_ADMIN_TOKEN')
    INFLUX_ORG = os.getenv('DOCKER_INFLUXDB_INIT_ORG')
    INFLUX_BUCKET = os.getenv('INFLUX_BUCKET', 'jokley_bucket')

    PANSTAMP = os.getenv("PANSTAMP", "false").lower() == "true"
    APPLICATION_ID = os.getenv("APPLICATION_ID")
    DEVICE_ID = os.getenv("DEVICE_ID")

    NTFY_BASE_URL = os.getenv("NTFY_BASE_URL", "https://ntfy.sh")
    NTFY_TOPIC = os.getenv("NTFY_TOPIC")
    URL_IOS_STORE = "https://apps.apple.com/us/app/ntfy/id1625396347"
    URL_ANDROID_STORE = "https://play.google.com/store/apps/details?id=io.heckel.ntfy"
