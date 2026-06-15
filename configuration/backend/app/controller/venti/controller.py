from .context import VentiContext
from .drying.drying_decision_engine import DryingDecisionEngine
from .interval_scheduler import get_interval_scheduler_delay
from datetime import datetime, timedelta

from app.services.control_data import build_control_data
from app.services.venti_service import venti_cmd, venti_auto
from app.extensions.extensions import scheduler

from .control.state_manager import state_manager

from app.notifications.transitions import TransitionDetector
from app.notifications.alerts.battery_engine import check_battery_alerts
from app.notifications.alerts.rssi_engine import check_rssi_alerts
from app.notifications.state_registry import alert_state

from app.notifications.summary.daily_summary import (
    build_daily_summary,
    should_send_summary
)
from app.notifications.summary.auto_summary import build_auto_summary

from app.events.event_bus import event_bus, EventType, Event
from app.utils.logger import logger

decision_engine = DryingDecisionEngine()


def evaluate(ctx, previous_state=None):
    # Schmale Wrapper-Funktion fuer Tests und Controller:
    # Die fachliche Entscheidung bleibt in der DryingDecisionEngine, der
    # Controller selbst kuemmert sich nur um Daten, Side-Effects und Events.
    return decision_engine.evaluate(ctx, previous_state=previous_state)


def sync_interval_end_scheduler(decision):
    # Normalerweise laeuft venti_control im festen Basistakt. Bei einem kurzen
    # Intervalllauf kann das zu spaetem Abschalten fuehren. Deshalb wird der
    # naechste Job-Lauf auf das berechnete Intervall-Ende vorgezogen, wenn die
    # Decision eine Restlaufzeit unterhalb des Basistakts meldet.
    delay_seconds = get_interval_scheduler_delay(decision)

    if delay_seconds is None:
        return False

    next_run_time = datetime.now(scheduler.timezone) + timedelta(seconds=delay_seconds)

    try:
        # APScheduler bekommt eine absolute naechste Laufzeit. Die Decision
        # merkt sich den Delay fuer Diagnose/Logs, damit spaeter sichtbar ist,
        # warum der Job ausserhalb des normalen Takts geplant wurde.
        scheduler.modify_job(
            "venti_control",
            next_run_time=next_run_time,
        )
        decision.details["scheduler_next_delay"] = delay_seconds
        logger.debug(
            "venti_control auf Intervall-Ende synchronisiert – nächster Lauf: %s",
            next_run_time,
        )
        return True
    except Exception:
        # Scheduler-Probleme duerfen den Controller nicht abbrechen:
        # Der normale Basistakt laeuft weiter, nur das punktgenaue
        # Intervall-Ende kann in diesem Zyklus nicht garantiert werden.
        logger.warning("venti_control konnte nicht auf Intervall-Ende synchronisiert werden")
        return False



def handle_after_heizung_pending(decision, ctx):
    # Nach Ende von Heizung/Nachlauf bewertet genau die erste normale
    # Venti-Decision, ob ein Restart-Delay noetig ist: Bei echter Trocknung
    # darf der Luefter nahtlos weiterlaufen, bei AUS startet die bestehende
    # Trocknungs-Restartsperre.
    if not state_manager.venti_after_heizung_pending:
        return

    try:
        if (
            decision.command == "off"
            and decision.reason in ("AUTO_IDLE", "INEFFICIENT_DRYING")
        ):
            state_manager.start_venti_drying_delay(ctx)
            decision.details["delay_remaining"] = (
                state_manager.get_venti_drying_delay_remaining(ctx.now)
            )
            decision.details["delay_started_after_heizung"] = True
    finally:
        state_manager.venti_after_heizung_pending = False

# =========================
# 🔁 RUNTIME STATE
# =========================
detector = TransitionDetector()
previous_mode = None
previous_state = None


def restore_controller_runtime_state():
    global previous_mode, previous_state

    # Restore laeuft nur einmal nach Prozessstart. Danach ist der
    # StateManager die In-Memory-Quelle fuer Persistenz- und Transition-Vergleiche.
    if (
        previous_mode is not None
        or previous_state is not None
        or detector.state_start_ts is not None
    ):
        return

    try:
        restored = state_manager.restore()
    except Exception:
        # Influx kann beim Prozessstart noch nicht bereit sein. Der Backend-
        # Prozess soll trotzdem weiterlaufen, /healthz beantworten und im
        # naechsten Zyklus erneut versuchen, den Runtime-State zu laden.
        logger.exception("Unable to restore controller state from InfluxDB; continuing without persisted state.")
        return

    if not restored:
        # Kein persistierter Zustand vorhanden: Der erste echte Zyklus baut
        # previous_mode/previous_state aus der neuen Decision auf.
        return

    previous_mode = restored.get("mode")
    previous_state = restored.get("state")

    detector.restore(
        command=restored.get("command"),
        reason=restored.get("state"),
        details=restored.get("details"),
        state_start_ts=restored.get("started_at"),
    )

    logger.info(
        "Restored controller state: mode=%s state=%s",
        previous_mode,
        previous_state,
    )


# =========================
# 🚀 MAIN CONTROL LOOP
# =========================
def venti_control():
    # Hauptjob fuer RO1/Luefter im normalen Venti-Betrieb. Er wird vom
    # Scheduler regelmaessig aufgerufen und fuehrt bewusst folgende Reihenfolge
    # aus: Restore -> Heizungssperre -> Context -> Decision -> Schalten ->
    # Persistenz -> Events/Alerts/Summaries.
    global previous_mode, previous_state

    # 1. RESTORE STATE
    restore_controller_runtime_state()

    # 2. HEIZUNG VERRIEGELUNG
    # heizung_control() läuft als eigenständiger Job und setzt den Lock.
    # Solange Heizung oder Nachlauf aktiv übernimmt heizung_control()
    # den Lüfter – venti_control() bleibt komplett draußen.
    if state_manager.heizung_lock:
        logger.info("venti_control gesperrt – Heizung Lock aktiv")
        return None

    # 3. BUILD CONTEXT
    # build_control_data() sammelt Influx-/Parameter-/Hardwarewerte; VentiContext
    # macht daraus die einheitliche Entscheidungsgrundlage fuer diesen Zyklus.
    data = build_control_data()
    ctx = VentiContext(data)
    ctx.venti_drying_delay_remaining = (
        state_manager.get_venti_drying_delay_remaining(ctx.now)
    )
    ctx.previous_state = previous_state
    ctx.previous_state_started_at = state_manager.last_ts

    # 4. DECISION ENGINE
    # Ab hier ist ctx vollstaendig vorbereitet. Die Engine entscheidet nur
    # fachlich ("on/off" + Reason + Details). Relais, Modusumschaltung und
    # Events passieren danach im Controller.
    decision = evaluate(ctx, previous_state=previous_state)

    handle_after_heizung_pending(decision, ctx)

    if ctx.mode == "auto" and decision.details.get("mode_override") == "off":
        # Auto-Disable ist eine fachliche Decision, aber das Umschalten des
        # Parameters/Modus ist ein Seiteneffekt und bleibt deshalb hier.
        venti_auto("off", ctx.tsSoll, "0")

    effective_mode = decision.details.get("mode_override", ctx.mode)

    # Wechselerkennung fuer Persistenz und Benachrichtigungen. Persistiert wird
    # nur, wenn sich wirklich etwas Relevantes geaendert hat. So bleibt die
    # Timeline lesbar und Influx/Grafana werden nicht mit identischen Zyklen
    # geflutet.
    mode_changed = previous_mode != effective_mode
    state_changed = previous_state != decision.reason
    previous_details = state_manager.last_details or {}
    previous_threshold = previous_details.get("min_efficiency_threshold")
    if previous_threshold is None:
        # Rueckwaertskompatibilitaet fuer alte Persistenzdaten vor dem
        # Self-Learning-Cleanup: Dort lag derselbe statische Grenzwert noch
        # unter adaptive_threshold.
        previous_threshold = previous_details.get("adaptive_threshold")
    threshold_changed = previous_threshold != decision.details.get("min_efficiency_threshold")

    # 5. EXECUTE CONTROL
    # Erst nach der vollstaendigen Decision wird das Relais geschaltet.
    # Dadurch landen alle Diagnosefelder konsistent in Persistenz und Events.
    venti_cmd(decision.command)

    # Persistenz ist die State-Timeline fuer Frontend/Grafana. Wiederholte
    # gleiche Entscheidungen werden nicht erneut geschrieben, ausser die
    # adaptive Schwelle hat sich veraendert.
    if mode_changed or state_changed or threshold_changed:
        state_manager.persist(
            state=decision.reason,
            command=decision.command,
            mode=effective_mode,
            details=decision.details,
            ctx=ctx
        )

    # 6. DECISION EVENT
    # Jede Runde publiziert die Decision fuer Logs/Debugging, auch wenn keine
    # Persistenz geschrieben wurde. So koennen Event-Handler den aktuellen
    # Zustand trotzdem beobachten.
    event_bus.publish(Event(
        type=EventType.DECISION_LOG,
        data={"decision": decision, "ctx": ctx}
    ))

    # Bei Intervall-Lueftung wird der naechste Lauf ans berechnete Ende gelegt,
    # damit 4-Minuten-Intervalle nicht bis zum normalen Basistakt ueberziehen.
    sync_interval_end_scheduler(decision)

    # 7. MODE CHANGE HANDLING
    if mode_changed:

        if previous_mode == "auto" and effective_mode != "auto":
            # Wenn Auto automatisch deaktiviert wurde, wird eine Zusammenfassung
            # verschickt, damit der Nutzer den Abschlussgrund nachvollziehen kann.
            logger.info("🛑 AUTO disabled -> sending summary")

            event_bus.publish(Event(
                type=EventType.DAILY_SUMMARY,
                data={"message": build_auto_summary(ctx)}
            ))

        event_bus.publish(Event(
            type=EventType.MODE_CHANGE,
            data={
                "old_mode": previous_mode,
                "new_mode": effective_mode,
                "ctx": ctx,
                "decision": decision
            }
        ))

        previous_mode = effective_mode

    # 8. TRANSITIONS
    # TransitionDetector erkennt Zustandswechsel mit Startzeit und Details.
    # Diese Events sind getrennt von der reinen Decision, damit Meldungen nur
    # bei echten Uebergaengen entstehen.
    events = detector.detect(decision, data)

    for event in events:
        event_bus.publish(Event(
            type=EventType.TRANSITION,
            data={
                "name": event[0],
                "event": event,
                "ctx": ctx
            }
        ))

    previous_state = decision.reason

    # 9. ALERTS
    # Systemalerts haengen am aktuellen Context, nicht an einer Zustandsaenderung.
    # Deshalb werden Batterie/RSSI jedes Mal geprueft, aber die Alert-State-
    # Objekte verhindern doppelte/zu haeufige Meldungen.
    for alert in (
        check_battery_alerts(ctx, alert_state.battery)
        + check_rssi_alerts(ctx, alert_state.rssi)
    ):
        event_bus.publish(Event(
            type=EventType.SYSTEM_ALERT,
            data=alert
        ))

    # 10. DAILY SUMMARY
    # Tageszusammenfassung wird zeitgesteuert ueber alert_state.summary
    # dedupliziert; der Controller triggert nur die Pruefung.
    if should_send_summary(ctx, alert_state.summary):
        event_bus.publish(Event(
            type=EventType.DAILY_SUMMARY,
            data={
                "message": build_daily_summary(ctx)
            }
        ))

    return decision
