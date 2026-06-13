from ..decision import Decision
from .heating_metrics import HeatingMetricsCalculator


class HeatingDecisionEngine:
    """
    Separate Entscheidungs-Engine fuer die Heizung.

    Die Engine gibt nur die fachliche Entscheidung zurueck. Das eigentliche
    Schalten von Relais und das Setzen/Freigeben des Venti-Locks passiert im
    controller_Heizung. Neue Heizungsregeln gehoeren hier hinein, nicht in den
    Venti-Controller.
    """

    def __init__(self, metrics_calculator=None):
        self.metrics_calculator = metrics_calculator or HeatingMetricsCalculator()

    def compute_active(self, ctx):
        # Kleine Hilfsfunktion fuer controller_Heizung:
        # Dort wird vor der eigentlichen Decision die echte Aktiv-Flanke
        # benoetigt, damit Nachlauf und SDEF-Delay korrekt gestartet werden.
        return self.metrics_calculator.compute(ctx)["active"]

    def decide(self, ctx, metrics=None):
        # Metrics enthalten alle vorberechneten Teilbedingungen:
        # Dauerphase, SDEF-Bedarf, SDEF-Delay, Nachlauf usw.
        # Falls Tests fertige Metrics uebergeben, werden sie direkt genutzt.
        if metrics is None:
            metrics = self.metrics_calculator.compute(ctx)

        # Manuelle Befehle aus UI/Grafana haben Vorrang vor jeder Automatik.
        # AUS darf trotzdem den Nachlauf ausloesen, wenn die Heizung aktiv war.
        if ctx.heizung_manual_command == "on":
            return Decision("on", "HEIZUNG_MANUAL_ON", self._active_details(ctx))

        if ctx.heizung_manual_command == "off":
            if metrics["nachlauf_active"]:
                return self._nachlauf_decision(ctx, metrics, "off", "manual_off_nachlauf")

            return Decision(
                "off",
                "HEIZUNG_MANUAL_OFF",
                {
                    "heizung_mode": "off",
                    "reason": "manual_off",
                    "venti_forced": False,
                },
            )

        if ctx.heizung_mode == "on":
            # Parameter/Modus "on" ist wie manueller Dauerbetrieb zu behandeln.
            # Der Luefter wird spaeter ueber controller_Heizung mit erzwungen.
            return Decision("on", "HEIZUNG_MANUAL_ON", self._active_details(ctx))

        # Auto-Aktiv ist entweder eine feste Dauerphase oder SDEF-Bedarf.
        # Die Details der Berechnung liegen in HeatingMetricsCalculator.
        heizung_active = (
            ctx.heizung_mode == "auto"
            and ctx.heizung_enabled
            and metrics["active"]
        )

        if heizung_active:
            return Decision("on", "HEIZUNG_ACTIVE", self._active_details(ctx))

        # Nachlauf ist eine Luefter-Funktion nach Heizungsende:
        # Heizung aus, Luefter bleibt ueber controller_Heizung gesperrt/ein.
        if metrics["nachlauf_active"]:
            return self._nachlauf_decision(ctx, metrics, ctx.heizung_mode)

        if ctx.heizung_mode == "off":
            # Modus off ist ein expliziter Benutzer-/Parameterzustand und wird
            # separat von HEIZUNG_DISABLED protokolliert.
            return Decision(
                "off",
                "HEIZUNG_MANUAL_OFF",
                {
                    "heizung_mode": ctx.heizung_mode,
                    "reason": "manual_off",
                    "venti_forced": False,
                },
            )

        if not ctx.heizung_enabled:
            # Auto kann aktiv sein, aber die Heizungsfunktion global deaktiviert.
            # Dann bleibt die Heizung aus und erzwingt keinen Luefter.
            return Decision(
                "off",
                "HEIZUNG_DISABLED",
                {
                    "heizung_mode": ctx.heizung_mode,
                    "reason": "disabled",
                    "venti_forced": False,
                },
            )

        # SDEF-Delay blockiert erneutes Einschalten nach erreichtem Limit.
        # Der Delay wird vom StateManager gestartet, wenn die Heizung nach
        # Erreichen des SDEF-Limits ausgeht. Hier wird nur ausgewertet.
        if metrics["sdef_delay_active"]:
            return Decision(
                "off",
                "HEIZUNG_SDEF_LIMIT",
                {
                    "heizung_mode": ctx.heizung_mode,
                    "delay_remaining": ctx.heizung_sdef_delay_remaining,
                    "sDefOut": ctx.sDefOut,
                    "heizung_sdef_limit": ctx.heizung_sdef_limit,
                    "heizung_sdef_hys": ctx.heizung_sdef_hys,
                    "reason": "sdef_delay",
                    "venti_forced": False,
                },
            )

        # Expliziter Limit-Zustand: fachlich hilfreich fuer Logs/Timeline,
        # auch wenn das Kommando wie HEIZUNG_IDLE "off" ist.
        # Ohne diesen Zustand waere spaeter nicht erkennbar, ob "aus" normal
        # idle war oder vom SDEF-Limit verursacht wurde.
        if metrics["sdef_limit_reached"]:
            return Decision(
                "off",
                "HEIZUNG_SDEF_LIMIT",
                {
                    "heizung_mode": ctx.heizung_mode,
                    "sDefOut": ctx.sDefOut,
                    "heizung_sdef_limit": ctx.heizung_sdef_limit,
                    "heizung_sdef_hys": ctx.heizung_sdef_hys,
                    "reason": "sdef_limit_reached",
                    "venti_forced": False,
                },
            )

        return Decision(
            "off",
            "HEIZUNG_IDLE",
            {
                "heizung_mode": ctx.heizung_mode,
                "reason": "idle",
                "venti_forced": False,
            },
        )

    def _nachlauf_decision(self, ctx, metrics, heizung_mode, reason=None):
        # Nachlauf bedeutet: Heizung selbst AUS, aber Venti bleibt fuer die
        # eingestellte Nachlaufzeit erzwungen EIN. Deshalb command="off" fuer
        # die Heizung, aber venti_forced=True fuer den Controller.
        details = {
            "heizung_mode": heizung_mode,
            "nachlauf_remaining": metrics["nachlauf_remaining"],
            "heizung_nachlauf": ctx.heizung_nachlauf,
            "heizung_off_since": ctx.heizung_off_since,
            "venti_forced": True,
        }

        if reason is not None:
            details["reason"] = reason

        return Decision("off", "HEIZUNG_NACHLAUF", details)

    def _active_details(self, ctx):
        # Gemeinsame Details fuer manuell/automatisch aktive Heizung.
        # remaining ist die Restdauer der Dauerphase; bei SDEF-Betrieb kann
        # der Wert 0 sein, die SDEF-Felder erklaeren dann den Heizgrund.
        return {
            "heizung_mode": ctx.heizung_manual_command or ctx.heizung_mode,
            "remaining": max(0, ctx.heizung_dauer - ctx.remainingTimeHeizung),
            "sDefOut": ctx.sDefOut,
            "heizung_sdef_limit": ctx.heizung_sdef_limit,
            "heizung_sdef_hys": ctx.heizung_sdef_hys,
            "venti_forced": True,
        }
