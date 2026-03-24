import requests
from app.config import Config
from app.utils.logger import logger

def send_notification(title: str, message: str, priority: str = "default"):

    if not Config.NTFY_TOPIC:
        logger.warning("NTFY_TOPIC not configured")
        return

    url = f"{Config.NTFY_BASE_URL}/{Config.NTFY_TOPIC}"

    headers = {
        "Title": title,
        "Priority": priority
    }

    try:
        requests.post(
            url,
            data=message.encode("utf-8"),
            headers=headers,
            timeout=5
        )
    except Exception as e:
        logger.error(f"NTFY send failed: {e}")