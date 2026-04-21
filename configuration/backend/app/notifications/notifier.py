import requests
from app.utils.logger import logger
from app.config import Config

def send_notification(title: str, message: str):
    """Send notification with UTF-8 support for emoji"""
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
        else:
            logger.error(f"NTFY send failed: {response.status_code}")
    
    except Exception as e:
        logger.error(f"NTFY send failed: {e}")