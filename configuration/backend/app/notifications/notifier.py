import threading
import requests
from app.utils.logger import logger
from app.config import Config
from app.services.influx_service import get_venti_control_param_actual_values
import time

# Cache – nicht bei jedem send_notification() Influx abfragen
_notif_enabled_cache = None
_notif_enabled_cache_ts = 0
_CACHE_TTL = 300  # 5 Minuten


def _notifications_enabled():
    global _notif_enabled_cache, _notif_enabled_cache_ts
    now = time.time()
    if _notif_enabled_cache is not None and now - _notif_enabled_cache_ts < _CACHE_TTL:
        return _notif_enabled_cache
    try:
        params = get_venti_control_param_actual_values()
        _notif_enabled_cache = params.get("notifications_enabled", True)
        _notif_enabled_cache_ts = now
        return _notif_enabled_cache
    except Exception as e:
        logger.warning(f"Notification preference check failed, sending anyway: {e}")
        return True


def _send(title: str, message: str):
    try:
        url = f"{Config.NTFY_BASE_URL}/{Config.NTFY_TOPIC}"
        full_message = f"{title}\n\n{message}"
        response = requests.post(
            url,
            data=full_message.encode("utf-8"),
            headers={"Content-Type": "text/plain; charset=utf-8"},
            timeout=5,
        )
        if response.status_code == 200:
            logger.debug(f"NTFY sent: {title}")
        else:
            logger.error(f"NTFY send failed: {response.status_code}")
    except Exception as e:
        logger.error(f"NTFY send failed: {e}")


def send_notification(title: str, message: str):
    """
    Fire-and-forget – läuft im Hintergrund-Thread.
    Blockiert den Controller nie, auch bei Timeout nicht.
    """
    if not _notifications_enabled():
        logger.info(f"Notifications disabled, skipped: {title}")
        return

    threading.Thread(target=_send, args=(title, message), daemon=True).start()
