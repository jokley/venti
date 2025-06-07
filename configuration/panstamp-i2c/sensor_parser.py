def parse_line(buf):
    if not buf.startswith("(") or ")" not in buf:
        return None

    try:
        header_end = buf.index(")")
        rssi_hex = buf[1:3]
        lqi_hex = buf[3:5]
        data = buf[header_end + 1:].strip()

        if len(data) < 18:
            return None  # Not enough data

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
