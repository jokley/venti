import requests
from app.utils.logger import logger
from app.config import Config
from app.services.influx_service import get_venti_control_param_actual_values


def _notifications_enabled():
    try:
        params = get_venti_control_param_actual_values()
        return params.get("notifications_enabled", True)
    except Exception as e:
        logger.warning(f"Notification preference check failed, sending anyway: {e}")
        return True

def send_notification(title: str, message: str):
    """Send notification with UTF-8 support for emoji"""
    if not _notifications_enabled():
        logger.info(f"Notifications disabled, skipped: {title}")
        return False

    try:
        url = f"{Config.NTFY_BASE_URL}/{Config.NTFY_TOPIC}"
        
        # Use UTF-8 encoding for emoji support
        headers = {
            "Content-Type": "text/plain; charset=utf-8",
        }
        
        # Combine title and message, encode as UTF-8
        full_message = f"{title}\n\n{message}"
        
        response = requests.post(
            url,
            data=full_message.encode('utf-8'),
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 200:
            logger.debug(f"NTFY sent: {title}")
            return True
        else:
            logger.error(f"NTFY send failed: {response.status_code}")
            return False
    
    except Exception as e:
        logger.error(f"NTFY send failed: {e}")
        return False
