class VentiContext:

    def __init__(self, d):

        # =========================
        # 🌬 CORE CONTROL STATE
        # =========================
        self.mode = d.get("mode")

        self.tempMax = d.get("tempMax")

        self.sDefOut = d.get("sDefOut")
        self.sDefMin = d.get("sDefMin")

        self.tsMin = d.get("tsMin")
        self.tsSoll = d.get("tsSoll")

        self.humMax = d.get("humMax")

        # =========================
        # 🌾 STOCK
        # =========================
        self.stock = d.get("stock")
        self.remainingTimeStock = d.get("remainingTimeStock")

        # =========================
        # 💨 SENSOR STATE (drying logic)
        # =========================
        self.sdef_on = d.get("sdef_on")
        self.sdef_hys_half = d.get("sdef_hys_half")
        self.sdefMinThreshold = d.get("sdefMinThreshold")

        self.ts_hys_half = d.get("ts_hys_half")

        # =========================
        # ⏱ INTERVAL LOGIC
        # =========================
        self.intervall_on = d.get("intervall_on")

        self.remainingTimeInterval = d.get("remainingTimeInterval")
        self.remainingTimeIntervalOn = d.get("remainingTimeIntervalOn")
        self.remainingTimeIntervalDiff = d.get("remainingTimeIntervalDiff")

        self.intervall_time = d.get("intervall_time")
        self.intervall_duration = d.get("intervall_duration")

        # =========================
        # 🔥 PROTECTION
        # =========================
        self.uschutz_on = d.get("uschutz_on")
        self.uschutz_hys = d.get("uschutz_hys")

        # =========================
        # ⏰ TIME (IMPORTANT for alerts & summary)
        # =========================
        self.now = d.get("now")

        # =========================
        # 🔋 SYSTEM HEALTH (NEW)
        # =========================
        self.battery = d.get("battery", {})
        self.rssi = d.get("rssi", {})
        self.sensor_age = d.get("sensor_age", {})

        # =========================
        # FAN Runtime
        # =========================
        self.fan_runtime_today = d.get("fan_runtime_today")
        self.fan_runtime_auto = d.get("fan_runtime_auto")
        self.auto_start = d.get("auto_start")

        self.is_fan_on = d.get("is_fan_on", False)
        self.fan_runtime_current = d.get("fan_runtime_current", 0)

        # =========================
        # 📈 Duration Changes (2 hours)
        # =========================
        self.temp_change_2h = d.get("temp_change_2h", 0.0)
        self.sdef_change_2h = d.get("sdef_change_2h", 0.0)
        self.ts_change_2h = d.get("ts_change_2h", 0.0)
        self.outdoor_temp_change_2h = d.get("outdoor_temp_change_2h", 0.0)
