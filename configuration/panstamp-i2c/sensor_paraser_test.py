import serial
from datetime import datetime
import time
from collections import defaultdict
import math  


LOGFILE = "sensor_log.txt"


def parse_line(buf):
    if not buf.startswith("(") or ")" not in buf:
        return None

    try:
        # Extract RSSI and LQI
        header_end = buf.index(")")
        rssi_hex = buf[1:3]
        lqi_hex = buf[3:5]
        data = buf[header_end + 1:].strip()

        if len(data) < 18:
            return None  # Not enough data

        # Decode RSSI
        rssi_raw = int(rssi_hex, 16)
        rssi_signed = rssi_raw if rssi_raw < 128 else rssi_raw - 256
        rssi_dbm = (rssi_signed / 2.0) - 74.0
        lqi = int(lqi_hex, 16)

        node = int(data[0:4], 16)
        register = int(data[12:14], 16)

        result = {
            "node": node,
            "register": register,
            "rssi_dbm": round(rssi_dbm, 1),
            "lqi": lqi,
            "raw_hex": buf,
        }

        if register == 0x0C and len(data) >= 22:
            temp_raw = int(data[14:18], 16)
            humi_raw = int(data[18:22], 16)
            temp = (temp_raw - 500) / 10.0
            humi = humi_raw / 10.0
            result["temperature_c"] = round(temp, 1)
            result["humidity_percent"] = round(humi, 1)

        elif register == 0x0B and len(data) >= 18:
            batt_raw = int(data[14:18], 16)
            # batt = batt_raw / 1000.0
            batt = batt_raw
            result["battery_v"] = round(batt, 1)

        elif register == 0x0A and len(data) >= 18:
            interval = int(data[14:18], 16)
            result["interval_s"] = interval

        return result

    except (ValueError, IndexError):
        return None


def log(message):
    timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    full_msg = f"{timestamp}\n{message}"
    #print(full_msg)
    with open(LOGFILE, "a") as f:
        f.write(full_msg + "\n")


def main():
    port = "/dev/ttyUSB0"
    baudrate = 38400
    log(f"Started logging from {port} at {baudrate} baud...")

    # Store partial data until we can write a complete line
    cache = defaultdict(dict)

    with serial.Serial(port, baudrate, timeout=1) as ser:
        while True:
            line = ser.readline().decode(errors='ignore').strip()
            if not line:
                continue

            now = datetime.utcnow()
            # timestamp_ns = int(now.timestamp() * 1e9)
            timestamp_s = int(time.time())  # seconds

            # log(f"RAW: {line}")
            parsed = parse_line(line)
            if not parsed:
                continue

            # Mapping from node number to name
            NODE_NAME_MAP = {
                3: "outdoor00",
                19: "probe01",
                21: "probe02"
            }
            
            # Get node number from parsed data
            node = parsed["node"]
            
            # Use mapping to get the name, fallback to original node if not found
            node_name = NODE_NAME_MAP.get(node, f"node{node}")

            register = parsed["register"]

            # Always keep latest RSSI and LQI
            cache[node]["rssi_dbm"] = parsed["rssi_dbm"]
            cache[node]["lqi"] = parsed["lqi"]

            if register == 0x0C:  # Temperature and Humidity
                cache[node]["temperature_c"] = parsed.get("temperature_c")
                cache[node]["humidity_percent"] = parsed.get(
                    "humidity_percent")
                cache[node]["timestamp_s"] = timestamp_s

            elif register == 0x0B:  # Battery
                cache[node]["battery_v"] = parsed.get("battery_v")

            # Check if we have all necessary fields to log a full InfluxDB line
            required = ["rssi_dbm", "lqi", "temperature_c",
                        "humidity_percent", "battery_v", "timestamp_s"]
            if all(key in cache[node] for key in required):
                tmp = cache[node]["temperature_c"]
                hum = cache[node]["humidity_percent"]

                # Calculate trockenmasse and sdef
                trockenmasse = -0.0028 * hum**2 + 0.004 * hum + (87 + tmp * 0.2677)
                sdef = ((hum * -0.05) + 5) * math.exp(0.0625 * tmp)

                # Add them to cache so they can be logged
                cache[node]["trockenmasse"] = round(trockenmasse, 2)
                cache[node]["sdef"] = round(sdef, 3)

  
                line_protocol = (
                    f"device_frmpayload_data_temperature,device_name={node_name} value={tmp} {timestamp_s}\n"
                    f"device_frmpayload_data_humidity,device_name={node_name} value={hum} {timestamp_s}\n"
                    f"device_frmpayload_data_trockenmasse,device_name={node_name} value={cache[node]['trockenmasse']} {timestamp_s}\n"
                    f"device_frmpayload_data_sdef,device_name={node_name} value={cache[node]['sdef']} {timestamp_s}\n"
                    f"device_frmpayload_data_battery,device_name={node_name} value={cache[node]['battery_v']} {timestamp_s}\n"
                    f"device_frmpayload_data_rssi,device_name={node_name} rssi={cache[node]['rssi_dbm']} {timestamp_s}"
                )
                log(line_protocol)


                cache.pop(node)


if __name__ == "__main__":
    main()
