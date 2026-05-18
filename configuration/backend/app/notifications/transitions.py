class TransitionDetector:
    def __init__(self):
        self.last_command = None
        self.last_reason = None
        self.last_details = None   # 👈 NEW
        self.state_start_ts = None

    def restore(self, command=None, reason=None, details=None, state_start_ts=None):
        self.last_command = command
        self.last_reason = reason
        self.last_details = details
        self.state_start_ts = state_start_ts

    def detect(self, decision, data):
        events = []

        now = data.get("now")
        if now is None:
            return events

        command = decision.command
        reason = decision.reason
        details = decision.details or {}

        # =========================
        # INIT
        # =========================
        if self.state_start_ts is None:
            self.state_start_ts = now
            self.last_reason = reason
            self.last_command = command
            self.last_details = details   # 👈 NEW
            return events

        # =========================
        # STATE CHANGE
        # =========================
        if self.last_reason != reason:
            duration = now - self.state_start_ts

            events.append((
                "STATE_CHANGE",
                self.last_reason,
                reason,
                duration,
                {
                    "old_details": self.last_details,   # 👈 OLD
                    "new_details": details,             # 👈 NEW
                    **data
                }
            ))

            self.state_start_ts = now

        # update
        self.last_command = command
        self.last_reason = reason
        self.last_details = details   # 👈 IMPORTANT

        return events
