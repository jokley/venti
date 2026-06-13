from ..decision import Decision
from ..control.state_manager import state_manager
from .drying_metrics import DryingMetricsCalculator


class DryingDecisionEngine:
    def __init__(self, metrics_calculator=None):
        self.metrics_calculator = metrics_calculator or DryingMetricsCalculator()

    def evaluate(self, ctx, previous_state=None):
        # Einstieg fuer den Controller:
        # 1) statischen Mindestwirkungsgrad aus dem Context setzen
        # 2) alle Kennzahlen berechnen
        # 3) Entscheidung inklusive Diagnosefeldern zurueckgeben
        ctx.min_efficiency_threshold = ctx.base_min_efficiency_threshold
        metrics = self.metrics_calculator.compute(ctx)
        decision = self.decide(ctx, metrics, previous_state=previous_state)
        self._append_metric_details(decision, metrics, ctx)
        return decision

    def decide(self, ctx, metrics=None, previous_state=None):
        # Tests koennen Teil-Metrics uebergeben. Fehlende abgeleitete Werte
        # werden hier nachberechnet, damit die Entscheidungslogik immer mit
        # demselben vollstaendigen Metrics-Objekt arbeitet.
        if metrics is None:
            metrics = self.metrics_calculator.compute(ctx)
        elif any(key not in metrics for key in ("drying_conditions", "ts_diff", "sdef_diff", "near_efficiency_endphase")):
            metrics = self._complete_metrics(ctx, metrics)
        decision = self._decide_base(ctx, metrics, previous_state=previous_state)
        decision = self._apply_auto_disable(ctx, decision, metrics)
        decision = self._apply_drying_delay_start(ctx, decision, previous_state)
        return decision


    def _complete_metrics(self, ctx, metrics):
        computed = self.metrics_calculator.compute(ctx)
        computed.update(metrics)
        return computed

    def _append_metric_details(self, decision, metrics, ctx):
        # Jede Decision bekommt die wichtigsten Kennzahlen fuer Persistenz,
        # Logs und UI. setdefault erhaelt explizite Detailwerte der jeweiligen
        # Regel, falls diese bereits genauer gefuellt wurden.
        decision.details.setdefault("efficiency", metrics["efficiency"])
        decision.details.setdefault("min_efficiency_threshold", ctx.min_efficiency_threshold)
        decision.details.setdefault("sdef_change_2h", metrics["sdef_gain"])
        decision.details.setdefault("ts_change_2h", metrics["ts_gain"])
        decision.details.setdefault("window_hours", metrics["window_hours"])

    def _decide_base(self, ctx, metrics,previous_state=None):
        trace = []

        def step(name, matched, reason=None):
            # Trace ist die fachliche Breadcrumb-Liste: Sie zeigt spaeter,
            # welche Regel gegriffen hat bzw. warum ein Zweig verlassen wurde.
            trace.append({
                "step": name,
                "matched": matched,
                "reason": reason,
            })

        # Globale Entscheidungsreihenfolge:
        # 1. Manuelle Modi
        # 2. Heizung aktiv / Nachlauf
        # 3. Ueberhitzungsschutz
        # 4. Stockaufbau
        # 5. Trocknungslogik
        # 6. Intervalllueftung
        # 7. Idle-Fallback
        # Fruehere Treffer gewinnen. Dadurch kann z.B. Ueberhitzung oder
        # Heizung den normalen Trocknungs- und Intervallzweig uebersteuern.

        if ctx.mode == "on":
            # Manueller EIN-Modus ist ein direkter Benutzerwunsch und wird
            # nicht durch Automatik, Effizienz oder Intervall ueberstimmt.
            step("manual_on", True, "VENTI_MANUAL_ON")
            return Decision(
                "on",
                "VENTI_MANUAL_ON",
                {
                    "mode": ctx.mode,
                    "runtime": ctx.remainingTimeInterval,
                    "tsDiff": metrics.get("ts_diff"),
                    "trace": trace,
                },
            )

        if ctx.mode != "auto":
            # Alles ausser auto/on bedeutet fachlich AUS. Der Luefter bleibt
            # aus, solange keine externe Heizungssperre vorher gegriffen hat.
            step("manual_off", True, "VENTI_MANUAL_OFF")
            return Decision(
                "off",
                "VENTI_MANUAL_OFF",
                {
                    "mode": ctx.mode,
                    "runtime": ctx.remainingTimeInterval,
                    "tsDiff": metrics.get("ts_diff"),
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

        if self._is_overheat(ctx, previous_state=previous_state):
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

        return self._decide_classic(ctx, metrics, trace, step, previous_state=previous_state)


    def _apply_auto_disable(self, ctx, decision, metrics):
        # Sicherheitsausstieg fuer lange, wirkungslose Automatikphasen:
        # Wenn Auto seit laengerem AUS ist und TS praktisch am Ziel liegt,
        # liefert die Engine nur den Mode-Override. venti_auto() bleibt als
        # Seiteneffekt bewusst im Controller.
        # remainingTimeIntervalOn ist hier die relevante AUS-Zeit seit dem
        # letzten Hardware-OFF. remainingTimeInterval waere die falsche Basis,
        # weil es nicht die aktuelle Off-Dauer beschreibt.
        auto_disable_triggered = (
            ctx.mode == "auto"
            and decision.command == "off"
            and ctx.remainingTimeStock is not None
            and ctx.stock is not None
            and ctx.remainingTimeStock > ctx.stock
            and not ctx.is_fan_on
            and ctx.remainingTimeIntervalOn is not None
            and ctx.remainingTimeIntervalOn >= 7200
            and metrics.get("ts_diff") is not None
            and metrics["ts_diff"] <= 0.5
        )

        if not auto_disable_triggered:
            return decision

        details = {
            "runtime": ctx.remainingTimeInterval,
            "tsDiff": metrics.get("ts_diff"),
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
        # Der Venti-Drying-Delay startet erst NACH einem echten Trocknungslauf,
        # wenn die neue Entscheidung wegen fehlender/ineffizienter Trocknung
        # auf AUS faellt. Er ist eine Restart-Sperre, kein Mindestlaufzeit-Timer.
        should_start_delay = (
            ctx.mode == "auto"
            and previous_state == "DRYING_ACTIVE"
            and decision.reason in ("AUTO_IDLE", "INEFFICIENT_DRYING") 
            and (decision.details or {}).get("reason") in (
                "drying_conditions_not_met",
                "inefficient_near_target",
                None,
            )
        )
    
        if not should_start_delay:
            return decision
    
        state_manager.start_venti_drying_delay(ctx)
        decision.details["delay_remaining"] = (
            state_manager.get_venti_drying_delay_remaining(ctx.now)
        )
        decision.details["delay_started"] = True
        return decision

    def _is_overheat(self, ctx, previous_state=None):
        # Ueberhitzung nutzt eine einfache Hysterese:
        # - sofort EIN ab uschutz_on
        # - wenn vorher OVERHEAT aktiv war, erst wieder frei geben, wenn
        #   tempMax um uschutz_hys unter die Schwelle gefallen ist.
        if ctx.tempMax is None or ctx.uschutz_on is None:
            return False
        if ctx.tempMax >= ctx.uschutz_on:
            return True
        if (
            previous_state == "OVERHEAT"
            and ctx.uschutz_hys is not None
            and ctx.tempMax + ctx.uschutz_hys >= ctx.uschutz_on
        ):
            return True
        return False

    def _decide_classic(self, ctx, metrics, trace, step, previous_state=None):
        # Klassische Trocknungsautomatik:
        # - Sind Trocknungsbedingungen gut, laeuft DRYING_ACTIVE.
        # - Wenn kein Trocknungslauf sinnvoll ist, darf Intervall pruefen.
        # - Wenn nichts greift, bleibt AUTO_IDLE.
        # SDef-/TS-Hysterese kommt vorbereitet aus den Metrics:
        # EIN bei oberer Schwelle, Weiterlaufen bis untere Schwelle.
        drying = metrics["drying_conditions"]
        if drying["met"]:
            if self._drying_delay_active(ctx):
                # Nach einem beendeten Trocknungslauf blockiert der Delay nur
                # erneutes DRYING_ACTIVE. Intervall darf trotzdem laufen.
                interval_decision = self._interval_decision(ctx, trace, step, previous_state=previous_state)
                if interval_decision:
                    return interval_decision
                step("drying_delay", True, "AUTO_IDLE")
                return self._auto_idle(ctx, metrics, trace, "drying_delay", drying)
    
            if self._inefficient_near_target(ctx, metrics):
                # Effizienzstopp nur nahe am TS-Ziel und erst nach Mindestlaufzeit.
                # So wird nicht ein frischer, noch sinnvoller Lauf abgebrochen.
                step("low_efficiency_near_target", True, "INEFFICIENT_DRYING")
                return Decision(
                    "off",
                    "INEFFICIENT_DRYING",
                    {
                        **self._drying_details(ctx, metrics, trace, "inefficient_near_target", drying),
                        "runtime": ctx.fan_runtime_current,
                        "weighted_gain": metrics["weighted_gain"],
                    },
                )

            step("drying_active", True, "DRYING_ACTIVE")
            return Decision(
                "on",
                "DRYING_ACTIVE",
                self._drying_details(ctx, metrics, trace, "legacy_drying", drying),
            )
    
        interval_decision = self._interval_decision(ctx, trace, step, previous_state=previous_state)
        if interval_decision:
            return interval_decision
    
        # Ziel erreicht – tsMin hat tsSoll + ts_hys_half überschritten.
        # SDefOut Checks entfallen hier, da die Metrics die Hysterese bereits
        # als drying_conditions abbilden.
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


    def _inefficient_near_target(self, ctx, metrics):
        # Ineffizienz ist bewusst streng:
        # - Luefter muss aktuell laufen
        # - Historie muss vollstaendig sein
        # - Mindestlaufzeit verhindert zu fruehe Bewertung
        # - Effizienz liegt unter Grenzwert
        # - TS ist bereits in der Endphase
        threshold = ctx.min_efficiency_threshold
        min_runtime = getattr(ctx, "efficiency_min_runtime", 1800)
        sufficient_runtime = (
            ctx.fan_runtime_current is not None
            and ctx.fan_runtime_current >= min_runtime
        )
    
        return (
            ctx.is_fan_on
            and metrics["has_history"]
            and sufficient_runtime                   # ← NEU
            and threshold is not None
            and threshold > 0
            and metrics["efficiency"] < threshold
            and metrics["near_efficiency_endphase"]
        )

    def _auto_idle(self, ctx, metrics, trace, reason, drying=None):
        # Gemeinsamer AUTO_IDLE-Payload fuer alle AUS-Gruende. Dadurch haben
        # Logs, Persistenz und Grafana immer dieselben Diagnosefelder, egal
        # welcher konkrete Idle-Zweig erreicht wurde.
        if drying is None:
            drying = metrics["drying_conditions"]

        details = {
            "reason": reason,
            "drying_conditions": drying,
            "sDefOut": ctx.sDefOut,
            "threshold": ctx.sdefMinThreshold,
            "tsDiff": metrics.get("ts_diff"),
            "efficiency": metrics["efficiency"],
            "min_efficiency_threshold": ctx.min_efficiency_threshold,
            "humMax": ctx.humMax,
            "intervall_on": ctx.intervall_on,
            "remainingTimeInterval": ctx.remainingTimeInterval,
            "remainingTimeIntervalOn": ctx.remainingTimeIntervalOn,
            "remainingTimeIntervalDiff": ctx.remainingTimeIntervalDiff,
            "intervall_time": ctx.intervall_time,
            "intervall_duration": ctx.intervall_duration,
            "is_fan_on": ctx.is_fan_on,
            "fan_runtime_current": ctx.fan_runtime_current,
            "venti_post_heizung_delay_remaining": ctx.venti_post_heizung_delay_remaining,
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
        # Aktiver Restart-Delay nach beendeter Trocknung. Dieser blockiert nur
        # neue DRYING_ACTIVE-Starts; Intervall darf separat entscheiden.
        return (ctx.venti_drying_delay_remaining or 0) > 0

    def _interval_decision(self, ctx, trace, step, previous_state=None):
        # Nach Heizungsende verhindert der Post-Heizung-Delay einen sofortigen
        # Intervall-Neustart. Die Heizung/Nachlauf-Phase hat den Luefter zuvor
        # bereits erzwungen; danach soll Intervall nicht direkt wieder ziehen.
        if (ctx.venti_post_heizung_delay_remaining or 0) > 0:
            step("post_heizung_delay", True, "AUTO_IDLE")
            return None
    
        # Intervall ist ein Pausen-Programm: Es darf erst NACH AUTO_IDLE und
        # nach Ablauf der eingestellten Wartezeit starten. Ein direkter Wechsel
        # von DRYING_ACTIVE nach INTERVAL_ACTIVE ist fachlich falsch, weil der
        # Intervall nur schlechte Aussenluft in Lueftungspausen ueberbruecken
        # soll und keinen Trocknungslauf verlaengern darf.
        interval_wait_elapsed = (
            ctx.remainingTimeIntervalOn is not None
            and ctx.intervall_time is not None
            and ctx.remainingTimeIntervalOn >= ctx.intervall_time
        )
        interval_start_due = (
            previous_state == "AUTO_IDLE"
            and not ctx.is_fan_on
            and interval_wait_elapsed
        )

        # Nur ein bereits bestehender INTERVAL_ACTIVE-State darf weiterlaufen.
        # Dessen Laufzeit wird ueber den State-Start gemessen, nicht ueber
        # beliebige vorherige Hardware-Laufzeit.
        interval_runtime = self._interval_runtime(ctx, previous_state)
        interval_running = (
            previous_state == "INTERVAL_ACTIVE"
            and ctx.is_fan_on
            and ctx.intervall_duration is not None
            and interval_runtime <= ctx.intervall_duration
        )
    
        if (
            ctx.humMax is not None
            and ctx.intervall_on is not None
            and ctx.humMax > ctx.intervall_on
            and (interval_start_due or interval_running)
        ):
            step("interval_active", True, "INTERVAL_ACTIVE")
            runtime = interval_runtime if interval_running else 0
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

    def _interval_runtime(self, ctx, previous_state):
        # Bevorzugt wird die State-Laufzeit seit Beginn von INTERVAL_ACTIVE.
        # Nur wenn diese State-Zeit nicht verfuegbar ist, faellt die Engine fuer
        # bestehende Intervalllaeufe auf die Hardware-Laufzeit zurueck.
        if (
            previous_state == "INTERVAL_ACTIVE"
            and ctx.now is not None
            and ctx.previous_state_started_at is not None
        ):
            return max(0, int(ctx.now - ctx.previous_state_started_at))

        return ctx.fan_runtime_current or 0

    def _drying_details(self, ctx, metrics, trace, phase, drying=None):
        # Gemeinsamer DRYING_ACTIVE-/INEFFICIENT-Payload. Alle Trocknungswerte
        # bleiben an einer Stelle, damit Logs, Persistenz und Benachrichtigungen
        # dieselbe Bedeutung der Felder verwenden.
        if drying is None:
            drying = metrics["drying_conditions"]

        return {
            "sDefOut": ctx.sDefOut,
            "sDefMin": ctx.sDefMin,
            "sDefDiff": metrics.get("sdef_diff"),
            "tsMin": ctx.tsMin,
            "tsSoll": ctx.tsSoll,
            "tsDiff": metrics.get("ts_diff"),
            "efficiency": metrics["efficiency"],
            "min_efficiency_threshold": ctx.min_efficiency_threshold,
            "drying_conditions": drying,
            "sdef_change_2h": metrics["sdef_gain"],
            "ts_change_2h": metrics["ts_gain"],
            "window_hours": metrics["window_hours"],
            "phase": phase,
            "trace": trace,
        }
