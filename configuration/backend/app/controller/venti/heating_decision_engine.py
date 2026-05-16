from .decision import Decision


class HeatingDecisionEngine:
    """
    Small, separate decision engine for the heater.
    Future heater rules (sDef, night window, outdoor temperature) belong here.
    """

    def decide(self, ctx):
        if ctx.heizung_manual_command == "on":
            return Decision("on", "HEIZUNG_MANUAL_ON", self._active_details(ctx))

        if ctx.heizung_manual_command == "off":
            if self._nachlauf_active(ctx):
                return self._nachlauf_decision(ctx, "off", "manual_off_nachlauf")

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

        heizung_active = (
            ctx.heizung_mode == "auto"
            and ctx.heizung_enabled
            and self._compute_active(ctx)
        )

        if heizung_active:
            return Decision("on", "HEIZUNG_ACTIVE", self._active_details(ctx))

        if self._nachlauf_active(ctx):
            return self._nachlauf_decision(ctx, ctx.heizung_mode)

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

        if self._sdef_delay_active(ctx):
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

        if self._sdef_limit_reached(ctx):
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

    def _compute_active(self, ctx):
        if ctx.heizung_manual_command == "on":
            return True

        if ctx.heizung_manual_command == "off":
            return False

        if ctx.heizung_mode == "on":
            return True

        if ctx.heizung_mode == "auto":
            if ctx.heizung_dauer > 0 and ctx.remainingTimeHeizung <= ctx.heizung_dauer:
                return True

            return self._compute_sdef_active(ctx)

        return False

    def _compute_sdef_active(self, ctx):
        limit = ctx.heizung_sdef_limit or 0

        if limit <= 0:
            return False

        if self._sdef_delay_active(ctx):
            return False

        if ctx.sDefOut is None:
            return bool(ctx.heizung_sdef_was_active)

        hys = max(0, ctx.heizung_sdef_hys or 0)

        if ctx.sDefOut >= limit:
            return False

        if ctx.sDefOut <= limit - hys:
            return True

        return bool(ctx.heizung_sdef_was_active)

    def _nachlauf_active(self, ctx):
        return ctx.heizung_nachlauf > 0 and ctx.heizung_off_since < ctx.heizung_nachlauf

    def _nachlauf_decision(self, ctx, heizung_mode, reason=None):
        details = {
            "heizung_mode": heizung_mode,
            "nachlauf_remaining": ctx.heizung_nachlauf - ctx.heizung_off_since,
            "heizung_nachlauf": ctx.heizung_nachlauf,
            "heizung_off_since": ctx.heizung_off_since,
            "venti_forced": True,
        }

        if reason is not None:
            details["reason"] = reason

        return Decision("off", "HEIZUNG_NACHLAUF", details)

    def _sdef_limit_reached(self, ctx):
        return (
            ctx.heizung_mode == "auto"
            and (ctx.heizung_sdef_limit or 0) > 0
            and ctx.remainingTimeHeizung > ctx.heizung_dauer
            and ctx.sDefOut is not None
            and ctx.sDefOut >= ctx.heizung_sdef_limit
        )

    def _sdef_delay_active(self, ctx):
        return (
            ctx.heizung_mode == "auto"
            and (ctx.heizung_sdef_limit or 0) > 0
            and ctx.remainingTimeHeizung > ctx.heizung_dauer
            and (ctx.heizung_sdef_delay_remaining or 0) > 0
        )

    def _active_details(self, ctx):
        return {
            "heizung_mode": ctx.heizung_manual_command or ctx.heizung_mode,
            "remaining": max(0, ctx.heizung_dauer - ctx.remainingTimeHeizung),
            "sDefOut": ctx.sDefOut,
            "heizung_sdef_limit": ctx.heizung_sdef_limit,
            "heizung_sdef_hys": ctx.heizung_sdef_hys,
            "venti_forced": True,
        }
