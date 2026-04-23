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
            "started_at": self.last_ts
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


# singleton
state_manager = ControlStateManager()