from app.services.influx_service import get_last_controller_state
from app.services.venti_service import write_controller_state
from app.utils.logger import logger


class ControlStateManager:

    def __init__(self):
        # internal runtime memory (NO external dependency)
        self.last_state = None
        self.last_command = None
        self.last_mode = None
        self.last_details = None
        self.last_ts = None

        self.last_inefficient_stop = None
        self.adaptive_min_efficiency_threshold = None

    # =========================
    # 🔁 RESTORE
    # =========================
    def restore(self):
        data = get_last_controller_state()

        if not data:
            logger.info("No persisted controller state found")
            return None

        self.last_state = data.get("state")
        self.last_command = data.get("command")
        self.last_mode = data.get("mode")
        self.last_details = data.get("details", {})
        self.last_ts = data.get("started_at")
        self.adaptive_min_efficiency_threshold = (
            (self.last_details or {}).get("adaptive_threshold")
            or (self.last_details or {}).get("min_efficiency_threshold")
        )

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
