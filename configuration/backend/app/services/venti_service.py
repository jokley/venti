# backend/services/venti_service.py
import json as std_json
from flask import json
from ..utils.logger import logger
from ..extensions.extensions import mqtt
from ..db.influx_client import get_influxdb_client
from ..config import Config
from influxdb_client import Point
from influxdb_client.client.write_api import SYNCHRONOUS


# Dragino LT-2222 relay downlink payloads:
# byte 1 = 03, byte 2 = RO1 action, byte 3 = RO2 action
# action 00 = Open, 01 = Close, 11 = No action
RO1_OPEN_RO2_NO_ACTION = "AwAR"       # 03 00 11
RO1_CLOSE_RO2_NO_ACTION = "AwER"      # 03 01 11
RO1_NO_ACTION_RO2_OPEN = "AxEA"       # 03 11 00
RO1_NO_ACTION_RO2_CLOSE = "AxEB"      # 03 11 01
RO1_OPEN_RO2_OPEN = "AwAA"            # 03 00 00
RO1_CLOSE_RO2_CLOSE = "AwEB"          # 03 01 01
RO1_CLOSE_RO2_OPEN = "AwEA"           # 03 01 00
RO1_OPEN_RO2_CLOSE = "AwAB"           # 03 00 01

COMBINED_RELAY_PAYLOADS = {
    ("off", "off"): RO1_OPEN_RO2_OPEN,
    ("on", "off"): RO1_CLOSE_RO2_OPEN,
    ("off", "on"): RO1_OPEN_RO2_CLOSE,
    ("on", "on"): RO1_CLOSE_RO2_CLOSE,
}


# =============================================================================
# 🌀 LÜFTER
# =============================================================================

def venti_cmd(cmd: str):
    """
    Sends command to the fan via MQTT (PanStamp or TTN).
    RO1 on Dragino LT-2222.
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
            # RO1 only – RO2 (Heizung) bleibt unangetastet
            data = RO1_CLOSE_RO2_NO_ACTION if cmd == "on" else RO1_OPEN_RO2_NO_ACTION
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


def venti_auto(cmd, trockenMasse, stockAufbau):
    """
    Writes fan mode, trockenmasse and stockaufbau to InfluxDB.
    """
    ORG = Config.INFLUX_ORG

    client = get_influxdb_client()
    write_api = client.write_api(write_options=SYNCHRONOUS)

    trockenMasse = int(trockenMasse * 10)

    record = [
        Point("venti")
        .field("mode", str(cmd))
        .field("trockenmasse", trockenMasse)
        .field("stockaufbau", str(stockAufbau))
    ]

    write_api.write(bucket=Config.INFLUX_BUCKET, org=ORG, record=record)
    client.close()


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
    """
    Writes fan control parameters to InfluxDB.
    All float values are scaled to int (* 10 or * 100) to avoid float storage issues.
    """
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

    write_api.write(bucket=Config.INFLUX_BUCKET, org=ORG, record=record)
    client.close()


# =============================================================================
# 🔥 HEIZUNG
# =============================================================================

def heizung_cmd(cmd: str):
    cmd = cmd.lower()
    try:
        if Config.PANSTAMP:
            topic = "relay/control"
            payload = json.dumps({"relay": cmd, "id": 2})
            mqtt.publish(topic, payload)
            logger.info(f"Heizung_cmd sent (PanStamp): {cmd}")
        else:
            if not Config.APPLICATION_ID or not Config.DEVICE_ID:
                logger.warning("Heizung_cmd: Missing APPLICATION_ID or DEVICE_ID, command skipped")
                return
            # RO2 only – RO1 (Lüfter) bleibt unangetastet
            # 03 11 01 = RO2 Close (EIN)
            # 03 11 00 = RO2 Open  (AUS)
            data = RO1_NO_ACTION_RO2_CLOSE if cmd == "on" else RO1_NO_ACTION_RO2_OPEN
            topic = f"application/{Config.APPLICATION_ID}/device/{Config.DEVICE_ID}/command/down"
            payload = json.dumps({
                "devEui": Config.DEVICE_ID,
                "confirmed": True,
                "fPort": 10,
                "data": data
            })
            mqtt.publish(topic, payload)
            logger.info(f"Heizung_cmd sent (TTN): {cmd}")
    except Exception as e:
        logger.error(f"Heizung_cmd error: {e}")


def heizung_venti_cmd(heizung: str, venti: str):
    """
    Sends one combined Dragino LT-2222 command for RO1 (fan) and RO2 (heater).
    """
    heizung = heizung.lower()
    venti = venti.lower()

    try:
        if Config.PANSTAMP:
            topic = "relay/control"
            mqtt.publish(topic, json.dumps({"relay": venti, "id": 1}))
            mqtt.publish(topic, json.dumps({"relay": heizung, "id": 2}))
            logger.info(f"Heizung/Venti_cmd sent (PanStamp): heizung={heizung}, venti={venti}")
        else:
            if not Config.APPLICATION_ID or not Config.DEVICE_ID:
                logger.warning("Heizung/Venti_cmd: Missing APPLICATION_ID or DEVICE_ID, command skipped")
                return

            data = COMBINED_RELAY_PAYLOADS.get((venti, heizung))
            if data is None:
                logger.warning(
                    "Heizung/Venti_cmd: Invalid command combination heizung=%s venti=%s",
                    heizung,
                    venti,
                )
                return

            topic = f"application/{Config.APPLICATION_ID}/device/{Config.DEVICE_ID}/command/down"
            payload = json.dumps({
                "devEui": Config.DEVICE_ID,
                "confirmed": True,
                "fPort": 10,
                "data": data
            })
            mqtt.publish(topic, payload)
            logger.info(f"Heizung/Venti_cmd sent (TTN): heizung={heizung}, venti={venti}")
    except Exception as e:
        logger.error(f"Heizung/Venti_cmd error: {e}")


def heizung_auto(cmd, heizung_dauer, heizung_sdef_limit=0):
    """
    Writes heating mode and duration to InfluxDB.

    cmd:           "off" | "on" | "auto"
    heizung_dauer:      duration in hours (float), stored as int * 10
                        only relevant when cmd == "auto"
    heizung_sdef_limit: outdoor SDEF threshold, stored as int * 10.
                        0 disables SDEF control.
    """
    ORG = Config.INFLUX_ORG

    client = get_influxdb_client()
    write_api = client.write_api(write_options=SYNCHRONOUS)

    heizung_dauer = float(heizung_dauer or 0)
    heizung_dauer = int(heizung_dauer * 10)
    heizung_sdef_limit = float(heizung_sdef_limit or 0)
    heizung_sdef_limit = max(0.0, min(20.0, heizung_sdef_limit))
    heizung_sdef_limit = int(heizung_sdef_limit * 10)

    record = [
        Point("heizung")
        .field("mode", str(cmd))
        .field("heizung_dauer", heizung_dauer)
        .field("heizung_sdef_limit", heizung_sdef_limit)
    ]

    write_api.write(bucket=Config.INFLUX_BUCKET, org=ORG, record=record)
    client.close()


def heizung_auto_param(
    heizung_enabled,
    heizung_nachlauf,
    heizung_sdef_hys,
):
    """
    Writes heating configuration parameters to InfluxDB.

    heizung_enabled:  bool   – feature active on this installation
    heizung_nachlauf: float  – cooldown time in minutes after heater stops,
                               stored as int * 10
    heizung_sdef_hys: float  – hysteresis below heizung_sdef_limit,
                               stored as int * 10
    """
    ORG = Config.INFLUX_ORG

    logger.info('****************************************')
    logger.info('Heizung Parameter geändert:')
    logger.info('Heizung enabled: {}'.format(heizung_enabled))
    logger.info('Heizung Nachlauf: {} min'.format(heizung_nachlauf))
    logger.info('Heizung SDEF Hysterese: {}'.format(heizung_sdef_hys))

    heizung_enabled = _to_bool(heizung_enabled)
    heizung_nachlauf = int(heizung_nachlauf * 10)   # Minuten * 10
    heizung_sdef_hys = float(heizung_sdef_hys or 0)
    heizung_sdef_hys = max(0.0, min(5.0, heizung_sdef_hys))
    heizung_sdef_hys = int(heizung_sdef_hys * 10)

    client = get_influxdb_client()
    write_api = client.write_api(write_options=SYNCHRONOUS)

    record = [
        Point("heizung_param")
        .field("heizung_enabled", heizung_enabled)
        .field("heizung_nachlauf", heizung_nachlauf)
        .field("heizung_sdef_hys", heizung_sdef_hys)
        # Zukunft auto_time:
        # .field("heizung_time_from", str(heizung_time_from))  # "06:00"
        # .field("heizung_time_to",   str(heizung_time_to))    # "18:00"
    ]

    write_api.write(bucket=Config.INFLUX_BUCKET, org=ORG, record=record)
    client.close()


# =============================================================================
# 🗃️ STATE
# =============================================================================

def write_controller_state(state, command, mode, details=None):
    """
    Persists the current controller decision to InfluxDB.
    Used by the state manager to restore state after restart.
    """
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


def write_heizung_controller_state(state, command, mode, details=None):
    """
    Persists the current heater decision to InfluxDB for Grafana and restore/debugging.
    """
    ORG = Config.INFLUX_ORG

    client = get_influxdb_client()
    write_api = client.write_api(write_options=SYNCHRONOUS)

    point = (
        Point("heizung_state")
        .field("state", state)
        .field("command", command)
        .field("mode", mode)
    )

    if details:
        point = point.field("details_json", std_json.dumps(details, default=str))
        if "venti_forced" in details:
            point = point.field("venti_forced", bool(details["venti_forced"]))

    write_api.write(bucket=Config.INFLUX_BUCKET, org=ORG, record=[point])
    client.close()


# =============================================================================
# 🛠️ HELPERS
# =============================================================================

def _to_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)
