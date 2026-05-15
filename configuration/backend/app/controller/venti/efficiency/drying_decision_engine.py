from ..decision import Decision
from ..control.state_manager import state_manager


class DryingDecisionEngine:
    def decide(self, ctx, metrics):
        trace = []

        def step(name, matched, reason=None):
            trace.append({
                "step": name,
                "matched": matched,
                "reason": reason,
            })

        # Global decision order:
        # 1. Manual modes
        # 2. Heizung active / nachlauf
        # 3. Overheat protection
        # 4. Stock building
        # 5. Drying logic (classic or self-learning)
        # 6. Interval ventilation
        # 7. Idle fallback

        if ctx.mode == "on":
            step("manual_on", True, "MANUAL_MODE")
            return Decision(
                "on",
                "MANUAL_MODE",
                {
                    "mode": ctx.mode,
                    "runtime": ctx.remainingTimeInterval,
                    "tsDiff": ctx.tsSoll - ctx.tsMin if ctx.tsSoll is not None and ctx.tsMin is not None else None,
                    "trace": trace,
                },
            )

        if ctx.mode != "auto":
            step("manual_mode", True, "MANUAL_MODE")
            return Decision(
                "off",
                "MANUAL_MODE",
                {
                    "runtime": ctx.remainingTimeInterval,
                    "tsDiff": ctx.tsSoll - ctx.tsMin if ctx.tsSoll is not None and ctx.tsMin is not None else None,
                    "trace": trace,
                },
            )

        # =========================
        # 🔥 HEIZUNG
        # Übersteuert Automatik komplett – Lüfter muss laufen solange
        # Heizung aktiv ist oder Nachlauf noch nicht abgelaufen.
        # =========================
        if ctx.heizung_enabled:
            if ctx.heizung_active:
                step("heizung_active", True, "HEIZUNG_ACTIVE")
                return Decision(
                    "on",
                    "HEIZUNG_ACTIVE",
                    {
                        "heizung_mode": ctx.heizung_mode,
                        "remaining": max(0, ctx.heizung_dauer - ctx.remainingTimeHeizung),
                        "trace": trace,
                    },
                )

            if ctx.heizung_off_since < ctx.heizung_nachlauf:
                step("heizung_nachlauf", True, "HEIZUNG_NACHLAUF")
                return Decision(
                    "on",
                    "HEIZUNG_NACHLAUF",
                    {
                        "nachlauf_remaining": ctx.heizung_nachlauf - ctx.heizung_off_since,
                        "heizung_nachlauf": ctx.heizung_nachlauf,
                        "heizung_off_since": ctx.heizung_off_since,
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

        # Both modes share the same outer controller flow.
        # Only the drying branch changes when self-learning is enabled.
        if ctx.self_learning_enabled:
            return self._decide_self_learning(ctx, metrics, trace, step)

        return self._decide_classic(ctx, metrics, trace, step)

    def _decide_classic(self, ctx, metrics, trace, step):
        # Classic mode stays close to the old parameter-based behavior:
        # if drying conditions are good, run; otherwise try interval mode;
        # otherwise remain idle.
        if ctx.drying_conditions_met:
            step("drying_active", True, "DRYING_ACTIVE")
            return Decision(
                "on",
                "DRYING_ACTIVE",
                self._drying_details(ctx, metrics, trace, "legacy_drying"),
            )

        if (
            ctx.humMax is not None
            and ctx.intervall_on is not None
            and ctx.humMax > ctx.intervall_on
            and (
                ctx.remainingTimeInterval >= ctx.intervall_time
                or (
                    ctx.remainingTimeIntervalOn <= ctx.intervall_duration
                    and ctx.remainingTimeIntervalDiff > 0
                )
            )
        ):
            step("interval_active", True, "INTERVAL_ACTIVE")
            return Decision(
                "on",
                "INTERVAL_ACTIVE",
                {
                    "humMax": ctx.humMax,
                    "threshold": ctx.intervall_on,
                    "interval_time": ctx.intervall_time,
                    "since_last_on": ctx.remainingTimeInterval,
                    "trace": trace,
                },
            )

        if (
            ctx.remainingTimeStock > ctx.stock
            and (
                ctx.sDefOut < ctx.sdefMinThreshold - ctx.sdef_hys_half
                or ctx.sDefOut < ctx.sdef_on - ctx.sdef_hys_half
                or ctx.tsSoll < ctx.tsMin - ctx.ts_hys_half
            )
        ):
            step("drying_not_possible", True, "AUTO_IDLE")
            return Decision(
                "off",
                "AUTO_IDLE",
                {
                    "reason": "drying_conditions_not_met",
                    "sDefOut": ctx.sDefOut,
                    "threshold": ctx.sdefMinThreshold,
                    "tsDiff": ctx.tsSoll - ctx.tsMin if ctx.tsSoll is not None and ctx.tsMin is not None else None,
                    "efficiency": metrics["efficiency"],
                    "adaptive_threshold": ctx.min_efficiency_threshold,
                    "trace": trace,
                },
            )

        step("auto_idle_default", True, "AUTO_IDLE")
        return self._auto_idle(ctx, metrics, trace, "drying_conditions_not_met")

    def _decide_self_learning(self, ctx, metrics, trace, step):
        # Self-learning uses the same start condition as classic mode,
        # then adds runtime-based efficiency checks and restart blocking
        # after a previously bad drying run.
        if ctx.drying_conditions_met:
            improved, retry_details = state_manager.retry_conditions_improved(ctx)
            if not improved:
                step("wait_better_retry_conditions", True, "AUTO_IDLE")
                return Decision(
                    "off",
                    "AUTO_IDLE",
                    {
                        "reason": "waiting_better_than_last_bad_drying",
                        "sDefOut": ctx.sDefOut,
                        "threshold": ctx.sdefMinThreshold,
                        "tsDiff": ctx.tsSoll - ctx.tsMin if ctx.tsSoll is not None and ctx.tsMin is not None else None,
                        "efficiency": metrics["efficiency"],
                        "adaptive_threshold": ctx.min_efficiency_threshold,
                        "last_bad_drying": state_manager.last_bad_drying_snapshot,
                        "retry_check": retry_details,
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

            # Give a fresh drying run time to produce history before
            # evaluating whether it is efficient enough to continue.
            if ctx.fan_runtime_current < ctx.efficiency_window:
                step("startup_window", True, "DRYING_ACTIVE")
                return Decision(
                    "on",
                    "DRYING_ACTIVE",
                    self._drying_details(ctx, metrics, trace, "startup_window"),
                )

            # Once enough history exists, stop the fan if the measured
            # drying efficiency falls below the active threshold.
            if metrics["has_history"] and metrics["efficiency"] < ctx.min_efficiency_threshold:
                step("low_efficiency", True, "INEFFICIENT_DRYING")
                return Decision(
                    "off",
                    "INEFFICIENT_DRYING",
                    {
                        **self._drying_details(ctx, metrics, trace, "inefficient"),
                        "runtime": ctx.fan_runtime_current,
                        "weighted_gain": metrics["weighted_gain"],
                    },
                )

            step("efficient_drying", True, "DRYING_ACTIVE")
            return Decision(
                "on",
                "DRYING_ACTIVE",
                self._drying_details(ctx, metrics, trace, "efficient"),
            )

        if (
            ctx.humMax is not None
            and ctx.intervall_on is not None
            and ctx.humMax > ctx.intervall_on
            and (
                ctx.remainingTimeInterval >= ctx.intervall_time
                or (
                    ctx.remainingTimeIntervalOn <= ctx.intervall_duration
                    and ctx.remainingTimeIntervalDiff > 0
                )
            )
        ):
            step("interval_active", True, "INTERVAL_ACTIVE")
            return Decision(
                "on",
                "INTERVAL_ACTIVE",
                {
                    "humMax": ctx.humMax,
                    "threshold": ctx.intervall_on,
                    "interval_time": ctx.intervall_time,
                    "since_last_on": ctx.remainingTimeInterval,
                    "trace": trace,
                },
            )

        step("drying_conditions_missing", True, "AUTO_IDLE")
        return self._auto_idle(ctx, metrics, trace, "drying_conditions_not_met")

    def _auto_idle(self, ctx, metrics, trace, reason):
        return Decision(
            "off",
            "AUTO_IDLE",
            {
                "reason": reason,
                "sDefOut": ctx.sDefOut,
                "threshold": ctx.sdefMinThreshold,
                "tsDiff": ctx.tsSoll - ctx.tsMin if ctx.tsSoll is not None and ctx.tsMin is not None else None,
                "efficiency": metrics["efficiency"],
                "adaptive_threshold": ctx.min_efficiency_threshold,
                "trace": trace,
            },
        )

    def _drying_details(self, ctx, metrics, trace, phase):
        # Keep all drying-related telemetry in one place so logs,
        # persistence, and notifications use the same payload shape.
        return {
            "sDefOut": ctx.sDefOut,
            "sDefMin": ctx.sDefMin,
            "sDefDiff": ctx.sDefOut - ctx.sDefMin if ctx.sDefOut is not None and ctx.sDefMin is not None else None,
            "tsMin": ctx.tsMin,
            "tsSoll": ctx.tsSoll,
            "tsDiff": ctx.tsSoll - ctx.tsMin if ctx.tsSoll is not None and ctx.tsMin is not None else None,
            "efficiency": metrics["efficiency"],
            "adaptive_threshold": ctx.min_efficiency_threshold,
            "sdef_change_2h": metrics["sdef_gain"],
            "ts_change_2h": metrics["ts_gain"],
            "window_hours": metrics["window_hours"],
            "phase": phase,
            "trace": trace,
        }