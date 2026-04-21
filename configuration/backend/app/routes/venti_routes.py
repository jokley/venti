from flask import Blueprint, jsonify, request
from datetime import datetime
from ..services.venti_service import venti_cmd, venti_auto, venti_auto_param
from ..controller.venti.controller import venti_control
from ..extensions.extensions import scheduler
from ..utils.logger import logger

venti_bp = Blueprint('venti', __name__)

@venti_bp.route('/venti', methods=['POST'])
def switch():
    data = request.get_json()
    CMD = data.get('cmd')
    TM = data.get('tm')
    STOCK = data.get('stock', '0')

    if CMD == 'on':
        venti_cmd(CMD)
        venti_auto(CMD, TM, '0')
        logger.info('****************************************')
        logger.info('Lüfter Hand ein')
        return jsonify('Venti on')
    
    elif CMD == 'off':
        venti_cmd(CMD)
        venti_auto(CMD, TM, '0')
        logger.info('****************************************')
        logger.info('Lüfter Hand aus')
        return jsonify('Venti off')
    
    elif CMD == 'auto':
        venti_auto(CMD, TM, STOCK)
        # Force scheduler to run now (don't wait 4 minutes)
        scheduler.modify_job('venti_control', next_run_time=datetime.now())
        logger.info('Automatik aktiviert')
        return jsonify('Venti auto')
    
    return jsonify('No command sent!')

@venti_bp.route('/ventiParams', methods=['POST'])
def set_params():
    data = request.get_json()
    venti_auto_param(**data)
    # Force scheduler to run now when params change
    scheduler.modify_job('venti_control', next_run_time=datetime.now())
    logger.info('Parameter aktualisiert')
    return jsonify('Parameters updated')