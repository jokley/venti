class DryingMetricsCalculator:
    def __init__(self, ts_weight=0.3):
        self.default_ts_weight = ts_weight

    def compute(self, ctx):
        """
        Zentrales Rechenmodell fuer die Trocknungsautomatik.

        Diese Klasse berechnet nur abgeleitete Werte und fachliche
        Zwischenentscheidungen. Sie schaltet nichts selbst. Die eigentliche
        Entscheidung, ob der Luefter ein- oder ausgeschaltet wird, trifft
        danach die DryingDecisionEngine anhand dieser Kennzahlen.
        """
        metrics = self._efficiency(ctx)
        metrics["ts_diff"] = self._ts_diff(ctx)
        metrics["sdef_diff"] = self._sdef_diff(ctx)
        metrics["drying_conditions"] = self._drying_conditions(ctx)
        metrics["near_efficiency_endphase"] = self._near_efficiency_endphase(ctx, metrics)
        return metrics

    def _efficiency(self, ctx):
        # Effizienz betrachtet die Veraenderung in einem Rueckblickfenster
        # (standardmaessig 2h). SDEF ist das Hauptsignal fuer Trocknung,
        # TS wird geringer gewichtet, damit Temperaturfortschritt hilft,
        # aber den Feuchtefortschritt nicht ueberstimmt.
        window_seconds = ctx.efficiency_window or 0

        if window_seconds <= 0:
            # Ohne gueltiges Zeitfenster kann keine Effizienz berechnet werden.
            # Wir liefern trotzdem vollstaendige Default-Metrics, damit die
            # Decision-Engine keine Sonderbehandlung fuer fehlende Keys braucht.
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

        # Ohne vollstaendige Historie darf die Effizienz NICHT zum Abschalten
        # verwendet werden. has_history=False verhindert genau diese Regel,
        # waehrend alle Anzeige-/Log-Felder weiterhin gefuellt bleiben.
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

        # Aktuelle Innen-/Trocknungswerte werden gegen historische Werte aus
        # derselben Messquelle verglichen. Wichtig: sDefOut ist das
        # Aussen-/Triggersignal und darf nicht mit den historischen
        # Innenwerten vermischt werden.
        sdef_gain = ctx.sDefMin - ctx.sDef_2h_ago
        ts_gain = ctx.tsMin - ctx.ts_2h_ago

        # weighted_gain ist der eigentliche Fortschritt pro Fenster:
        # - sdef_gain zaehlt voll
        # - ts_gain zaehlt nur mit ts_weight
        # Daraus entsteht efficiency = Fortschritt pro Stunde.
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
        # Positive Werte bedeuten: tsMin liegt noch unter tsSoll, es ist also
        # noch Abstand zum Ziel vorhanden. Kleine/negative Werte bedeuten
        # Zielnaehe bzw. Ziel erreicht.
        if ctx.tsSoll is None or ctx.tsMin is None:
            return None
        return ctx.tsSoll - ctx.tsMin

    def _sdef_diff(self, ctx):
        # Differenz zwischen Aussen-/Trigger-SDEF und Innen-/Minimum-SDEF.
        # Positive Werte sprechen fuer moegliches Trocknungspotenzial.
        if ctx.sDefOut is None or ctx.sDefMin is None:
            return None
        return ctx.sDefOut - ctx.sDefMin

    def _near_efficiency_endphase(self, ctx, metrics):
        # Die Effizienzabschaltung soll erst nahe am TS-Ziel greifen.
        # Sonst koennte ein schlechter kurzfristiger Verlauf einen sinnvollen
        # Trocknungsstart zu frueh abbrechen.
        ts_diff = metrics.get("ts_diff")
        ts_margin = getattr(ctx, "efficiency_endphase_ts_margin", None)
        return (
            ts_diff is not None
            and ts_margin is not None
            and ts_margin > 0
            and ts_diff < ts_margin
        )

    def _drying_conditions(self, ctx):
        # Vollstaendige Hysterese fuer die Trocknungsfreigabe:
        # - Luefter AUS: Start nur bei "strengeren" EIN-Schwellen.
        # - Luefter EIN: Weiterlaufen bis zu "lockereren" AUS-Schwellen.
        # Dadurch flattert der Luefter nicht um Grenzwerte herum.
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
        # SDEF muss beide Bedingungen erfuellen:
        # 1) genug Abstand zu sdefMinThreshold
        # 2) genug Abstand zu sdef_on
        # TS muss gleichzeitig unter/innerhalb seiner Hysterese-Schwelle sein.
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
        # Alle Werte, die fuer die Hystereseentscheidung benoetigt werden,
        # muessen vorhanden sein. Fehlt ein Wert, wird nicht "optimistisch"
        # gestartet, sondern kontrolliert auf unavailable/False entschieden.
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
        # Hysterese-Richtung haengt vom aktuellen Hardwarezustand ab:
        # Beim laufenden Luefter werden die Schwellen entspannt, damit ein
        # sinnvoller Lauf nicht wegen minimaler Messwertbewegung abbricht.
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
        # Kleine, stabile Reason-Codes fuer Logs, Persistenz und Tests.
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
        # Einheitliches Ergebnisobjekt: Die Decision-Engine bekommt nicht nur
        # True/False, sondern auch Phase, Einzelgruende und Schwellen fuer
        # Diagnose im Frontend/Grafana.
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
