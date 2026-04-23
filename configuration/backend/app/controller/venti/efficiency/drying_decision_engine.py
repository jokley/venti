from ..decision import Decision


class DryingDecisionEngine:
    def decide(self, ctx, metrics):
        trace = []

        def step(name, matched, reason=None):
            trace.append({
                "step": name,
                "matched": matched,
                "reason": reason,
            })

        if ctx.mode != "auto":
            step("manual_mode", True, "MANUAL_MODE")
            return Decision(
                "off",
                "MANUAL_MODE",
                {
                    "runtime": ctx.remainingTimeInterval,
                    "tsDiff": ctx.tsSoll - ctx.tsOut if ctx.tsSoll is not None and ctx.tsOut is not None else None,
                    "trace": trace,
                },
            )

        if ctx.overheat:
            step("overheat", True, "OVERHEAT")
            return Decision(
                "on",
                "OVERHEAT",
                {
                    "tempMax": ctx.tempMax,
                    "threshold": ctx.uschutz_on,
                    "diff": ctx.tempMax - ctx.uschutz_on if ctx.tempMax is not None and ctx.uschutz_on is not None else None,
                    "trace": trace,
                },
            )

        if ctx.stock > 0 and ctx.remainingTimeStock <= ctx.stock:
            step("stock_building", True, "STOCK_BUILDING")
            return Decision(
                "on",
                "STOCK_BUILDING",
                {
                    "remaining": ctx.remainingTimeStock,
                    "stock": ctx.stock,
                    "restzeit": ctx.stock - ctx.remainingTimeStock,
                    "trace": trace,
                },
            )

        if ctx.fan_off and ctx.temp_rising:
            step("temp_rise_start", True, "TEMP_RISE")
            return Decision(
                "on",
                "TEMP_RISE",
                {
                    "temp_change_2h": ctx.temp_change_2h,
                    "reason": "fan_off_temp_rising_start",
                    "efficiency": metrics["efficiency"],
                    "trace": trace,
                },
            )

        if not ctx.drying_conditions_met:
            step("drying_conditions", True, "AUTO_IDLE")
            return Decision(
                "off",
                "AUTO_IDLE",
                {
                    "reason": "drying_conditions_not_met",
                    "sDefOut": ctx.sDefOut,
                    "threshold": ctx.sdefMinThreshold,
                    "tsDiff": ctx.tsSoll - ctx.tsOut if ctx.tsSoll is not None and ctx.tsOut is not None else None,
                    "efficiency": metrics["efficiency"],
                    "adaptive_threshold": ctx.min_efficiency_threshold,
                    "trace": trace,
                },
            )

        if not ctx.is_fan_on:
            step("drying_start", True, "DRYING_ACTIVE")
            return Decision(
                "on",
                "DRYING_ACTIVE",
                self._drying_details(ctx, metrics, trace, "start"),
            )

        if ctx.fan_runtime_current < ctx.efficiency_window:
            step("startup_window", True, "DRYING_ACTIVE")
            return Decision(
                "on",
                "DRYING_ACTIVE",
                self._drying_details(ctx, metrics, trace, "startup_window"),
            )

        if metrics["has_history"] and metrics["efficiency"] < ctx.min_efficiency_threshold:
            step("low_efficiency", True, "INEFFICIENT_DRYING")
            return Decision(
                "off",
                "INEFFICIENT_DRYING",
                {
                    "runtime": ctx.fan_runtime_current,
                    "efficiency": metrics["efficiency"],
                    "adaptive_threshold": ctx.min_efficiency_threshold,
                    "sdef_change_2h": metrics["sdef_gain"],
                    "ts_change_2h": metrics["ts_gain"],
                    "weighted_gain": metrics["weighted_gain"],
                    "window_hours": metrics["window_hours"],
                    "trace": trace,
                },
            )

        step("efficient_drying", True, "DRYING_ACTIVE")
        return Decision(
            "on",
            "DRYING_ACTIVE",
            self._drying_details(ctx, metrics, trace, "efficient"),
        )

    def _drying_details(self, ctx, metrics, trace, phase):
        return {
            "sDefOut": ctx.sDefOut,
            "sDefMin": ctx.sDefMin,
            "sDefDiff": ctx.sDefOut - ctx.sDefMin if ctx.sDefOut is not None and ctx.sDefMin is not None else None,
            "tsMin": ctx.tsOut,
            "tsSoll": ctx.tsSoll,
            "tsDiff": ctx.tsSoll - ctx.tsOut if ctx.tsSoll is not None and ctx.tsOut is not None else None,
            "efficiency": metrics["efficiency"],
            "adaptive_threshold": ctx.min_efficiency_threshold,
            "sdef_change_2h": metrics["sdef_gain"],
            "ts_change_2h": metrics["ts_gain"],
            "window_hours": metrics["window_hours"],
            "phase": phase,
            "trace": trace,
        }
