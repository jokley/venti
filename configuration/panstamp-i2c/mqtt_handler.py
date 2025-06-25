import os
import json
import time
import logging
import paho.mqtt.client as mqtt
from influx import write_relay_string_state  # Neue Funktion importieren
from i2c_IO import set_relay  # Relay-Steuerung

# Logger setup
logger = logging.getLogger("mqtt_handler")

# MQTT Configuration
MQTT_BROKER = "172.16.238.15"
MQTT_PORT = 1883
MQTT_TOPIC_COMMAND = "relay/control"
MQTT_TOPIC_STATE = "relay/state"
MQTT_CLIENT_ID = "relay_controller"

# Callback when a message is received
def on_message(client, userdata, message):
    try:
        payload = message.payload.decode("utf-8")
        logger.info(f"Received message on topic {message.topic}: {payload}")
        
        data = json.loads(payload)
        relay_id = data.get("id")
        state = data.get("relay")

        if relay_id is not None and state is not None:
            logger.info(f"Control Relay {relay_id}: {state}")
            set_relay(relay_id, state.lower() == 'on')

            # Neue InfluxDB-Schreibweise über Client-Funktion
            write_relay_string_state(relay_id, state)

        else:
            logger.warning("Invalid message format, expected 'id' and 'relay'.")

    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)

def on_connect(client, userdata, flags, rc):
    logger.info(f"Connected to MQTT Broker with result code {rc}")
    client.subscribe(MQTT_TOPIC_COMMAND)

def on_disconnect(client, userdata, rc):
    logger.warning(f"Disconnected from MQTT Broker with result code {rc}")

def setup_mqtt():
    client = mqtt.Client(client_id=MQTT_CLIENT_ID, protocol=mqtt.MQTTv311)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    logger.info(f"Connecting to MQTT Broker at {MQTT_BROKER}:{MQTT_PORT}...")
    client.connect(MQTT_BROKER, MQTT_PORT, 60)

    return client
