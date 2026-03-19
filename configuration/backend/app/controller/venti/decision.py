class Decision:
    def __init__(self, command, reason, details=None):
        self.command = command
        self.reason = reason
        self.details = details or {}