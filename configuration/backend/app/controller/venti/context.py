class VentiContext:

    def __init__(self, d, battery=None, rssi=None, sensor_age=None):

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
        self.battery = battery or {}       # {device: %}

        self.rssi = rssi or {}             # {device: dBm}

        self.sensor_age = sensor_age or {} # {device: seconds since last update}