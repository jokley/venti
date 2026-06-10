from app.services.influx_service import get_last_controller_state, get_last_heizung_controller_state
from app.services.venti_service import write_controller_state, write_heizung_controller_state
from app.utils.logger import logger


AUTO_DELAY_SECONDS = 20 * 60


class ControlStateManager:

    def __init__(self):
        # Runtime-Spiegel des zuletzt persistierten venti_state. Der Controller
        # nutzt ihn fuer Wechselerkennung, ohne jedes Mal Influx zu lesen.
        self.last_state = None
        self.last_command = None
        self.last_mode = None
        self.last_details = None
        self.last_ts = None

        # Heizung memory:
        # - off_ts treibt Nachlauf
        # - heizung_was_active erkennt EIN->AUS-Flanken
        # - heizung_lock sperrt venti_control waehrend Heizung/Nachlauf
        self.heizung_off_ts = None
        self.heizung_was_active = False
        self.heizung_lock = False
        self.last_heizung_state = None
        self.last_heizung_command = None
        self.last_heizung_mode = None
        self.last_heizung_details = None
        self.last_heizung_ts = None
        self.last_heizung_relay_command = None
        self.last_heizung_forced_venti_command = None
        self.heizung_manual_command = None
        self.heizung_sdef_delay_started_at = None
        self.venti_drying_delay_started_at = None

    # =========================
    # 🔁 RESTORE
    # =========================
    def restore(self):
        # Beim Prozessstart wird die letzte Influx-Timeline in den
        # In-Memory-State zurueckgespiegelt. Danach laufen Vergleiche lokal.
        data = get_last_controller_state()
        heizung_data = get_last_heizung_controller_state()

        if not data and not heizung_data:
            logger.info("No persisted controller state found")
            return None

        if heizung_data:
            self.restore_heizung(heizung_data)

        if not data:
            return {
                "state": self.last_state,
                "command": self.last_command,
                "mode": self.last_mode,
                "details": self.last_details,
                "started_at": self.last_ts,
            }

        self.last_state = data.get("state")
        self.last_command = data.get("command")
        self.last_mode = data.get("mode")
        self.last_details = data.get("details", {})
        self.last_ts = data.get("started_at")
        logger.info(
            "Restored controller state: state=%s mode=%s",
            self.last_state,
            self.last_mode
        )

        return {
            "state": self.last_state,
            "command": self.last_command,
            "mode": self.last_mode,
            "details": self.last_details,
            "started_at": self.last_ts,
        }

    def restore_heizung(self, data):
        self.last_heizung_state = data.get("state")
        self.last_heizung_command = data.get("command")
        self.last_heizung_mode = data.get("mode")
        self.last_heizung_details = data.get("details", {})
        self.last_heizung_ts = data.get("started_at")
        self.last_heizung_relay_command = self.last_heizung_command

        if self.last_heizung_state == "HEIZUNG_NACHLAUF" and self.last_heizung_ts is not None:
            self.heizung_off_ts = self.last_heizung_ts
            self.heizung_was_active = False
            self.heizung_lock = True
            if self.last_heizung_mode == "off":
                self.heizung_manual_command = "off"
            logger.info(
                "Restored heizung nachlauf – lock gesetzt (off_ts=%s)",
                self.heizung_off_ts,
            )
        elif self.last_heizung_state in ("HEIZUNG_ACTIVE", "HEIZUNG_MANUAL_ON"):
            self.heizung_was_active = True
            self.heizung_lock = True
            self.last_heizung_forced_venti_command = "on"
            if self.last_heizung_mode == "on" or self.last_heizung_state == "HEIZUNG_MANUAL_ON":
                self.heizung_manual_command = "on"
            logger.info("Restored heizung active – lock gesetzt")
        elif self.last_heizung_mode == "off" or self.last_heizung_state == "HEIZUNG_MANUAL_OFF":
            self.heizung_manual_command = "off"

    # =========================
    # 💾 PERSIST
    # =========================
    def persist(self, state, command, mode, details, ctx):
        # Influx bleibt die dauerhafte State-Timeline; diese Attribute sind der
        # lokale Spiegel fuer die naechste Regelrunde.
        write_controller_state(
            state=state,
            command=command,
            mode=mode,
            details=details
        )

        self.last_state = state
        self.last_command = command
        self.last_mode = mode
        self.last_details = details
        self.last_ts = ctx.now

        logger.debug("State persisted: %s (%s)", state, command)

    # =========================
    # 🔥 HEIZUNG
    # =========================
    def update_heizung(self, heizung_active, ctx):
        """
        Einmal pro heizung_control() Zyklus aufrufen.

        - Erkennt Flanke EIN→AUS und setzt heizung_off_ts
        - Aktualisiert heizung_was_active
        - Setzt heizung_lock (wird von venti_control geprüft)

        Nachlauf-Prüfung erfolgt NACH diesem Aufruf in heizung_control(),
        weil heizung_off_since erst danach korrekt berechnet werden kann.
        heizung_lock wird deshalb in heizung_control() nochmals gesetzt.
        """
        if self.heizung_was_active and not heizung_active:
            self.heizung_off_ts = ctx.now
            logger.info("Heizung abgegangen – Nachlauf startet (off_ts=%s)", ctx.now)

        self.heizung_was_active = heizung_active

        # Vorläufiger Lock – wird in heizung_control() nach
        # Nachlauf-Berechnung endgültig gesetzt
        if heizung_active:
            self.heizung_lock = True

    def set_heizung_manual_on(self):
        """
        Synchronisiert einen direkt geschalteten manuellen EIN-Befehl.
        Der Scheduler liest diesen Override und persistiert danach heizung_state.
        """
        self.heizung_manual_command = "on"
        self.heizung_was_active = True
        self.heizung_off_ts = None
        self.heizung_lock = True
        self.last_heizung_forced_venti_command = "on"
        logger.info("Heizung Hand EIN synchronisiert – lock gesetzt")

    def start_heizung_manual_nachlauf(self, now, nachlauf_seconds, was_active=True):
        """
        Synchronisiert einen direkt geschalteten manuellen AUS-Befehl.
        Bei konfiguriertem Nachlauf bleibt der Lock aktiv, sonst wird er
        sofort freigegeben.
        """
        self.heizung_manual_command = "off"

        can_start_nachlauf = (
            was_active
            or getattr(self, "heizung_was_active", False)
            or getattr(self, "heizung_lock", False)
            or getattr(self, "last_heizung_state", None) in (
                "HEIZUNG_ACTIVE",
                "HEIZUNG_MANUAL_ON",
                "HEIZUNG_NACHLAUF",
            )
            or getattr(self, "last_heizung_mode", None) == "on"
            or getattr(self, "last_heizung_command", None) == "on"
            or getattr(self, "last_heizung_forced_venti_command", None) == "on"
        )

        if can_start_nachlauf and self.heizung_off_ts is None:
            self.heizung_off_ts = now

        if nachlauf_seconds > 0 and self.heizung_off_ts is not None:
            self.heizung_was_active = False
            self.heizung_lock = True
            self.last_heizung_forced_venti_command = "on"
            logger.info(
                "Heizung Hand AUS synchronisiert – Nachlauf startet (off_ts=%s)",
                self.heizung_off_ts,
            )
        else:
            self.heizung_was_active = False
            self.release_heizung_lock()

    def persist_heizung(self, state, command, mode, details, ctx):
        write_heizung_controller_state(
            state=state,
            command=command,
            mode=mode,
            details=details
        )

        self.last_heizung_state = state
        self.last_heizung_command = command
        self.last_heizung_mode = mode
        self.last_heizung_details = details
        self.last_heizung_ts = ctx.now

        logger.debug("Heizung state persisted: %s (%s)", state, command)

    def release_heizung_lock(self):
        """
        Gibt den Lock frei wenn weder Heizung noch Nachlauf aktiv.
        Wird von heizung_control() aufgerufen wenn Nachlauf endet.
        Setzt heizung_off_ts zurück damit kein Nachlauf mehr erkannt wird.
        """
        self.heizung_lock = False
        self.heizung_off_ts = None
        self.last_heizung_forced_venti_command = None
        logger.info("Heizung Lock freigegeben – venti_control wieder aktiv")

    # =========================
    # ⏳ AUTO DELAYS
    # =========================
    def start_heizung_sdef_delay(self, ctx):
        self.heizung_sdef_delay_started_at = ctx.now
        logger.info("Heizung SDEF Delay gestartet – %ss", AUTO_DELAY_SECONDS)

    def clear_heizung_sdef_delay(self):
        self.heizung_sdef_delay_started_at = None

    def get_heizung_sdef_delay_remaining(self, now):
        return self._delay_remaining(self.heizung_sdef_delay_started_at, now)

    def start_venti_drying_delay(self, ctx):
        self.venti_drying_delay_started_at = ctx.now
        logger.info("Venti Trocknungs-Delay gestartet – %ss", AUTO_DELAY_SECONDS)

    def clear_venti_drying_delay(self):
        self.venti_drying_delay_started_at = None

    def get_venti_drying_delay_remaining(self, now):
        return self._delay_remaining(self.venti_drying_delay_started_at, now)

    def _delay_remaining(self, started_at, now):
        if started_at is None:
            return 0

        remaining = AUTO_DELAY_SECONDS - int(now - started_at)

        if remaining <= 0:
            return 0

        return remaining



# singleton
state_manager = ControlStateManager()
