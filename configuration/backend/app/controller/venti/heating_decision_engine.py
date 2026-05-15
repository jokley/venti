from .decision import Decision


class HeatingDecisionEngine:
    """
    Small, separate decision engine for the heater.
    Future heater rules (sDef, night window, outdoor temperature) belong here.
    """

    def decide(self, ctx):
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

        heizung_active = self._compute_active(ctx)

        if heizung_active:
            return Decision(
                "on",
                "HEIZUNG_ACTIVE",
                {
                    "heizung_mode": ctx.heizung_mode,
                    "remaining": max(0, ctx.heizung_dauer - ctx.remainingTimeHeizung),
                    "venti_forced": True,
                },
            )

        if ctx.heizung_nachlauf > 0 and ctx.heizung_off_since < ctx.heizung_nachlauf:
            return Decision(
                "off",
                "HEIZUNG_NACHLAUF",
                {
                    "heizung_mode": ctx.heizung_mode,
                    "nachlauf_remaining": ctx.heizung_nachlauf - ctx.heizung_off_since,
                    "heizung_nachlauf": ctx.heizung_nachlauf,
                    "heizung_off_since": ctx.heizung_off_since,
                    "venti_forced": True,
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

    def _compute_active(self, ctx):
        if ctx.heizung_mode == "on":
            return True

        if ctx.heizung_mode == "auto":
            return ctx.remainingTimeHeizung <= ctx.heizung_dauer

        return False
