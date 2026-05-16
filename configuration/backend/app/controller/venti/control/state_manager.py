from app.services.influx_service import get_last_controller_state, get_last_heizung_controller_state
from app.services.venti_service import write_controller_state, write_heizung_controller_state
from app.utils.logger import logger


AUTO_DELAY_SECONDS = 20 * 60


class ControlStateManager:

    def __init__(self):
        # Internal runtime memory. This mirrors the last persisted controller
        # state so the controller can continue smoothly across loop cycles.
        self.last_state = None
        self.last_command = None
        self.last_mode = None
        self.last_details = None
        self.last_ts = None

        # Self-learning memory:
        # - last inefficient stop timestamp
        # - snapshot of the last bad drying situation
        # - current adaptive efficiency threshold
        self.last_inefficient_stop = None
        self.last_bad_drying_snapshot = None
        self.adaptive_min_efficiency_threshold = None

        # Heizung memory:
        # - timestamp when heater went off → drives nachlauf calculation
        # - last known active state → edge detection EIN→AUS
        # - lock flag → blocks venti_control while heizung or nachlauf active
        self.heizung_off_ts = None
        self.heizung_was_active = False
        self.heizung_lock = False
        self.last_heizung_state = None
        self.last_heizung_command = None
        self.last_heizung_mode = None
        self.last_heizung_details = None
        self.last_heizung_ts = None
        self.last_heizung_relay_command = None
        self.last_heizung_forced_venti_command = None
        self.heizung_sdef_delay_started_at = None
        self.venti_drying_delay_started_at = None

    # =========================
    # 🔁 RESTORE
    # =========================
    def restore(self):
        data = get_last_controller_state()
        heizung_data = get_last_heizung_controller_state()

        if not data and not heizung_data:
            logger.info("No persisted controller state found")
            return None

        if heizung_data:
            self.restore_heizung(heizung_data)

        if not data:
            return {
                "state": self.last_state,
                "command": self.last_command,
                "mode": self.last_mode,
                "details": self.last_details,
                "started_at": self.last_ts,
                "adaptive_min_efficiency_threshold": self.adaptive_min_efficiency_threshold,
            }

        self.last_state = data.get("state")
        self.last_command = data.get("command")
        self.last_mode = data.get("mode")
        self.last_details = data.get("details", {})
        self.last_ts = data.get("started_at")
        self.adaptive_min_efficiency_threshold = (
            (self.last_details or {}).get("adaptive_threshold")
            or (self.last_details or {}).get("min_efficiency_threshold")
        )

        if self.last_state == "INEFFICIENT_DRYING" and self.last_ts is not None:
            self.last_inefficient_stop = self.last_ts
            self.last_bad_drying_snapshot = self._extract_bad_drying_snapshot(
                self.last_details,
                self.last_ts,
            )
        elif (
            self.last_state == "AUTO_IDLE"
            and (self.last_details or {}).get("reason") == "inefficient_cooldown"
            and self.last_ts is not None
        ):
            self.last_inefficient_stop = self.last_ts
        elif (
            self.last_state == "AUTO_IDLE"
            and (self.last_details or {}).get("reason") == "waiting_better_than_last_bad_drying"
        ):
            self.last_bad_drying_snapshot = (self.last_details or {}).get("last_bad_drying")

        logger.info(
            "Restored controller state: state=%s mode=%s",
            self.last_state,
            self.last_mode
        )

        return {
            "state": self.last_state,
            "command": self.last_command,
            "mode": self.last_mode,
            "details": self.last_details,
            "started_at": self.last_ts,
            "adaptive_min_efficiency_threshold": self.adaptive_min_efficiency_threshold,
        }

    def restore_heizung(self, data):
        self.last_heizung_state = data.get("state")
        self.last_heizung_command = data.get("command")
        self.last_heizung_mode = data.get("mode")
        self.last_heizung_details = data.get("details", {})
        self.last_heizung_ts = data.get("started_at")
        self.last_heizung_relay_command = self.last_heizung_command

        if self.last_heizung_state == "HEIZUNG_NACHLAUF" and self.last_heizung_ts is not None:
            self.heizung_off_ts = self.last_heizung_ts
            self.heizung_was_active = False
            self.heizung_lock = True
            logger.info(
                "Restored heizung nachlauf – lock gesetzt (off_ts=%s)",
                self.heizung_off_ts,
            )
        elif self.last_heizung_state == "HEIZUNG_ACTIVE":
            self.heizung_was_active = True
            self.heizung_lock = True
            self.last_heizung_forced_venti_command = "on"
            logger.info("Restored heizung active – lock gesetzt")

    # =========================
    # 💾 PERSIST
    # =========================
    def persist(self, state, command, mode, details, ctx):
        write_controller_state(
            state=state,
            command=command,
            mode=mode,
            details=details
        )

        self.last_state = state
        self.last_command = command
        self.last_mode = mode
        self.last_details = details
        self.last_ts = ctx.now

        logger.debug("State persisted: %s (%s)", state, command)

    # =========================
    # 🔥 HEIZUNG
    # =========================
    def update_heizung(self, heizung_active, ctx):
        """
        Einmal pro heizung_control() Zyklus aufrufen.

        - Erkennt Flanke EIN→AUS und setzt heizung_off_ts
        - Aktualisiert heizung_was_active
        - Setzt heizung_lock (wird von venti_control geprüft)

        Nachlauf-Prüfung erfolgt NACH diesem Aufruf in heizung_control(),
        weil heizung_off_since erst danach korrekt berechnet werden kann.
        heizung_lock wird deshalb in heizung_control() nochmals gesetzt.
        """
        if self.heizung_was_active and not heizung_active:
            self.heizung_off_ts = ctx.now
            logger.info("Heizung abgegangen – Nachlauf startet (off_ts=%s)", ctx.now)

        self.heizung_was_active = heizung_active

        # Vorläufiger Lock – wird in heizung_control() nach
        # Nachlauf-Berechnung endgültig gesetzt
        if heizung_active:
            self.heizung_lock = True

    def persist_heizung(self, state, command, mode, details, ctx):
        write_heizung_controller_state(
            state=state,
            command=command,
            mode=mode,
            details=details
        )

        self.last_heizung_state = state
        self.last_heizung_command = command
        self.last_heizung_mode = mode
        self.last_heizung_details = details
        self.last_heizung_ts = ctx.now

        logger.debug("Heizung state persisted: %s (%s)", state, command)

    def release_heizung_lock(self):
        """
        Gibt den Lock frei wenn weder Heizung noch Nachlauf aktiv.
        Wird von heizung_control() aufgerufen wenn Nachlauf endet.
        Setzt heizung_off_ts zurück damit kein Nachlauf mehr erkannt wird.
        """
        self.heizung_lock = False
        self.heizung_off_ts = None
        self.last_heizung_forced_venti_command = None
        logger.info("Heizung Lock freigegeben – venti_control wieder aktiv")

    # =========================
    # ⏳ AUTO DELAYS
    # =========================
    def start_heizung_sdef_delay(self, ctx):
        self.heizung_sdef_delay_started_at = ctx.now
        logger.info("Heizung SDEF Delay gestartet – %ss", AUTO_DELAY_SECONDS)

    def clear_heizung_sdef_delay(self):
        self.heizung_sdef_delay_started_at = None

    def get_heizung_sdef_delay_remaining(self, now):
        return self._delay_remaining(self.heizung_sdef_delay_started_at, now)

    def start_venti_drying_delay(self, ctx):
        self.venti_drying_delay_started_at = ctx.now
        logger.info("Venti Trocknungs-Delay gestartet – %ss", AUTO_DELAY_SECONDS)

    def clear_venti_drying_delay(self):
        self.venti_drying_delay_started_at = None

    def get_venti_drying_delay_remaining(self, now):
        return self._delay_remaining(self.venti_drying_delay_started_at, now)

    def _delay_remaining(self, started_at, now):
        if started_at is None:
            return 0

        remaining = AUTO_DELAY_SECONDS - int(now - started_at)

        if remaining <= 0:
            return 0

        return remaining

    # =========================
    # 🧠 SELF-LEARNING
    # =========================
    def remember_bad_drying(self, ctx, metrics, details=None):
        details = details or {}
        self.last_bad_drying_snapshot = {
            "timestamp": ctx.now,
            "sDefOut": ctx.sDefOut,
            "sDefMin": ctx.sDefMin,
            "sDefDiff": (
                ctx.sDefOut - ctx.sDefMin
                if ctx.sDefOut is not None and ctx.sDefMin is not None
                else None
            ),
            "tsMin": ctx.tsMin,
            "tsSoll": ctx.tsSoll,
            "tsDiff": (
                ctx.tsSoll - ctx.tsMin
                if ctx.tsSoll is not None and ctx.tsMin is not None
                else None
            ),
            "efficiency": metrics.get("efficiency"),
            "adaptive_threshold": details.get("adaptive_threshold"),
            "sdef_change_2h": details.get("sdef_change_2h", metrics.get("sdef_gain")),
            "ts_change_2h": details.get("ts_change_2h", metrics.get("ts_gain")),
            "window_hours": metrics.get("window_hours"),
        }
        self.last_inefficient_stop = ctx.now

    def clear_bad_drying(self):
        self.last_bad_drying_snapshot = None

    def retry_conditions_improved(self, ctx):
        snapshot = self.last_bad_drying_snapshot

        if not snapshot:
            return True, None

        current_sdef_diff = (
            ctx.sDefOut - ctx.sDefMin
            if ctx.sDefOut is not None and ctx.sDefMin is not None
            else None
        )
        current_ts_diff = (
            ctx.tsSoll - ctx.tsMin
            if ctx.tsSoll is not None and ctx.tsMin is not None
            else None
        )

        better_sdef_out = (
            snapshot.get("sDefOut") is not None
            and ctx.sDefOut is not None
            and ctx.sDefOut >= snapshot["sDefOut"] + (ctx.sdef_hys_half or 0)
        )
        better_sdef_diff = (
            snapshot.get("sDefDiff") is not None
            and current_sdef_diff is not None
            and current_sdef_diff >= snapshot["sDefDiff"] + (ctx.sdef_hys_half or 0)
        )
        better_ts_diff = (
            snapshot.get("tsDiff") is not None
            and current_ts_diff is not None
            and current_ts_diff >= snapshot["tsDiff"] + (ctx.ts_hys_half or 0)
        )
        not_worse_sdef = (
            snapshot.get("sDefDiff") is None
            or current_sdef_diff is None
            or current_sdef_diff >= snapshot["sDefDiff"]
        )
        not_worse_ts = (
            snapshot.get("tsDiff") is None
            or current_ts_diff is None
            or current_ts_diff >= snapshot["tsDiff"]
        )

        improved = (
            (better_sdef_out or better_sdef_diff or better_ts_diff)
            and not_worse_sdef
            and not_worse_ts
        )

        return improved, {
            "current": {
                "sDefOut": ctx.sDefOut,
                "sDefDiff": current_sdef_diff,
                "tsDiff": current_ts_diff,
            },
            "required_improvement": {
                "sDefOut": snapshot.get("sDefOut"),
                "sDefDiff": snapshot.get("sDefDiff"),
                "tsDiff": snapshot.get("tsDiff"),
            },
            "checks": {
                "better_sdef_out": better_sdef_out,
                "better_sdef_diff": better_sdef_diff,
                "better_ts_diff": better_ts_diff,
                "not_worse_sdef": not_worse_sdef,
                "not_worse_ts": not_worse_ts,
            },
        }

    def _extract_bad_drying_snapshot(self, details, timestamp):
        details = details or {}
        return {
            "timestamp": timestamp,
            "sDefOut": details.get("sDefOut"),
            "sDefMin": details.get("sDefMin"),
            "sDefDiff": details.get("sDefDiff"),
            "tsMin": details.get("tsMin"),
            "tsSoll": details.get("tsSoll"),
            "tsDiff": details.get("tsDiff"),
            "efficiency": details.get("efficiency"),
            "adaptive_threshold": details.get("adaptive_threshold"),
            "sdef_change_2h": details.get("sdef_change_2h"),
            "ts_change_2h": details.get("ts_change_2h"),
            "window_hours": details.get("window_hours"),
        }

    # =========================
    # 📈 ADAPTIVE THRESHOLD
    # =========================
    def get_adaptive_threshold(self, default_value):
        if self.adaptive_min_efficiency_threshold is None:
            self.adaptive_min_efficiency_threshold = default_value
        return self.adaptive_min_efficiency_threshold

    def update_adaptive_threshold(self, efficiency, ctx, has_history=True):
        threshold = self.get_adaptive_threshold(ctx.base_min_efficiency_threshold)

        if not has_history:
            return threshold

        if efficiency > ctx.good_drying_level:
            threshold *= ctx.efficiency_learning_down
        else:
            threshold *= ctx.efficiency_learning_up

        floor = max(0.01, ctx.base_min_efficiency_threshold * 0.5)
        ceiling = max(floor, ctx.base_min_efficiency_threshold * 2.0)
        threshold = min(max(threshold, floor), ceiling)

        self.adaptive_min_efficiency_threshold = round(threshold, 4)
        return self.adaptive_min_efficiency_threshold


# singleton
state_manager = ControlStateManager()
