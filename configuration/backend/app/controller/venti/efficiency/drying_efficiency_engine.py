class DryingEfficiencyEngine:
    def __init__(self, ts_weight=0.3):
        self.ts_weight = ts_weight

    def compute(self, ctx):
        """
        Central drying efficiency model.
        Returns a metrics dict so downstream logic can both decide and explain.
        """
        window_seconds = ctx.efficiency_window or 0

        if window_seconds <= 0:
            return {
                "efficiency": 0.0,
                "window_seconds": 0,
                "window_hours": 0.0,
                "sdef_gain": 0.0,
                "ts_gain": 0.0,
                "weighted_gain": 0.0,
                "has_history": False,
            }

        has_history = (
            ctx.sDefOut is not None
            and ctx.sDef_2h_ago is not None
            and ctx.tsOut is not None
            and ctx.ts_2h_ago is not None
        )

        if not has_history:
            return {
                "efficiency": 0.0,
                "window_seconds": window_seconds,
                "window_hours": round(window_seconds / 3600.0, 3),
                "sdef_gain": 0.0,
                "ts_gain": 0.0,
                "weighted_gain": 0.0,
                "has_history": False,
            }

        sdef_gain = ctx.sDefOut - ctx.sDef_2h_ago
        ts_gain = ctx.tsOut - ctx.ts_2h_ago
        weighted_gain = sdef_gain + (self.ts_weight * ts_gain)
        window_hours = window_seconds / 3600.0
        efficiency = weighted_gain / window_hours if window_hours > 0 else 0.0

        return {
            "efficiency": efficiency,
            "window_seconds": window_seconds,
            "window_hours": round(window_hours, 3),
            "sdef_gain": sdef_gain,
            "ts_gain": ts_gain,
            "weighted_gain": weighted_gain,
            "has_history": True,
        }
