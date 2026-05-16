from flask import Blueprint, jsonify, request
from datetime import datetime
from ..services.venti_service import (
    venti_cmd, venti_auto, venti_auto_param,
    heizung_auto, heizung_auto_param
)
from ..controller.venti.controller import venti_control
from ..controller.venti.controller_Heizung import heizung_control
from ..controller.venti.control.state_manager import state_manager
from ..extensions.extensions import scheduler
from ..services.influx_service import (
    VENTI_PARAM_DEFAULTS,
    HEIZUNG_PARAM_DEFAULTS,
    get_venti_control_param_actual_values,
    get_heizung_param_actual_values
)
from ..utils.logger import logger

venti_bp = Blueprint('venti', __name__)


# =============================================================================
# 🔧 TRIGGER HELPERS
# =============================================================================

def _trigger_venti_control_now():
    """
    Triggert venti_control() sofort über den Scheduler.
    Fallback: direkt aufrufen wenn Scheduler-Job nicht aktiv.
    """
    try:
        scheduler.modify_job('venti_control', next_run_time=datetime.now())
    except Exception:
        logger.warning("venti_control Job nicht gefunden – direkt ausführen")
        venti_control()


def _trigger_heizung_control_now():
    """
    Triggert heizung_control() sofort über den Scheduler.
    Fallback: direkt aufrufen wenn Scheduler-Job nicht aktiv.
    Setzt Lock und Relay sofort – kein Warten auf nächsten Zyklus.
    """
    try:
        scheduler.modify_job('heizung_control', next_run_time=datetime.now())
    except Exception:
        logger.warning("heizung_control Job nicht gefunden – direkt ausführen")
        heizung_control()


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
        logger.info('****************************************')
        logger.info('Lüfter Hand ein')
        return jsonify('Venti on')

    elif CMD == 'off':
        state_manager.clear_venti_drying_delay()
        venti_cmd(CMD)
        venti_auto(CMD, TM, '0')
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
        heizung_auto('on', 0, SDEF_LIMIT)
        _trigger_heizung_control_now()   # Lock sofort setzen
        logger.info('****************************************')
        logger.info('Heizung Hand ein')
        return jsonify('Heizung on')

    elif CMD == 'off':
        state_manager.clear_heizung_sdef_delay()
        heizung_auto('off', 0, SDEF_LIMIT)
        _trigger_heizung_control_now()   # Lock sofort freigeben
        logger.info('****************************************')
        logger.info('Heizung Hand aus')
        return jsonify('Heizung off')

    elif CMD == 'auto':
        state_manager.clear_heizung_sdef_delay()
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
