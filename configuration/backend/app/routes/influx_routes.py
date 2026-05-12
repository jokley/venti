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
    mode = dataVenti.mode
    tsSoll = dataVenti.trockenmasse
    stockini = int(dataVenti.stockaufbau)
    iniDict = {'cmd': mode, 'stock': stockini, 'tm': tsSoll} 
    return jsonify(iniDict)

@influx_bp.route('/controlValues', methods=['GET'])
def control_values():
    dataVenti = get_venti_control_values()

    mode = dataVenti.mode
    tsSoll = dataVenti.trockenmasse
    stockini = int(dataVenti.stockaufbau)

    return jsonify({
        'cmd': mode,
        'stock': stockini,
        'tm': tsSoll
    })

@influx_bp.route('/controlParamValues', methods=['GET'])
def control_param_values():
    return jsonify(get_venti_control_param_actual_values())
