# backend/services/venti_service.py
from flask import json
from datetime import datetime, timedelta, timezone
from ..utils.logger import logger
from ..services.influx_service import (
    get_venti_control_values,
    get_venti_control_param_values,
    get_min_max_values,
    get_outdoor_values,
    get_venti_lastTimeOn,
)
from ..extensions.extensions import mqtt
from ..db.influx_client import get_influxdb_client
from ..utils.time_utils import (
    get_timestamp_now_epoche,
    get_timestamp_now_offset,
)
from ..config import Config
from influxdb_client import  Point
from influxdb_client.client.write_api import SYNCHRONOUS

def venti_control():
    """
    Main ventilation control logic.
    Reads current sensor and control values, then decides
    whether to turn the fan on/off based on temperature,
    humidity, stock, and other thresholds.
    """
    # --- Get control and sensor values ---
    dataVenti = get_venti_control_values()
    startTime = dataVenti[0]['mode'][0]
    mode = dataVenti[0]['mode'][1]
    tsSoll = dataVenti[0]['trockenMasseSoll'][1]
    stock = int(dataVenti[0]['stockaufbau'][1]) * 3600

    if mode == "on":
        venti_cmd("on")
        return

    # Min/Max probe values
    data = get_min_max_values()
    humMin = data[0]['humidityMin']
    humMax = data[0]['humidityMax']
    sDefMin = data[0]['sDefMin']
    sDefMax = data[0]['sDefMax']
    tempMin = data[0]['temperatureMin']
    tempMax = data[0]['temperatureMax']
    tsMin = data[0]['trockenMasseMin']
    tsMax = data[0]['trockenMasseMax']

    # Outdoor values
    dataOut = get_outdoor_values()
    humOut = dataOut[0]['humidityOut']
    sDefOut = dataOut[0]['sDefOut']
    tempOut = dataOut[0]['temperatureOut']
    tsOut = dataOut[0]['trockenMasseOut']

    # Last fan on/off times
    dataLastTime = get_venti_lastTimeOn()
    lastOn = dataLastTime[0]['lastTimeOn']
    lastOff = dataLastTime[0]['lastTimeOff']

    # --- Time calculations ---
    DST = get_timestamp_now_offset()
    timeNow = get_timestamp_now_epoche()

    startTimeStock = (startTime + timedelta(seconds=DST)).replace(tzinfo=timezone.utc).timestamp()
    lastTimeOn = (lastOn + timedelta(seconds=DST)).replace(tzinfo=timezone.utc).timestamp()
    lastTimeOff = (lastOff + timedelta(seconds=DST)).replace(tzinfo=timezone.utc).timestamp()

    remainingTimeStock = int(timeNow - startTimeStock)
    remainingTimeInterval = int(timeNow - lastTimeOn)
    remainingTimeIntervalOn = int(timeNow - lastTimeOff)
    remainingTimeIntervalDiff = int(lastTimeOn - lastTimeOff)

    # --- Control parameters ---
    pramsVenti = get_venti_control_param_values()

    sdef_on = pramsVenti[0]['sdef_on'][1] / 10
    sdef_min_offset = pramsVenti[0]['sdef_min_offset'][1] / 10
    sdef_hys = pramsVenti[0]['sdef_hys'][1] / 10
    uschutz_on = pramsVenti[0]['uschutz_on'][1] / 10
    uschutz_hys = pramsVenti[0]['uschutz_hys'][1] / 10
    ts_hys = pramsVenti[0]['ts_hys'][1] / 10
    intervall_on = pramsVenti[0]['intervall_on'][1] / 10
    intervall_time = (pramsVenti[0]['intervall_time'][1] / 10) * 3600
    intervall_duration = (pramsVenti[0]['intervall_duration'][1] / 10) * 60
    intervall_enable = pramsVenti[0]['intervall_enable'][1]

    sdef_hys_half = sdef_hys / 2
    ts_hys_half = ts_hys / 2
    sdefMinThreshold = sDefMin + sdef_min_offset

    # --- Überhitzungsschutz ---
    if tempMax >= uschutz_on:
        venti_cmd("on")
        logger.info("****************************************")
        logger.info(f"Mode: {mode}")
        logger.info("Überhitzungsschutz aktiv!")
        logger.info(f"Temperatur: {tempMax}")
        return

    # --- Automatiksteuerung ---
    if tempMax + uschutz_hys < uschutz_on:
        if mode == "auto":
            # Stockaufbau
            if remainingTimeStock <= stock and stock > 0:
                venti_cmd("on")
                logger.info("****************************************")
                logger.info(f"Mode: {mode}")
                logger.info("Stockaufbau")
                logger.info(f"Restzeit: {stock - remainingTimeStock}")

            # Trockenmasse Automatik
            elif sDefOut >= sdefMinThreshold + sdef_hys_half and sDefOut >= sdef_on + sdef_hys_half and tsSoll >= tsMin + ts_hys_half:
                venti_cmd("on")
                logger.info("****************************************")
                logger.info(f"Mode: {mode}")
                logger.info("Lüfter ein")
                logger.info(f"SDef min: {sDefMin} | SDef out: {sDefOut}")
                logger.info(f"SDef diff: {sDefOut - sDefMin}")
                logger.info(f"TS ist: {tsMin} | TS soll: {tsSoll}")
                logger.info(f"TS diff: {tsSoll - tsMin}")
                logger.info(f"Dauer aus: {remainingTimeInterval}")

            # Intervall Belüftung
            elif humMax > intervall_on and (remainingTimeInterval >= intervall_time or (remainingTimeIntervalOn <= intervall_duration and remainingTimeIntervalDiff > 0)):
                venti_cmd("on")
                logger.info("****************************************")
                logger.info(f"Mode: {mode}")
                logger.info("Intervall Belüftung")
                logger.info(f"Intervall Schwelle: {intervall_on}")
                logger.info(f"Restzeit: {720 - remainingTimeIntervalOn}")

            # Belüftung aus
            elif remainingTimeStock > stock and (sDefOut < sdefMinThreshold - sdef_hys_half or sDefOut < sdef_on - sdef_hys_half or tsSoll < tsMin - ts_hys_half):
                venti_cmd("off")
                logger.info("****************************************")
                logger.info(f"Mode: {mode}")
                logger.info("Lüfter aus")
                logger.info(f"SDef min: {sDefMin} | SDef out: {sDefOut}")
                logger.info(f"SDef diff: {sDefOut - sDefMin}")
                logger.info(f"TS ist: {tsMin} | TS soll: {tsSoll}")
                logger.info(f"TS diff: {tsSoll - tsMin}")
                logger.info(f"Dauer aus: {remainingTimeInterval}")

                if remainingTimeInterval >= 7200 and tsSoll - tsMin <= 0.5:
                    venti_auto("off", tsSoll, "0")
                    logger.info("****************************************")
                    logger.info("Automatik aus")
                    logger.info(f"TS ist: {tsMin} | TS soll: {tsSoll}")

            # Nur Logger Info wenn alles andere nicht zutrifft
            else:
                venti_cmd("off")
                logger.info("****************************************")
                logger.info(f"Mode: {mode}")
                logger.info("Lüfter aus")
                logger.info(f"SDef min: {sDefMin} | SDef out: {sDefOut}")
                logger.info(f"SDef diff: {sDefOut - sDefMin}")
                logger.info(f"TS ist: {tsMin} | TS soll: {tsSoll}")
                logger.info(f"TS diff: {tsSoll - tsMin}")
                logger.info(f"Dauer aus: {remainingTimeInterval}")

        elif mode == "off":
            venti_cmd("off")

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