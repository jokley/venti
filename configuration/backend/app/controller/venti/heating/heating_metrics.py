class HeatingMetricsCalculator:
    def compute(self, ctx):
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
        # This mirrors the old HeatingDecisionEngine._compute_active() helper.
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
        return (
            ctx.heizung_mode == "auto"
            and ctx.heizung_dauer > 0
            and ctx.remainingTimeHeizung <= ctx.heizung_dauer
        )

    def _sdef_active(self, ctx, sdef_delay_active):
        if ctx.heizung_mode != "auto":
            return False

        limit = ctx.heizung_sdef_limit or 0

        if limit <= 0:
            return False

        if sdef_delay_active:
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

    def _nachlauf_remaining(self, ctx):
        return ctx.heizung_nachlauf - ctx.heizung_off_since

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
