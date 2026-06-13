from .context import VentiContext
from app.services.control_data import build_control_data
from app.services.venti_service import heizung_cmd, heizung_venti_cmd
from .control.state_manager import state_manager
from .heating.heating_decision_engine import HeatingDecisionEngine
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
        # 1. Context aufbauen
        # build_control_data liefert dieselbe Datenbasis wie venti_control.
        # Danach werden die Runtime-Werte aus dem StateManager ergaenzt, weil
        # sie nicht direkt aus Influx/Parametern kommen.
        data = build_control_data()
        ctx = VentiContext(data)
        ctx.heizung_sdef_was_active = state_manager.heizung_was_active
        ctx.heizung_sdef_delay_remaining = (
            state_manager.get_heizung_sdef_delay_remaining(ctx.now)
        )
        ctx.heizung_manual_command = state_manager.heizung_manual_command

        # Erste Bewertung ohne Nachlauf-Decision: wir brauchen nur die echte
        # Aktiv-Flanke, damit SDEF-Delay und Nachlaufzeit korrekt starten.
        heizung_was_active = state_manager.heizung_was_active
        heizung_active = heating_engine.compute_active(ctx)
        ctx.heizung_active = heizung_active

        # Wenn die SDEF-Automatik wegen erreichtem Limit ausgeht, startet eine
        # Restart-Sperre. So schwingt die Heizung nicht direkt um das Limit.
        # Die feste Anfangsdauer hat Vorrang; deshalb wird das Limit erst nach
        # Ablauf von heizung_dauer als Abschaltgrund fuer den SDEF-Delay gewertet.
        if (
            heizung_was_active
            and not heizung_active
            and ctx.heizung_mode == "auto"
            and (ctx.heizung_sdef_limit or 0) > 0
            and ctx.remainingTimeHeizung > ctx.heizung_dauer
            and ctx.sDefOut is not None
            and ctx.sDefOut >= ctx.heizung_sdef_limit
        ):
            state_manager.start_heizung_sdef_delay(ctx)
            ctx.heizung_sdef_delay_remaining = (
                state_manager.get_heizung_sdef_delay_remaining(ctx.now)
            )

        # Flanke EIN→AUS erkennen, heizung_off_ts setzen,
        # heizung_was_active aktualisieren
        # Wichtig: Diese Funktion setzt den vorlaeufigen Lock nur bei aktiver
        # Heizung. Ob Nachlauf den Lock weiter haelt, entscheidet der Block
        # weiter unten nach der finalen HeatingDecision.
        state_manager.update_heizung(heizung_active, ctx)

        # heizung_off_since NACH update_heizung() berechnen
        # damit ein soeben gesetztes heizung_off_ts sofort wirkt
        ctx.heizung_off_since = (
            int(ctx.now - state_manager.heizung_off_ts)
            if state_manager.heizung_off_ts is not None
            else 999999
        )

        # 2. Fachliche Heizungsentscheidung
        # Die HeatingDecisionEngine entscheidet nur Heizung/Nachlauf/Details.
        # Relaiskommandos und Lock-Side-Effects passieren im Controller.
        decision = heating_engine.decide(ctx)
        details = decision.details or {}
        heizung_active = decision.reason in ("HEIZUNG_ACTIVE", "HEIZUNG_MANUAL_ON")
        nachlauf_active = decision.reason == "HEIZUNG_NACHLAUF"
        ctx.heizung_active = heizung_active

        # =========================
        # 🔒 LOCK SETZEN / FREIGEBEN
        # =========================
        # Der Lock ist die harte Kopplung: solange Heizung oder Nachlauf aktiv
        # sind, darf venti_control den Luefter nicht eigenstaendig schalten.
        if heizung_active or nachlauf_active:
            state_manager.heizung_lock = True
        else:
            if state_manager.heizung_lock:
                # War gesperrt, jetzt freigeben. Direkt danach startet der
                # Venti-Post-Heizung-Delay, damit die normale Intervalllogik
                # nicht sofort nach Ende des erzwungenen Heizungs-Luefterlaufs
                # wieder anspringt.
                state_manager.release_heizung_lock()
                state_manager.start_venti_post_heizung_delay(ctx)

        # =========================
        # 🔌 RELAYS SCHALTEN
        # =========================

        # Variante A: Heizung erzwingt RO1=Luefter EIN. Nachlauf laesst die
        # Heizung aus, haelt aber den Luefter weiter an.
        if heizung_active:
            # Heizung aktiv: RO2=Heizung EIN und RO1=Luefter EIN.
            heizung_venti_cmd("on", "on")
            logger.info(
                "Heizung aktiv – Lüfter EIN (mode=%s, remaining=%ss)",
                ctx.heizung_mode,
                details.get("remaining"),
            )
        elif nachlauf_active:
            # Nachlauf: Heizung AUS, Luefter bleibt EIN. Dadurch wird Restwaerme
            # abgefuehrt, ohne dass venti_control parallel eigene Befehle sendet.
            heizung_venti_cmd("off", "on")
            logger.info(
                "Heizung Nachlauf – Lüfter EIN (noch %ss)",
                details.get("nachlauf_remaining"),
            )
        else:
            # Kein Heizungsgrund und kein Nachlauf: RO2 sicher AUS. RO1 wird
            # nicht mehr von der Heizung erzwungen und darf durch venti_control
            # im naechsten Zyklus wieder normal entschieden werden.
            heizung_cmd("off")
            logger.info("Heizung inaktiv – Lüfter durch venti_control")

        # 3. Persistenz nur bei relevanten Aenderungen
        # state/command/mode werden getrennt verglichen, weil z.B. derselbe
        # Zustand mit anderem Kommando oder geaendertem manuellen Modus fuer
        # Timeline und UI relevant ist.
        state_changed = state_manager.last_heizung_state != decision.reason
        command_changed = state_manager.last_heizung_command != decision.command
        effective_mode = ctx.heizung_manual_command or ctx.heizung_mode
        mode_changed = state_manager.last_heizung_mode != effective_mode

        # heizung_state ist die dauerhafte Timeline. Identische Zyklen bleiben
        # im File/Influx ruhig, damit nur relevante Wechsel sichtbar werden.
        if state_changed or command_changed or mode_changed:
            state_manager.persist_heizung(
                state=decision.reason,
                command=decision.command,
                mode=effective_mode,
                details=details,
                ctx=ctx
            )

        # 4. Decision-Event fuer Logs/Debugging. Wird unabhaengig von Persistenz
        # gesendet, damit Beobachter jeden Heizungszyklus sehen koennen.
        event_bus.publish(Event(
            type=EventType.DECISION_LOG,
            data={"decision": decision, "ctx": ctx}
        ))

        # 5. TransitionDetector initialisieren
        # Wenn der Prozess mitten in einer aktiven Heiz-/Nachlaufphase startet,
        # fehlt dem Detector ein vorheriger Zustand. Wir setzen dann bewusst
        # HEIZUNG_IDLE als Startpunkt, damit die erste aktive Decision als
        # sauberer Uebergang gemeldet werden kann.
        if heizung_detector.state_start_ts is None and decision.reason in (
            "HEIZUNG_ACTIVE",
            "HEIZUNG_MANUAL_ON",
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

        # 6. Transition-Events publizieren. Diese Events sind die Grundlage fuer
        # Benachrichtigungen und unterscheiden sich vom reinen Decision-Log:
        # Sie entstehen nur bei Zustandswechseln.
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
        # Der Heizungsjob darf bei einem Fehler nicht den Scheduler/Backend-
        # Prozess beenden. Fehler werden geloggt; der naechste Schedulerlauf
        # versucht erneut, einen konsistenten Zustand herzustellen.
        logger.error(f"heizung_control error: {e}", exc_info=True)
