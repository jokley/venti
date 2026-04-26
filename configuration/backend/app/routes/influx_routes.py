from flask import Blueprint, jsonify
from ..utils.logger import logger
from ..services.influx_service import (
    get_venti_control_values,
    get_venti_control_param_actual_values
)

influx_bp = Blueprint('influx', __name__)


@influx_bp.route('/influx', methods=['GET'])
def influx():
    dataVenti = get_venti_control_values()
    venti = dataVenti[0]
    startTime = venti['mode'][0]
    mode = venti['mode'][1]
    tsSoll = venti['trockenMasseSoll'][1]
    stock = int(venti['stockaufbau'][1])
    stockini = venti['stockaufbau'][1]
    iniDict = {'cmd': mode, 'stock': stockini, 'tm': tsSoll} 
    return jsonify(iniDict)

@influx_bp.route('/controlValues', methods=['GET'])
def control_values():
    dataVenti = get_venti_control_values()
    venti = dataVenti[0]
    mode = venti['mode'][1]
    tsSoll = venti['trockenMasseSoll'][1]
    stockini = venti['stockaufbau'][1]
    return jsonify({'cmd': mode, 'stock': stockini, 'tm': tsSoll})

@influx_bp.route('/controlParamValues', methods=['GET'])
def control_param_values():
    return jsonify(get_venti_control_param_actual_values())
