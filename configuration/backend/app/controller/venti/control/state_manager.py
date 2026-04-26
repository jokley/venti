from app.services.influx_service import get_last_controller_state
from app.services.venti_service import write_controller_state
from app.utils.logger import logger


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

    # =========================
    # 🔁 RESTORE
    # =========================
    def restore(self):
        data = get_last_controller_state()

        if not data:
            logger.info("No persisted controller state found")
            return None

        # Restore the last known controller result so transitions,
        # mode changes, and adaptive threshold logic can resume cleanly.
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

    # =========================
    # 💾 PERSIST
    # =========================
    def persist(self, state, command, mode, details, ctx):
        # Persistence is the bridge between in-memory control logic and the
        # next controller cycle after a restart or redeploy.
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

    def remember_bad_drying(self, ctx, metrics, details=None):
        # Capture the full situation of a bad drying run so a later restart
        # can require meaningfully better conditions before retrying.
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
        # Once drying is active again we no longer need to block retries
        # based on the previous failed snapshot.
        self.last_bad_drying_snapshot = None

    def retry_conditions_improved(self, ctx):
        snapshot = self.last_bad_drying_snapshot

        if not snapshot:
            return True, None

        # Compare the current potential drying situation against the last
        # known bad run. A new retry is allowed only if the relevant values
        # improved and the others did not get worse.
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

    def get_adaptive_threshold(self, default_value):
        # Initialize lazily so classic mode does not need to care about the
        # adaptive threshold state at all.
        if self.adaptive_min_efficiency_threshold is None:
            self.adaptive_min_efficiency_threshold = default_value
        return self.adaptive_min_efficiency_threshold

    def update_adaptive_threshold(self, efficiency, ctx, has_history=True):
        threshold = self.get_adaptive_threshold(ctx.base_min_efficiency_threshold)

        if not has_history:
            return threshold

        # Good drying slightly lowers the stop threshold. Weak drying slightly
        # raises it. The floor/ceiling keeps learning bounded and predictable.
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
