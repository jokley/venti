# backend/services/venti_service.py
import json as std_json
from flask import json
from ..utils.logger import logger
from ..extensions.extensions import mqtt
from ..db.influx_client import get_influxdb_client
from ..config import Config
from influxdb_client import  Point
from influxdb_client.client.write_api import SYNCHRONOUS


def venti_cmd(cmd: str):
    """
    Sends command to the fan via MQTT (PanStamp or TTN)
    """
    cmd = cmd.lower()
    try:
        if Config.PANSTAMP:
            topic = "relay/control"
            payload = json.dumps({"relay": cmd, "id": 1})
            mqtt.publish(topic, payload)
            logger.info(f"Venti_cmd sent (PanStamp): {cmd}")
        else:
            if not Config.APPLICATION_ID or not Config.DEVICE_ID:
                logger.warning("Venti_cmd: Missing APPLICATION_ID or DEVICE_ID, command skipped")
                return
            data = "AwEA" if cmd == "on" else "AwAA"
            topic = f"application/{Config.APPLICATION_ID}/device/{Config.DEVICE_ID}/command/down"
            payload = json.dumps({
                "devEui": Config.DEVICE_ID,
                "confirmed": True,
                "fPort": 10,
                "data": data
            })
            mqtt.publish(topic, payload)
            logger.info(f"Venti_cmd sent (TTN): {cmd}")
    except Exception as e:
        logger.error(f"Venti_cmd error: {e}")

def venti_auto(cmd, trockenMasse,stockAufbau):
    
    ORG = Config.INFLUX_ORG

    client = get_influxdb_client()

    write_api = client.write_api(write_options=SYNCHRONOUS)

    record = [
	Point("venti").field("mode", cmd).field("trockenmasse", trockenMasse).field("stockaufbau", stockAufbau),
    ]      

    write_api.write(bucket="jokley_bucket", org=ORG, record=record)
    client.close()

def _to_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def venti_auto_param(
    sdef_on,
    sdef_min_offset,
    sdef_hys,
    uschutz_on,
    uschutz_hys,
    ts_hys,
    intervall_on,
    intervall_time,
    intervall_duration,
    notifications_enabled,
    self_learning_enabled,
    efficiency_window_hours,
    base_min_efficiency_threshold,
    good_drying_level,
    efficiency_learning_up,
    efficiency_learning_down,
    ts_weight,
):

    ORG = Config.INFLUX_ORG

    logger.info('****************************************')
    logger.info('Regelparameter geändert:')
    logger.info('SDef on: {}'.format(sdef_on))
    logger.info('SDef MinOffset: {}'.format(sdef_min_offset))
    logger.info('SDef Hys: {}'.format(sdef_hys))
    logger.info('ÜSchutz on: {}'.format(uschutz_on))
    logger.info('ÜSchutz hys: {}'.format(uschutz_hys))
    logger.info('TS Hys: {}'.format(ts_hys))
    logger.info('Intervall on: {}'.format(intervall_on))
    logger.info('Intervall time: {}'.format(intervall_time))
    logger.info('Intervall duration: {}'.format(intervall_duration))
    logger.info('Notifications enabled: {}'.format(notifications_enabled))
    logger.info('Self learning enabled: {}'.format(self_learning_enabled))
    logger.info('Efficiency window hours: {}'.format(efficiency_window_hours))
    logger.info('Base min efficiency threshold: {}'.format(base_min_efficiency_threshold))
    logger.info('Good drying level: {}'.format(good_drying_level))
    logger.info('Efficiency learning up: {}'.format(efficiency_learning_up))
    logger.info('Efficiency learning down: {}'.format(efficiency_learning_down))
    logger.info('TS weight: {}'.format(ts_weight))

    sdef_on = int(sdef_on * 10)
    sdef_min_offset = int(sdef_min_offset * 10)
    sdef_hys = int(sdef_hys * 10)
    uschutz_on = int(uschutz_on * 10)
    uschutz_hys = int(uschutz_hys * 10)
    ts_hys = int(ts_hys * 10)
    intervall_on = int(intervall_on * 10)
    intervall_time = int(intervall_time * 10)
    intervall_duration = int(intervall_duration * 10)
    notifications_enabled = _to_bool(notifications_enabled)
    self_learning_enabled = _to_bool(self_learning_enabled)
    efficiency_window_hours = int(efficiency_window_hours * 10)
    base_min_efficiency_threshold = int(base_min_efficiency_threshold * 100)
    good_drying_level = int(good_drying_level * 100)
    efficiency_learning_up = int(efficiency_learning_up * 100)
    efficiency_learning_down = int(efficiency_learning_down * 100)
    ts_weight = int(ts_weight * 100)

   

    client = get_influxdb_client()
    write_api = client.write_api(write_options=SYNCHRONOUS)

    record = [
        Point("venti_param")
        .field("sdef_on", sdef_on)
        .field("sdef_min_offset", sdef_min_offset)
        .field("sdef_hys", sdef_hys)
        .field("uschutz_on", uschutz_on)
        .field("uschutz_hys", uschutz_hys)
        .field("ts_hys", ts_hys)
        .field("intervall_on", intervall_on)
        .field("intervall_time", intervall_time)
        .field("intervall_duration", intervall_duration)
        .field("notifications_enabled", notifications_enabled)
        .field("self_learning_enabled", self_learning_enabled)
        .field("efficiency_window_hours", efficiency_window_hours)
        .field("base_min_efficiency_threshold", base_min_efficiency_threshold)
        .field("good_drying_level", good_drying_level)
        .field("efficiency_learning_up", efficiency_learning_up)
        .field("efficiency_learning_down", efficiency_learning_down)
        .field("ts_weight", ts_weight)
    ]

    write_api.write(bucket="jokley_bucket", org=ORG, record=record)
    client.close()


def write_controller_state(state, command, mode, details=None):
    ORG = Config.INFLUX_ORG

    client = get_influxdb_client()
    write_api = client.write_api(write_options=SYNCHRONOUS)

    point = (
        Point("venti_state")
        .field("state", state)
        .field("command", command)
        .field("mode", mode)
    )

    if details:
        point = point.field("details_json", std_json.dumps(details, default=str))

    write_api.write(bucket=Config.INFLUX_BUCKET, org=ORG, record=[point])
    client.close()
