import smbus2

bus = smbus2.SMBus(1)
PCF8574_ADDR = 0x20

def set_relay(relay_id: int, state: bool):
    """
    Set individual relay state on PCF8574.
    relay_id: 1–8 (bit 0–7)
    state: True to turn ON (bit LOW), False to turn OFF (bit HIGH)
    """
    if not (1 <= relay_id <= 8):
        raise ValueError("Relay ID must be between 1 and 8")

    # Read current byte from PCF8574
    try:
        current_state = bus.read_byte(PCF8574_ADDR)
    except Exception as e:
        print(f"Error reading from I2C: {e}")
        current_state = 0xFF  # Default all OFF if read fails

    bit = 1 << (relay_id - 1)

    if state:
        # Turn ON relay => set bit LOW (clear bit)
        new_state = current_state & ~bit
    else:
        # Turn OFF relay => set bit HIGH (set bit)
        new_state = current_state | bit

    bus.write_byte(PCF8574_ADDR, new_state)
