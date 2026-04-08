# backend/services/venti_service.py
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

def venti_auto_param(sdef_on, sdef_min_offset, sdef_hys, uschutz_on, uschutz_hys, ts_hys,
                     intervall_on, intervall_time, intervall_duration, intervall_enable):

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
    logger.info('Intervall enable: {}'.format(intervall_enable))

    sdef_on = int(sdef_on * 10)
    sdef_min_offset = int(sdef_min_offset * 10)
    sdef_hys = int(sdef_hys * 10)
    uschutz_on = int(uschutz_on * 10)
    uschutz_hys = int(uschutz_hys * 10)
    ts_hys = int(ts_hys * 10)
    intervall_on = int(intervall_on * 10)
    intervall_time = int(intervall_time * 10)
    intervall_duration = int(intervall_duration * 10)
    intervall_enable = intervall_enable

   

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
        .field("intervall_enable", intervall_enable)
    ]

    write_api.write(bucket="jokley_bucket", org=ORG, record=record)
    client.close()