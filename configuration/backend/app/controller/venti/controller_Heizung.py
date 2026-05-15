from .context import VentiContext
from app.services.control_data import build_control_data
from app.services.venti_service import heizung_cmd, heizung_venti_cmd
from .control.state_manager import state_manager
from .heating_decision_engine import HeatingDecisionEngine
from app.notifications.transitions import TransitionDetector
from app.events.event_bus import event_bus, EventType, Event
from app.utils.logger import logger


heating_engine = HeatingDecisionEngine()
heizung_detector = TransitionDetector()


def heizung_control():
    """
    Eigenständiger Scheduler Job – läuft immer, unabhängig vom
    Lüfter-Modus (on / off / auto).

    Verantwortlichkeiten:
    - RO2 (Heizung) schalten
    - RO1 (Lüfter) zwingen wenn Heizung oder Nachlauf aktiv (Variante A)
    - heizung_lock setzen/freigeben → sperrt venti_control solange nötig
    - heizung_off_ts nach Nachlaufende zurücksetzen
    """
    try:
        data = build_control_data()
        ctx = VentiContext(data)

        # First pass: detect active heating and update off timestamp on falling edge.
        heizung_active = heating_engine._compute_active(ctx) if ctx.heizung_enabled else False
        ctx.heizung_active = heizung_active

        # Flanke EIN→AUS erkennen, heizung_off_ts setzen,
        # heizung_was_active aktualisieren
        state_manager.update_heizung(heizung_active, ctx)

        # heizung_off_since NACH update_heizung() berechnen
        # damit ein soeben gesetztes heizung_off_ts sofort wirkt
        ctx.heizung_off_since = (
            int(ctx.now - state_manager.heizung_off_ts)
            if state_manager.heizung_off_ts is not None
            else 999999
        )

        decision = heating_engine.decide(ctx)
        details = decision.details or {}
        heizung_active = decision.reason == "HEIZUNG_ACTIVE"
        nachlauf_active = decision.reason == "HEIZUNG_NACHLAUF"
        ctx.heizung_active = heizung_active

        # =========================
        # 🔒 LOCK SETZEN / FREIGEBEN
        # =========================
        if heizung_active or nachlauf_active:
            state_manager.heizung_lock = True
        else:
            if state_manager.heizung_lock:
                # War gesperrt, jetzt freigeben
                state_manager.release_heizung_lock()

        # =========================
        # 🔌 RELAYS SCHALTEN
        # =========================

        if heizung_active:
            heizung_venti_cmd("on", "on")
            logger.info(
                "Heizung aktiv – Lüfter EIN (mode=%s, remaining=%ss)",
                ctx.heizung_mode,
                details.get("remaining"),
            )
        elif nachlauf_active:
            heizung_venti_cmd("off", "on")
            logger.info(
                "Heizung Nachlauf – Lüfter EIN (noch %ss)",
                details.get("nachlauf_remaining"),
            )
        else:
            heizung_cmd("off")
            logger.info(
                "Heizung inaktiv, kein Nachlauf – Lüfter durch venti_control"
            )

        state_changed = state_manager.last_heizung_state != decision.reason
        command_changed = state_manager.last_heizung_command != decision.command
        mode_changed = state_manager.last_heizung_mode != ctx.heizung_mode

        if state_changed or command_changed or mode_changed:
            state_manager.persist_heizung(
                state=decision.reason,
                command=decision.command,
                mode=ctx.heizung_mode,
                details=details,
                ctx=ctx
            )

        event_bus.publish(Event(
            type=EventType.DECISION_LOG,
            data={"decision": decision, "ctx": ctx}
        ))

        if heizung_detector.state_start_ts is None and decision.reason in (
            "HEIZUNG_ACTIVE",
            "HEIZUNG_NACHLAUF",
        ):
            heizung_detector.restore(
                command="off",
                reason="HEIZUNG_IDLE",
                details={},
                state_start_ts=ctx.now,
            )
        elif heizung_detector.state_start_ts is None:
            heizung_detector.restore(
                command=decision.command,
                reason=decision.reason,
                details=details,
                state_start_ts=ctx.now,
            )

        events = heizung_detector.detect(decision, data)

        for event in events:
            event_bus.publish(Event(
                type=EventType.TRANSITION,
                data={
                    "name": event[0],
                    "event": event,
                    "ctx": ctx
                }
            ))

    except Exception as e:
        logger.error(f"heizung_control error: {e}", exc_info=True)
