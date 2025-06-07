import os
import json
import time
import logging
import paho.mqtt.client as mqtt
from influx import write_to_influx
from i2c_IO import set_relay  # Importing the relay control function

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

            # Build measurement name
            measurement = f"device_frmpayload_data_RO{relay_id}_status"
            value = "ON" if state.lower() == "on" else "OFF"

            # Format line protocol
            timestamp = int(time.time())  # seconds precision
            line_protocol = f'{measurement},device_name=fan _value="{value}" {timestamp}'

            # Write to InfluxDB using your wrapper
            write_to_influx(line_protocol)

        else:
            logger.warning("Invalid message format, expected 'id' and 'relay'.")

    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)



# Write relay state to InfluxDB
def write_relay_state_to_influx(relay_id, state):
    timestamp_s = int(time.time())
    line_protocol = (
        f"relay_state,relay_id={relay_id} state={1 if state.lower() == 'on' else 0} {timestamp_s}"
    )
    write_to_influx(line_protocol)

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
