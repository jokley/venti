from flask import Blueprint, jsonify,request,send_file
from ..utils.logger import logger
import threading
import os

system_bp = Blueprint('system', __name__)

@system_bp.route('/ventiSystem', methods=['POST'])
def venti_system():
    data = request.get_json()
    OSCMD = data.get('oscmd')

    if OSCMD == 'reboot':
        def reboot_system():
            os.system('reboot -d 5 -f')
        threading.Thread(target=reboot_system).start()
        return jsonify('System Reboot initiated')
    
    elif OSCMD == 'shutdown':
        def shutdown_system():
            os.system('poweroff -d 5 -f')
        threading.Thread(target=shutdown_system).start()
        return jsonify('System Shutdown initiated')
    
    elif OSCMD == 'refresh':
        return jsonify('Page Refresh')

    return jsonify('System command executed')

@system_bp.route('/logging')
def default_route():
    """Default route to test logging"""
    logger.debug('this is a DEBUG message')
    logger.info('this is an INFO message')
    logger.warning('this is a WARNING message')
    logger.error('this is an ERROR message')
    logger.critical('this is a CRITICAL message')
    return jsonify('hello world')

@system_bp.route('/download')
def download():
    path = 'debug.log'
    return send_file(path, as_attachment=True)