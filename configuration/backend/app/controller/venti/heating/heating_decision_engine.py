from ..decision import Decision
from .heating_metrics import HeatingMetricsCalculator


class HeatingDecisionEngine:
    """
    Small, separate decision engine for the heater.
    Future heater rules (sDef, night window, outdoor temperature) belong here.
    """

    def __init__(self, metrics_calculator=None):
        self.metrics_calculator = metrics_calculator or HeatingMetricsCalculator()

    def compute_active(self, ctx):
        return self.metrics_calculator.compute(ctx)["active"]

    def decide(self, ctx, metrics=None):
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
            return Decision("on", "HEIZUNG_MANUAL_ON", self._active_details(ctx))

        # Auto-Aktiv ist entweder eine feste Dauerphase oder SDEF-Bedarf.
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
        return {
            "heizung_mode": ctx.heizung_manual_command or ctx.heizung_mode,
            "remaining": max(0, ctx.heizung_dauer - ctx.remainingTimeHeizung),
            "sDefOut": ctx.sDefOut,
            "heizung_sdef_limit": ctx.heizung_sdef_limit,
            "heizung_sdef_hys": ctx.heizung_sdef_hys,
            "venti_forced": True,
        }
