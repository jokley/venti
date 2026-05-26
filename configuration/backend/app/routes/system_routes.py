from flask import Blueprint, jsonify,request,send_file

from app.controller.venti.context import VentiContext
from app.controller.venti.controller import evaluate
from app.services.control_data import build_control_data
from app.notifications.notifier import send_notification
from app.notifications.summary.daily_summary import build_daily_summary
from app.db.influx_client import get_influxdb_client
from app.services.influx_service import get_sensor_age
  
from ..utils.logger import logger
import threading
import os

system_bp = Blueprint('system', __name__)


def _influx_ok() -> bool:
    """Lightweight Influx availability check used by watchdog."""
    client = get_influxdb_client()
    try:
        # Keep query intentionally cheap; we only need a connectivity signal.
        client.query_api().query(query='buckets() |> limit(n: 1)')
        return True
    except Exception:
        return False
    finally:
        client.close()


def _is_panstamp_mode() -> bool:
    value = os.getenv("PANSTAMP", "false").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _panstamp_stream_ok() -> bool:
    """
    For PANSTAMP=true: stream is considered unhealthy only when all monitored
    sensors are stale (older than PANSTAMP_MAX_SENSOR_AGE_SEC) or no ages exist.
    For LoRa mode this check is ignored (always true).
    """
    if not _is_panstamp_mode():
        return True

    max_age = int(os.getenv("PANSTAMP_MAX_SENSOR_AGE_SEC", "300"))

    try:
        ages = get_sensor_age()
    except Exception:
        return False

    if not ages:
        return False

    # Healthy when at least one sensor is still recent.
    return any(int(age) <= max_age for age in ages.values() if age is not None)

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

@system_bp.route('/debug')
def debug_ctx():
    """Debug route to return ctx as JSON"""
    data = build_control_data()
    ctx = VentiContext(data)
    return jsonify(vars(ctx))


@system_bp.route("/trace")
def rule_trace():
    data = build_control_data()
    ctx = VentiContext(data)

    decision = evaluate(ctx)

    return jsonify({
        "context": {
            "mode": ctx.mode,
            "tempMax": ctx.tempMax,
            "humMax": ctx.humMax,
            "tsMin": ctx.tsMin,
            "tsSoll": ctx.tsSoll,
            "stock": ctx.stock,
            "remainingTimeStock": ctx.remainingTimeStock,

            # health layer (VERY useful for debugging)
            "battery": data.get("battery", {}),
            "rssi": data.get("rssi", {}),
            "sensor_age": data.get("sensor_age", {}),
        },

        "final_decision": {
            "command": decision.command,
            "reason": decision.reason,
        },

        "trace": decision.details.get("trace", [])
    })

@system_bp.route("/summary", methods=["GET"])
def force_daily_summary():
    data = build_control_data()
    ctx = VentiContext(data)

    msg = build_daily_summary(ctx)

    send_notification(
        title="Tagesübersicht (forced)",
        message=msg
    )

    return jsonify({
        "status": "forced_sent"
    })


@system_bp.route("/healthz", methods=["GET"])
def healthz():
    """Basic backend liveness endpoint for container watchdogs."""
    return jsonify({"status": "ok"}), 200


@system_bp.route("/watchdog/status", methods=["GET"])
def watchdog_status():
    """Status endpoint consumed by the watchdog service."""
    return jsonify({
        "influx_ok": _influx_ok(),
        "panstamp_mode": _is_panstamp_mode(),
        "panstamp_stream_ok": _panstamp_stream_ok(),
    }), 200
