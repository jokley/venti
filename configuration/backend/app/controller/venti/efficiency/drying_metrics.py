class DryingMetricsCalculator:
    def __init__(self, ts_weight=0.3):
        self.default_ts_weight = ts_weight

    def compute(self, ctx):
        """
        Central drying metrics model.

        The calculator contains stable derived values and condition results.
        It does not decide which command should be executed.
        """
        metrics = self._efficiency(ctx)
        metrics["ts_diff"] = self._ts_diff(ctx)
        metrics["sdef_diff"] = self._sdef_diff(ctx)
        metrics["drying_conditions"] = self._drying_conditions(ctx)
        metrics["near_efficiency_endphase"] = self._near_efficiency_endphase(ctx, metrics)
        return metrics

    def _efficiency(self, ctx):
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
            ctx.sDefMin is not None
            and ctx.sDef_2h_ago is not None
            and ctx.tsMin is not None
            and ctx.ts_2h_ago is not None
        )

        # Without a full history window we still return a metrics object,
        # but mark it as not usable for efficiency-based stopping.
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

        # Compare current drying-state values against historical drying-state
        # values from the same probe source. `sDefOut` is the outdoor trigger
        # signal and must not be mixed with historical probe readings.
        sdef_gain = ctx.sDefMin - ctx.sDef_2h_ago
        ts_gain = ctx.tsMin - ctx.ts_2h_ago

        # `sdef_gain` is the main signal. `ts_gain` is included with a
        # smaller weight so TS still influences the result without dominating it.
        ts_weight = getattr(ctx, "ts_weight", self.default_ts_weight)
        weighted_gain = sdef_gain + (ts_weight * ts_gain)
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

    def _ts_diff(self, ctx):
        if ctx.tsSoll is None or ctx.tsMin is None:
            return None
        return ctx.tsSoll - ctx.tsMin

    def _sdef_diff(self, ctx):
        if ctx.sDefOut is None or ctx.sDefMin is None:
            return None
        return ctx.sDefOut - ctx.sDefMin

    def _near_efficiency_endphase(self, ctx, metrics):
        ts_diff = metrics.get("ts_diff")
        ts_margin = getattr(ctx, "efficiency_endphase_ts_margin", None)
        return (
            ts_diff is not None
            and ts_margin is not None
            and ts_margin > 0
            and ts_diff < ts_margin
        )

    def _drying_conditions(self, ctx):
        # Vollstaendige Hysterese:
        # Luefter AUS startet mit oberen SDef- und unteren TS-Schwellen;
        # Luefter EIN laeuft bis zu den unteren SDef- und oberen TS-Schwellen.
        if not self._has_drying_condition_values(ctx):
            return self._drying_conditions_result(
                met=False,
                phase="unavailable",
                reason="missing_required_values",
                sdef_ok=False,
                ts_ok=False,
                sdef_threshold_min=None,
                sdef_threshold_on=None,
                ts_threshold=None,
            )

        thresholds = self._drying_thresholds(ctx)
        sdef_ok = (
            ctx.sDefOut >= thresholds["sdef_threshold_min"]
            and ctx.sDefOut >= thresholds["sdef_threshold_on"]
        )
        ts_ok = ctx.tsMin <= thresholds["ts_threshold"]

        return self._drying_conditions_result(
            met=sdef_ok and ts_ok,
            phase=thresholds["phase"],
            reason=self._drying_conditions_reason(sdef_ok, ts_ok),
            sdef_ok=sdef_ok,
            ts_ok=ts_ok,
            sdef_threshold_min=thresholds["sdef_threshold_min"],
            sdef_threshold_on=thresholds["sdef_threshold_on"],
            ts_threshold=thresholds["ts_threshold"],
        )

    def _has_drying_condition_values(self, ctx):
        return (
            ctx.sDefOut is not None
            and ctx.sdefMinThreshold is not None
            and ctx.sdef_on is not None
            and ctx.tsSoll is not None
            and ctx.tsMin is not None
            and ctx.sdef_hys_half is not None
            and ctx.ts_hys_half is not None
        )

    def _drying_thresholds(self, ctx):
        if ctx.is_fan_on:
            return {
                "phase": "continue",
                "sdef_threshold_min": ctx.sdefMinThreshold - ctx.sdef_hys_half,
                "sdef_threshold_on": ctx.sdef_on - ctx.sdef_hys_half,
                "ts_threshold": ctx.tsSoll + ctx.ts_hys_half,
            }

        return {
            "phase": "start",
            "sdef_threshold_min": ctx.sdefMinThreshold + ctx.sdef_hys_half,
            "sdef_threshold_on": ctx.sdef_on + ctx.sdef_hys_half,
            "ts_threshold": ctx.tsSoll - ctx.ts_hys_half,
        }

    def _drying_conditions_reason(self, sdef_ok, ts_ok):
        if sdef_ok and ts_ok:
            return "conditions_met"
        if not sdef_ok and not ts_ok:
            return "sdef_and_ts_not_met"
        if not sdef_ok:
            return "sdef_not_met"
        return "ts_not_met"

    def _drying_conditions_result(
        self,
        met,
        phase,
        reason,
        sdef_ok,
        ts_ok,
        sdef_threshold_min,
        sdef_threshold_on,
        ts_threshold,
    ):
        return {
            "met": met,
            "phase": phase,
            "reason": reason,
            "sdef_ok": sdef_ok,
            "ts_ok": ts_ok,
            "sdef_threshold_min": sdef_threshold_min,
            "sdef_threshold_on": sdef_threshold_on,
            "ts_threshold": ts_threshold,
        }
