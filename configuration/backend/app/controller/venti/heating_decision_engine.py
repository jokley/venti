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
                    "sDefOut": ctx.sDefOut,
                    "heizung_sdef_limit": ctx.heizung_sdef_limit,
                    "heizung_sdef_hys": ctx.heizung_sdef_hys,
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
                    "lockout_remaining": ctx.heizung_sdef_lockout_remaining,
                    "sdef_lockout": (ctx.heizung_sdef_lockout_remaining or 0) > 0,
                    "venti_forced": True,
                },
            )

        if self._sdef_lockout_active(ctx):
            return Decision(
                "off",
                "HEIZUNG_SDEF_LOCKOUT",
                {
                    "heizung_mode": ctx.heizung_mode,
                    "lockout_remaining": ctx.heizung_sdef_lockout_remaining,
                    "sDefOut": ctx.sDefOut,
                    "heizung_sdef_limit": ctx.heizung_sdef_limit,
                    "heizung_sdef_hys": ctx.heizung_sdef_hys,
                    "reason": "sdef_lockout",
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
        if ctx.heizung_mode == "on":
            return True

        if ctx.heizung_mode == "auto":
            if ctx.remainingTimeHeizung <= ctx.heizung_dauer:
                return True

            return self._compute_sdef_active(ctx)

        return False

    def _compute_sdef_active(self, ctx):
        limit = ctx.heizung_sdef_limit or 0

        if limit <= 0:
            return False

        if self._sdef_lockout_active(ctx):
            return False

        if ctx.sDefOut is None:
            return bool(ctx.heizung_sdef_was_active)

        hys = max(0, ctx.heizung_sdef_hys or 0)

        if ctx.sDefOut >= limit:
            return False

        if ctx.sDefOut <= limit - hys:
            return True

        return bool(ctx.heizung_sdef_was_active)

    def _sdef_limit_reached(self, ctx):
        return (
            ctx.heizung_mode == "auto"
            and (ctx.heizung_sdef_limit or 0) > 0
            and ctx.remainingTimeHeizung > ctx.heizung_dauer
            and ctx.sDefOut is not None
            and ctx.sDefOut >= ctx.heizung_sdef_limit
        )

    def _sdef_lockout_active(self, ctx):
        return (
            ctx.heizung_mode == "auto"
            and (ctx.heizung_sdef_limit or 0) > 0
            and ctx.remainingTimeHeizung > ctx.heizung_dauer
            and (ctx.heizung_sdef_lockout_remaining or 0) > 0
        )
