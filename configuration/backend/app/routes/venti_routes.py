from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta
from ..services.venti_service import (
    venti_cmd, venti_auto, venti_auto_param,
    heizung_cmd, heizung_venti_cmd,
    heizung_auto, heizung_auto_param
)
from ..controller.venti.controller import venti_control
from ..controller.venti.controller_Heizung import heizung_control
from ..controller.venti.control.state_manager import state_manager
from ..extensions.extensions import scheduler
from ..scheduler import VENTI_CONTROL_INTERVAL_MINUTES, HEIZUNG_CONTROL_INTERVAL_MINUTES
from ..services.influx_service import (
    VENTI_PARAM_DEFAULTS,
    HEIZUNG_PARAM_DEFAULTS,
    get_venti_control_param_actual_values,
    get_heizung_param_actual_values,
    get_heizung_control_values
)
from ..utils.time_utils import get_timestamp_now_epoche
from ..utils.logger import logger

venti_bp = Blueprint('venti', __name__)


# =============================================================================
# 🔧 TRIGGER HELPERS
# =============================================================================

def _trigger_venti_control_now():
    """
    Führt venti_control() synchron aus, damit API-Änderungen sofort
    persistiert, geschaltet und gemeldet werden. Danach wird der nächste
    Schedulerlauf auf den normalen Takt ab jetzt gelegt.
    """
    _run_control_now_and_sync_job(
        "venti_control",
        VENTI_CONTROL_INTERVAL_MINUTES,
        venti_control,
    )


def _trigger_heizung_control_now():
    """
    Führt heizung_control() synchron aus, damit Mode, Parameter, Lock,
    Relais und Notifications sofort konsistent sind. Danach wird der nächste
    Schedulerlauf auf den normalen Takt ab jetzt gelegt.
    """
    _run_control_now_and_sync_job(
        "heizung_control",
        HEIZUNG_CONTROL_INTERVAL_MINUTES,
        heizung_control,
    )


def _run_control_now_and_sync_job(job_id, interval_minutes, control_func):
    try:
        control_func()
    finally:
        _sync_scheduler_job(job_id, interval_minutes)


def _sync_scheduler_job(job_id, interval_minutes):
    next_run_time = datetime.now(scheduler.timezone) + timedelta(minutes=interval_minutes)

    try:
        scheduler.modify_job(
            job_id,
            next_run_time=next_run_time,
        )
        logger.debug(
            "Scheduler Job %s synchronisiert – nächster Lauf: %s",
            job_id,
            next_run_time,
        )
    except Exception:
        logger.warning("Scheduler Job %s konnte nicht synchronisiert werden", job_id)


def _heizung_was_active_before_manual_off():
    """
    Best effort snapshot before heizung_auto('off') overwrites the persisted mode.
    This keeps manual off -> nachlauf reliable after scheduler timing or restarts.
    """
    runtime_active = (
        state_manager.heizung_was_active
        or state_manager.heizung_lock
        or state_manager.heizung_manual_command == "on"
        or state_manager.last_heizung_command == "on"
        or state_manager.last_heizung_mode == "on"
        or state_manager.last_heizung_forced_venti_command == "on"
        or state_manager.last_heizung_state in (
            "HEIZUNG_ACTIVE",
            "HEIZUNG_MANUAL_ON",
            "HEIZUNG_NACHLAUF",
        )
    )

    if runtime_active:
        return True

    try:
        return get_heizung_control_values().mode == "on"
    except Exception:
        logger.warning("Heizung Modus vor Hand AUS konnte nicht gelesen werden", exc_info=True)
        return False


# =============================================================================
# 🌀 LÜFTER
# =============================================================================

@venti_bp.route('/venti', methods=['POST'])
def switch():
    data = request.get_json()
    CMD = data.get('cmd')
    TM = data.get('tm')
    STOCK = data.get('stock', '0')

    if CMD == 'on':
        state_manager.clear_venti_drying_delay()
        venti_cmd(CMD)
        venti_auto(CMD, TM, '0')
        _trigger_venti_control_now()
        logger.info('****************************************')
        logger.info('Lüfter Hand ein')
        return jsonify('Venti on')

    elif CMD == 'off':
        state_manager.clear_venti_drying_delay()
        venti_cmd(CMD)
        venti_auto(CMD, TM, '0')
        _trigger_venti_control_now()
        logger.info('****************************************')
        logger.info('Lüfter Hand aus')
        return jsonify('Venti off')

    elif CMD == 'auto':
        state_manager.clear_venti_drying_delay()
        venti_auto(CMD, TM, STOCK)
        _trigger_venti_control_now()
        logger.info('Automatik aktiviert')
        return jsonify('Venti auto')

    return jsonify('No command sent!')


@venti_bp.route('/ventiParams', methods=['POST'])
def set_params():
    data = request.get_json() or {}
    current_params = get_venti_control_param_actual_values()

    merged_params = {
        key: data.get(key, current_params.get(key, default_value))
        for key, default_value in VENTI_PARAM_DEFAULTS.items()
    }

    venti_auto_param(**merged_params)
    _trigger_venti_control_now()
    logger.info('Parameter aktualisiert')
    return jsonify('Parameters updated')


# =============================================================================
# 🔥 HEIZUNG
# =============================================================================

@venti_bp.route('/heizung', methods=['POST'])
def heizung_switch():
    data = request.get_json()
    CMD = data.get('heizung_cmd')
    DAUER = float(data.get('heizung_dauer') or 0)
    SDEF_LIMIT = float(data.get('heizung_sdef_limit') or 0)

    if CMD == 'on':
        state_manager.clear_heizung_sdef_delay()
        state_manager.set_heizung_manual_on()
        heizung_venti_cmd('on', 'on')
        heizung_auto('on', 0, SDEF_LIMIT)
        _trigger_heizung_control_now()   # State/Notifications sofort syncen
        logger.info('****************************************')
        logger.info('Heizung Hand ein')
        return jsonify('Heizung on')

    elif CMD == 'off':
        state_manager.clear_heizung_sdef_delay()
        current_params = get_heizung_param_actual_values()
        nachlauf_seconds = int(current_params.get("heizung_nachlauf", 0) * 60)
        now = get_timestamp_now_epoche()
        was_active = _heizung_was_active_before_manual_off()

        state_manager.start_heizung_manual_nachlauf(
            now,
            nachlauf_seconds,
            was_active=was_active,
        )

        if state_manager.heizung_lock and state_manager.heizung_off_ts is not None:
            heizung_venti_cmd('off', 'on')
        else:
            heizung_cmd('off')

        heizung_auto('off', 0, SDEF_LIMIT)
        _trigger_heizung_control_now()   # State/Notifications sofort syncen
        logger.info('****************************************')
        logger.info('Heizung Hand aus')
        return jsonify('Heizung off')

    elif CMD == 'auto':
        state_manager.clear_heizung_sdef_delay()
        state_manager.heizung_manual_command = None
        heizung_auto('auto', DAUER, SDEF_LIMIT)
        _trigger_heizung_control_now()   # Lock + Timer sofort auswerten
        logger.info('****************************************')
        logger.info('Heizung Auto – Dauer: %sh, SDEF Limit: %s', DAUER, SDEF_LIMIT)
        return jsonify('Heizung auto')

    return jsonify('No command sent!')


@venti_bp.route('/heizungParams', methods=['POST'])
def set_heizung_params():
    data = request.get_json() or {}
    current_params = get_heizung_param_actual_values()

    merged_params = {
        key: data.get(key, current_params.get(key, default_value))
        for key, default_value in HEIZUNG_PARAM_DEFAULTS.items()
    }

    heizung_auto_param(**merged_params)
    _trigger_heizung_control_now()   # Nachlaufzeit-Änderung sofort wirksam
    logger.info('Heizung Parameter aktualisiert')
    return jsonify('Heizung parameters updated')
