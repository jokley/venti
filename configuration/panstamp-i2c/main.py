import os
import time
import serial
import math
import logging
import threading
from datetime import datetime
from queue import Queue, Full, Empty
from collections import defaultdict

from sensor_parser import parse_line
from influx import write_combined_point
from mqtt_handler import setup_mqtt

# Configure logging
LOG_LEVEL = "INFO"
logging.basicConfig(level=LOG_LEVEL,
                    format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger("panstamp_i2c")

# Global constants
SERIAL_PORT = "/dev/ttyUSB0"
BAUDRATE = 38400
QUEUE_MAXSIZE = 100

NODE_NAME_MAP = {}
env_mapping = {
    "NODE_OUTDOOR00": "outdoor00",
    "NODE_PROBE01": "probe01",
    "NODE_PROBE02": "probe02",
}

for env_var, name in env_mapping.items():
    node_id = os.getenv(env_var)
    if node_id and node_id.isdigit():
        NODE_NAME_MAP[int(node_id)] = name


USB_VENDOR_ID = "0403"
USB_PRODUCT_ID = "6015"  # FTDI Panstick device
USB_SYS_BASE = "/sys/bus/usb/devices"
USB_DRIVER_BASE = "/sys/bus/usb/drivers/usb"
USB_RESET_RETRY_INTERVAL = 3


def _read_sysfs_value(path):
    with open(path, encoding="utf-8") as value_file:
        return value_file.read().strip().lower()


def get_usb_sys_path(vendor_id, product_id):
    """Return the sysfs USB device path (for example ``1-1.1``) for Panstick."""
    try:
        for entry in os.listdir(USB_SYS_BASE):
            dev_path = os.path.join(USB_SYS_BASE, entry)
            try:
                vendor = _read_sysfs_value(os.path.join(dev_path, "idVendor"))
                product = _read_sysfs_value(os.path.join(dev_path, "idProduct"))
            except (FileNotFoundError, NotADirectoryError):
                continue

            if vendor == vendor_id.lower() and product == product_id.lower():
                return entry
    except Exception:
        logger.exception("Error finding USB sysfs path.")
    return None


def _write_sysfs(path, value):
    with open(path, "w", encoding="utf-8") as sysfs_file:
        sysfs_file.write(f"{value}\n")


def usb_unbind_bind():
    """Try to recover the FTDI adapter by re-binding the host USB device."""
    usb_path = get_usb_sys_path(USB_VENDOR_ID, USB_PRODUCT_ID)
    if usb_path is None:
        logger.error("Unable to find matching USB device path for %s:%s.", USB_VENDOR_ID, USB_PRODUCT_ID)
        return False

    try:
        logger.warning("Unbinding USB device %s", usb_path)
        _write_sysfs(os.path.join(USB_DRIVER_BASE, "unbind"), usb_path)
        time.sleep(3)
        logger.warning("Rebinding USB device %s", usb_path)
        _write_sysfs(os.path.join(USB_DRIVER_BASE, "bind"), usb_path)
        time.sleep(3)
        logger.info("USB unbind/bind completed for %s", usb_path)
        return True
    except Exception:
        logger.exception("USB unbind/bind failed for %s.", usb_path)
        return False


def read_serial(serial_port, baudrate, data_queue, reconnect_wait=5, max_retries=None):
    """
    Continuously read lines from serial and enqueue them; robust to errors.
    Resets the USB device after repeated failures.
    """
    retries = 0
    while True:
        try:
            with serial.Serial(serial_port, baudrate, timeout=1) as ser:
                logger.info("Opened serial port %s", serial_port)
                while True:
                    try:
                        line = ser.readline().decode(errors="ignore").strip()
                        if line:
                            # Reset only after actual serial traffic, not merely an open.
                            retries = 0
                            data_queue.put(line, timeout=1)
                    except Full:
                        logger.warning("⚠️ Serial data queue full, dropping incoming line.")
                        time.sleep(0.1)
        except (serial.SerialException, OSError) as exc:
            retries += 1
            logger.error("Serial port error (retry %s): %s", retries, exc)
            if max_retries and retries >= max_retries:
                logger.error("Max retries (%s) reached, giving up.", max_retries)
                break
            if retries % USB_RESET_RETRY_INTERVAL == 0:
                usb_unbind_bind()
            logger.info("Attempting to reconnect in %s seconds...", reconnect_wait)
            time.sleep(reconnect_wait)
        except KeyboardInterrupt:
            logger.info("Serial reader interrupted by user.")
            break
        except Exception:
            logger.exception("Unexpected error in serial reader thread.")
            time.sleep(reconnect_wait)

def main():
    logger.info(f"Started logging from {SERIAL_PORT} at {BAUDRATE} baud...")

    cache = defaultdict(dict)
    data_queue = Queue(maxsize=QUEUE_MAXSIZE)

    # Setup MQTT client
    mqtt_client = setup_mqtt()
    mqtt_client.loop_start()

    # Start the serial reader thread
    serial_thread = threading.Thread(target=read_serial, args=(SERIAL_PORT, BAUDRATE, data_queue), daemon=True)
    serial_thread.start()

    while True:
        try:
            line = data_queue.get(timeout=5)
        except Empty:
            logger.debug("No serial data received in last 5 seconds.")
            continue

        timestamp_s = int(time.time())
        parsed = parse_line(line)
        logger.info(f"Parsed line: {parsed}")
        if not parsed:
            continue

        node = parsed["node"]
        node_name = NODE_NAME_MAP.get(node, f"node{node}")
        register = parsed["register"]

        cache[node]["rssi_dbm"] = parsed["rssi_dbm"]
        cache[node]["lqi"] = parsed["lqi"]

        if register == 0x0C:
            cache[node]["temperature_c"] = parsed.get("temperature_c")
            cache[node]["humidity_percent"] = parsed.get("humidity_percent")
            cache[node]["timestamp_s"] = timestamp_s
        elif register == 0x0B:
            cache[node]["battery_v"] = parsed.get("battery_v")

        required = ["rssi_dbm", "lqi", "temperature_c", "humidity_percent", "battery_v", "timestamp_s"]
        if all(key in cache[node] for key in required):
            tmp = cache[node]["temperature_c"]
            hum = cache[node]["humidity_percent"]
        
            trockenmasse = -0.0028 * hum**2 + 0.004 * hum + (87 + tmp * 0.2677)
            sdef = ((hum * -0.05) + 5) * math.exp(0.0625 * tmp)
        
            cache[node]["trockenmasse"] = round(trockenmasse, 2)
            cache[node]["sdef"] = round(sdef, 3)
        
            write_combined_point(
                node_name=node_name,
                tmp=tmp,
                hum=hum,
                trockenmasse=cache[node]["trockenmasse"],
                sdef=cache[node]["sdef"],
                battery=cache[node]["battery_v"],
                rssi=cache[node]["rssi_dbm"],
                timestamp_s=timestamp_s,
            )
        
            logger.info(f"Wrote data for node {node_name} to InfluxDB")
            cache.pop(node)
        else:
            logger.debug(f"Incomplete data for node {node}, skipping Influx write.")

if __name__ == "__main__":
    main()
