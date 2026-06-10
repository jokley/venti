from ..decision import Decision
from ..control.state_manager import state_manager


class DryingDecisionEngine:
    def decide(self, ctx, metrics, previous_state=None):
        decision = self._decide_base(ctx, metrics)
        decision = self._apply_auto_disable(ctx, decision)
        decision = self._apply_drying_delay_start(ctx, decision, previous_state)
        return decision

    def _decide_base(self, ctx, metrics):
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
        # Fruehere Treffer gewinnen. Dadurch kann z.B. Ueberhitzung oder
        # Heizung den normalen Trocknungs- und Intervallzweig uebersteuern.

        if ctx.mode == "on":
            step("manual_on", True, "VENTI_MANUAL_ON")
            return Decision(
                "on",
                "VENTI_MANUAL_ON",
                {
                    "mode": ctx.mode,
                    "runtime": ctx.remainingTimeInterval,
                    "tsDiff": ctx.tsSoll - ctx.tsMin if ctx.tsSoll is not None and ctx.tsMin is not None else None,
                    "trace": trace,
                },
            )

        if ctx.mode != "auto":
            step("manual_off", True, "VENTI_MANUAL_OFF")
            return Decision(
                "off",
                "VENTI_MANUAL_OFF",
                {
                    "mode": ctx.mode,
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

        if self._is_overheat(ctx):
            # Ueberhitzung hat Vorrang vor Komfort-/Effizienzregeln:
            # Luefter an, bis die Hysterese in control_data wieder freigibt.
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
            # Stockaufbau ist eine feste Nachlauf-/Aufbauphase und wird vor
            # Trocknungs- und Intervalllogik behandelt.
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


    def _apply_auto_disable(self, ctx, decision):
        # Sicherheitsausstieg fuer lange, wirkungslose Automatikphasen:
        # Wenn Auto seit laengerem AUS ist und TS praktisch am Ziel liegt,
        # liefert die Engine nur den Mode-Override. venti_auto() bleibt als
        # Seiteneffekt bewusst im Controller.
        auto_disable_triggered = (
            ctx.mode == "auto"
            and decision.command == "off"
            and ctx.remainingTimeStock is not None
            and ctx.stock is not None
            and ctx.remainingTimeStock > ctx.stock
            and not ctx.is_fan_on
            and ctx.remainingTimeIntervalOn is not None
            and ctx.remainingTimeIntervalOn >= 7200
            and ctx.tsSoll is not None
            and ctx.tsMin is not None
            and (ctx.tsSoll - ctx.tsMin) <= 0.5
        )

        if not auto_disable_triggered:
            return decision

        details = {
            "runtime": ctx.remainingTimeInterval,
            "tsDiff": ctx.tsSoll - ctx.tsMin,
            "reason": "auto_disabled",
            "mode_override": "off",
            "previous_decision_reason": decision.reason,
            "previous_decision_detail_reason": (decision.details or {}).get("reason"),
            "auto_off_after_seconds": ctx.remainingTimeIntervalOn,
        }

        trace = (decision.details or {}).get("trace")
        if trace is not None:
            details["trace"] = trace + [{
                "step": "auto_disable",
                "matched": True,
                "reason": "MANUAL_MODE",
            }]

        return Decision("off", "MANUAL_MODE", details)

    def _apply_drying_delay_start(self, ctx, decision, previous_state):
        # Restart-Sperre nach Ende eines Trocknungslaufs. Die aktive Sperre wird
        # weiter in _drying_delay_active() ausgewertet; diese Methode startet nur
        # den Delay, wenn DRYING_ACTIVE gerade wegen fehlender Bedingungen endet.
        should_start_delay = (
            ctx.mode == "auto"
            and previous_state == "DRYING_ACTIVE"
            and decision.reason == "AUTO_IDLE"
            and (decision.details or {}).get("reason") == "drying_conditions_not_met"
        )

        if not should_start_delay:
            return decision

        state_manager.start_venti_drying_delay(ctx)
        decision.details["delay_remaining"] = (
            state_manager.get_venti_drying_delay_remaining(ctx.now)
        )
        decision.details["delay_started"] = True
        return decision

    def _is_overheat(self, ctx):
        return (
            ctx.tempMax is not None
            and ctx.uschutz_on is not None
            and ctx.tempMax >= ctx.uschutz_on
        )

    def _drying_conditions(self, ctx):
        # Vollstaendige Hysterese aus VentiContext:
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

    def _decide_classic(self, ctx, metrics, trace, step):
        # Classic mode stays close to the old parameter-based behavior:
        # if drying conditions are good, run; otherwise try interval mode;
        # otherwise remain idle.
        # sDefOut Hysterese wird in _drying_conditions abgedeckt –
        # EIN bei oberer Schwelle, Weiterlaufen bis untere Schwelle.
        drying = self._drying_conditions(ctx)
        if drying["met"]:
            if self._drying_delay_active(ctx):
                # Nach einem beendeten Trocknungslauf blockiert der Delay nur
                # erneutes DRYING_ACTIVE. Intervall darf trotzdem laufen.
                interval_decision = self._interval_decision(ctx, trace, step)
                if interval_decision:
                    return interval_decision
                step("drying_delay", True, "AUTO_IDLE")
                return self._auto_idle(ctx, metrics, trace, "drying_delay", drying)
    
            step("drying_active", True, "DRYING_ACTIVE")
            return Decision(
                "on",
                "DRYING_ACTIVE",
                self._drying_details(ctx, metrics, trace, "legacy_drying", drying),
            )
    
        interval_decision = self._interval_decision(ctx, trace, step)
        if interval_decision:
            return interval_decision
    
        # Ziel erreicht – tsMin hat tsSoll + ts_hys_half überschritten
        # sDefOut Checks entfallen hier da in _drying_conditions mit
        # korrekter Hysterese abgedeckt.
        if (
            ctx.remainingTimeStock > ctx.stock
            and ctx.tsSoll is not None
            and ctx.tsMin is not None
            and ctx.tsMin > ctx.tsSoll + ctx.ts_hys_half
        ):
            step("drying_not_possible", True, "AUTO_IDLE")
            return self._auto_idle(ctx, metrics, trace, "ts_target_reached", drying)
    
        step("auto_idle_default", True, "AUTO_IDLE")
        return self._auto_idle(ctx, metrics, trace, "drying_conditions_not_met", drying)

    def _decide_self_learning(self, ctx, metrics, trace, step):
        # Self-learning uses the same start condition as classic mode,
        # then adds runtime-based efficiency checks and restart blocking
        # after a previously bad drying run.
        drying = self._drying_conditions(ctx)
        if drying["met"]:
            if self._drying_delay_active(ctx):
                # Self-Learning nutzt denselben Restart-Delay wie Classic:
                # erst Intervall pruefen, sonst im Idle mit Delaygrund bleiben.
                interval_decision = self._interval_decision(ctx, trace, step)
                if interval_decision:
                    return interval_decision

                step("drying_delay", True, "AUTO_IDLE")
                return self._auto_idle(ctx, metrics, trace, "drying_delay", drying)

            # Nach einem schlechten Lauf muss die neue Ausgangslage messbar
            # besser sein, damit der Controller nicht sofort wieder startet.
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
                        "drying_conditions": drying,
                        "trace": trace,
                    },
                )

            if not ctx.is_fan_on:
                step("drying_start", True, "DRYING_ACTIVE")
                return Decision(
                    "on",
                    "DRYING_ACTIVE",
                    self._drying_details(ctx, metrics, trace, "start", drying),
                )

            # Give a fresh drying run time to produce history before
            # evaluating whether it is efficient enough to continue.
            if ctx.fan_runtime_current < ctx.efficiency_window:
                step("startup_window", True, "DRYING_ACTIVE")
                return Decision(
                    "on",
                    "DRYING_ACTIVE",
                    self._drying_details(ctx, metrics, trace, "startup_window", drying),
                )

            # Once enough history exists, stop the fan if the measured
            # drying efficiency falls below the active threshold.
            if metrics["has_history"] and metrics["efficiency"] < ctx.min_efficiency_threshold:
                step("low_efficiency", True, "INEFFICIENT_DRYING")
                return Decision(
                    "off",
                    "INEFFICIENT_DRYING",
                    {
                        **self._drying_details(ctx, metrics, trace, "inefficient", drying),
                        "runtime": ctx.fan_runtime_current,
                        "weighted_gain": metrics["weighted_gain"],
                    },
                )

            step("efficient_drying", True, "DRYING_ACTIVE")
            return Decision(
                "on",
                "DRYING_ACTIVE",
                self._drying_details(ctx, metrics, trace, "efficient", drying),
            )

        interval_decision = self._interval_decision(ctx, trace, step)
        if interval_decision:
            return interval_decision

        step("drying_conditions_missing", True, "AUTO_IDLE")
        return self._auto_idle(ctx, metrics, trace, "drying_conditions_not_met", drying)

    def _auto_idle(self, ctx, metrics, trace, reason, drying=None):
        if drying is None:
            drying = self._drying_conditions(ctx)

        details = {
            "reason": reason,
            "drying_conditions": drying,
            "sDefOut": ctx.sDefOut,
            "threshold": ctx.sdefMinThreshold,
            "tsDiff": ctx.tsSoll - ctx.tsMin if ctx.tsSoll is not None and ctx.tsMin is not None else None,
            "efficiency": metrics["efficiency"],
            "adaptive_threshold": ctx.min_efficiency_threshold,
            "humMax": ctx.humMax,
            "intervall_on": ctx.intervall_on,
            "remainingTimeInterval": ctx.remainingTimeInterval,
            "remainingTimeIntervalOn": ctx.remainingTimeIntervalOn,
            "remainingTimeIntervalDiff": ctx.remainingTimeIntervalDiff,
            "intervall_time": ctx.intervall_time,
            "intervall_duration": ctx.intervall_duration,
            "is_fan_on": ctx.is_fan_on,
            "fan_runtime_current": ctx.fan_runtime_current,
            "trace": trace,
            # Hysterese Debug
            "sdef_on": ctx.sdef_on,
            "sdef_hys_half": ctx.sdef_hys_half,
            "sdef_ein_schwelle": (
                round(ctx.sdef_on + ctx.sdef_hys_half, 2)
                if ctx.sdef_on is not None and ctx.sdef_hys_half is not None else None
            ),
            "sdefMinThreshold_ein": (
                round(ctx.sdefMinThreshold + ctx.sdef_hys_half, 2)
                if ctx.sdefMinThreshold is not None and ctx.sdef_hys_half is not None else None
            ),
        }
        if reason == "drying_delay":
            details["delay_remaining"] = ctx.venti_drying_delay_remaining
        return Decision("off", "AUTO_IDLE", details)

    def _drying_delay_active(self, ctx):
        return (ctx.venti_drying_delay_remaining or 0) > 0

    def _interval_decision(self, ctx, trace, step):
        # Intervall-Start zaehlt die echte AUS-Zeit seit letztem Hardware-OFF.
        # Dadurch startet Auto nach manuellem AUS nicht sofort wieder.
        interval_start_due = (
            not ctx.is_fan_on
            and ctx.remainingTimeIntervalOn is not None
            and ctx.intervall_time is not None
            and ctx.remainingTimeIntervalOn >= ctx.intervall_time
        )
        # Die laufende Intervallphase kommt aus dem Hardwarestatus: solange
        # der Luefter wirklich EIN ist und die Dauer nicht abgelaufen ist,
        # bleibt INTERVAL_ACTIVE aktiv.
        interval_running = (
            ctx.is_fan_on
            and ctx.fan_runtime_current is not None
            and ctx.intervall_duration is not None
            and ctx.fan_runtime_current <= ctx.intervall_duration
        )

        if (
            ctx.humMax is not None
            and ctx.intervall_on is not None
            and ctx.humMax > ctx.intervall_on
            and (interval_start_due or interval_running)
        ):
            step("interval_active", True, "INTERVAL_ACTIVE")
            runtime = ctx.fan_runtime_current if ctx.is_fan_on else 0
            return Decision(
                "on",
                "INTERVAL_ACTIVE",
                {
                    "humMax": ctx.humMax,
                    "threshold": ctx.intervall_on,
                    "interval_time": ctx.intervall_time,
                    "interval_duration": ctx.intervall_duration,
                    "since_last_on": ctx.remainingTimeInterval,
                    "remaining_off_time": ctx.remainingTimeIntervalOn,
                    "runtime": runtime,
                    "remaining": max(0, ctx.intervall_duration - runtime),
                    "trace": trace,
                },
            )

        return None

    def _drying_details(self, ctx, metrics, trace, phase, drying=None):
        # Keep all drying-related telemetry in one place so logs,
        # persistence, and notifications use the same payload shape.
        if drying is None:
            drying = self._drying_conditions(ctx)

        return {
            "sDefOut": ctx.sDefOut,
            "sDefMin": ctx.sDefMin,
            "sDefDiff": ctx.sDefOut - ctx.sDefMin if ctx.sDefOut is not None and ctx.sDefMin is not None else None,
            "tsMin": ctx.tsMin,
            "tsSoll": ctx.tsSoll,
            "tsDiff": ctx.tsSoll - ctx.tsMin if ctx.tsSoll is not None and ctx.tsMin is not None else None,
            "efficiency": metrics["efficiency"],
            "adaptive_threshold": ctx.min_efficiency_threshold,
            "drying_conditions": drying,
            "sdef_change_2h": metrics["sdef_gain"],
            "ts_change_2h": metrics["ts_gain"],
            "window_hours": metrics["window_hours"],
            "phase": phase,
            "trace": trace,
        }
