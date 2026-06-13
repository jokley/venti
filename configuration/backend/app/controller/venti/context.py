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
        # ⏰ TIME
        # =========================
        self.now = d.get("now")
        # =========================
        # 🔋 SYSTEM HEALTH
        # =========================
        self.battery = d.get("battery", {})
        self.rssi = d.get("rssi", {})
        self.sensor_age = d.get("sensor_age", {})
        # =========================
        # 💨 FAN RUNTIME
        # =========================
        self.fan_runtime_today = d.get("fan_runtime_today")
        self.fan_runtime_auto = d.get("fan_runtime_auto")
        self.auto_start = d.get("auto_start")
        self.is_fan_on = d.get("is_fan_on", False)
        self.fan_runtime_current = d.get("fan_runtime_current", 0)
        self.venti_drying_delay_remaining = d.get("venti_drying_delay_remaining", 0)
        self.venti_post_heizung_delay_remaining = d.get("venti_post_heizung_delay_remaining", 0)
        self.previous_state = d.get("previous_state")
        self.previous_state_started_at = d.get("previous_state_started_at")
        # =========================
        # 🧠 EFFICIENCY ENGINE
        # =========================
        self.sDef_2h_ago = d.get("sDef_2h_ago")
        self.ts_2h_ago = d.get("ts_2h_ago")
        self.temp_change_2h = d.get("temp_change_2h", 0)
        self.sdef_change_2h = d.get("sdef_change_2h", 0)
        self.ts_change_2h = d.get("ts_change_2h", 0)
        self.efficiency_window = d.get("efficiency_window", 2 * 3600)
        self.base_min_efficiency_threshold = d.get("base_min_efficiency_threshold", 0.25)
        self.min_efficiency_threshold = d.get("min_efficiency_threshold", self.base_min_efficiency_threshold)
        self.efficiency_endphase_ts_margin = d.get("efficiency_endphase_ts_margin", 3.0)
        self.ts_weight = d.get("ts_weight", 0.30)
        self.efficiency_min_runtime = d.get("efficiency_min_runtime",int((self.efficiency_window or 7200) * 0.25))
        # =========================
        # 🔥 HEIZUNG
        # =========================
        self.heizung_enabled = d.get("heizung_enabled", False)
        self.heizung_mode = d.get("heizung_mode", "off")
        self.heizung_dauer = d.get("heizung_dauer", 0)        # Sekunden
        self.heizung_sdef_limit = d.get("heizung_sdef_limit", 0)
        self.heizung_sdef_hys = d.get("heizung_sdef_hys", 1.0)
        self.heizung_sdef_was_active = d.get("heizung_sdef_was_active", False)
        self.heizung_sdef_delay_remaining = d.get("heizung_sdef_delay_remaining", 0)
        self.heizung_manual_command = d.get("heizung_manual_command")
        self.remainingTimeHeizung = d.get("remainingTimeHeizung", 999999)
        self.heizung_nachlauf = d.get("heizung_nachlauf", 0)  # Sekunden
        self.heizung_off_since = d.get("heizung_off_since", 999999)
        # heizung_active wird nach dem Context-Build im Controller gesetzt:
        # ctx.heizung_active = _compute_heizung_active(ctx)
        # ctx.heizung_off_since wird danach ebenfalls neu berechnet.
        self.heizung_active = False
