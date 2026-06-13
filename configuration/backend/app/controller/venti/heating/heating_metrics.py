class HeatingMetricsCalculator:
    def compute(self, ctx):
        # Zentrale Vorberechnung fuer die HeatingDecisionEngine.
        # Hier werden nur boolesche Teilbedingungen und Restzeiten berechnet;
        # die finale fachliche Entscheidung bleibt in heating_decision_engine.py.
        duration_active = self._duration_active(ctx)
        sdef_delay_active = self._sdef_delay_active(ctx)
        sdef_active = self._sdef_active(ctx, sdef_delay_active)
        active = self._active(ctx, duration_active, sdef_active)
        nachlauf_active = self._nachlauf_active(ctx)

        return {
            "active": active,
            "sdef_active": sdef_active,
            "sdef_delay_active": sdef_delay_active,
            "sdef_limit_reached": self._sdef_limit_reached(ctx),
            "nachlauf_active": nachlauf_active,
            "nachlauf_remaining": self._nachlauf_remaining(ctx) if nachlauf_active else 0,
            "duration_active": duration_active,
        }

    def _active(self, ctx, duration_active, sdef_active):
        # Zusammenfassung der Aktivgruende:
        # - manuell on erzwingt aktiv
        # - manuell off sperrt aktiv
        # - Modus on erzwingt aktiv
        # - Auto ist aktiv, wenn Dauerphase oder SDEF-Bedarf aktiv ist
        # Diese Funktion spiegelt bewusst den alten _compute_active()-Helper.
        if ctx.heizung_manual_command == "on":
            return True

        if ctx.heizung_manual_command == "off":
            return False

        if ctx.heizung_mode == "on":
            return True

        if ctx.heizung_mode == "auto":
            return duration_active or sdef_active

        return False

    def _duration_active(self, ctx):
        # Feste Heizdauer im Auto-Modus:
        # remainingTimeHeizung ist die bisherige Laufzeit seit Heizungsstart.
        # Solange sie kleiner/gleich heizung_dauer ist, bleibt die Dauerphase an.
        return (
            ctx.heizung_mode == "auto"
            and ctx.heizung_dauer > 0
            and ctx.remainingTimeHeizung <= ctx.heizung_dauer
        )

    def _sdef_active(self, ctx, sdef_delay_active):
        # SDEF-Automatik:
        # - nur im Auto-Modus
        # - nur bei gesetztem heizung_sdef_limit
        # - nicht waehrend SDEF-Restart-Delay
        # - mit Hysterese, damit die Heizung nicht am Grenzwert flattert
        if ctx.heizung_mode != "auto":
            return False

        limit = ctx.heizung_sdef_limit or 0

        if limit <= 0:
            return False

        if sdef_delay_active:
            return False

        if ctx.sDefOut is None:
            # Wenn der aktuelle Sensorwert fehlt, behalten wir den letzten
            # bekannten SDEF-Aktivzustand bei. So schaltet ein kurz fehlender
            # Messwert die Heizung nicht abrupt aus/ein.
            return bool(ctx.heizung_sdef_was_active)

        hys = max(0, ctx.heizung_sdef_hys or 0)

        if ctx.sDefOut >= limit:
            # Limit erreicht oder ueberschritten: kein weiterer SDEF-Heizbedarf.
            return False

        if ctx.sDefOut <= limit - hys:
            # Erst unterhalb limit - Hysterese wird wieder eingeschaltet.
            return True

        # Zwischen den Hysteresegrenzen bleibt der vorherige Zustand erhalten.
        return bool(ctx.heizung_sdef_was_active)

    def _nachlauf_active(self, ctx):
        # Nachlauf ist aktiv, wenn nach Heizungsende noch nicht die komplette
        # heizung_nachlauf-Zeit vergangen ist. In dieser Phase erzwingt der
        # Heizungscontroller nur den Luefter, nicht die Heizung selbst.
        return ctx.heizung_nachlauf > 0 and ctx.heizung_off_since < ctx.heizung_nachlauf

    def _nachlauf_remaining(self, ctx):
        # Restzeit fuer Logs/UI. Wird nur verwendet, wenn _nachlauf_active True ist.
        return ctx.heizung_nachlauf - ctx.heizung_off_since

    def _sdef_limit_reached(self, ctx):
        # Separater Diagnosezustand fuer "Heizung aus, weil SDEF-Limit erreicht".
        # remainingTimeHeizung > heizung_dauer verhindert, dass die feste
        # Anfangsdauer faelschlich als Limit-Abschaltung interpretiert wird.
        return (
            ctx.heizung_mode == "auto"
            and (ctx.heizung_sdef_limit or 0) > 0
            and ctx.remainingTimeHeizung > ctx.heizung_dauer
            and ctx.sDefOut is not None
            and ctx.sDefOut >= ctx.heizung_sdef_limit
        )

    def _sdef_delay_active(self, ctx):
        # Restart-Sperre nach einer SDEF-Limit-Abschaltung. Auch hier gilt:
        # Die feste Dauerphase hat Vorrang, deshalb greift der Delay erst
        # nachdem remainingTimeHeizung groesser als heizung_dauer ist.
        return (
            ctx.heizung_mode == "auto"
            and (ctx.heizung_sdef_limit or 0) > 0
            and ctx.remainingTimeHeizung > ctx.heizung_dauer
            and (ctx.heizung_sdef_delay_remaining or 0) > 0
        )
