from datetime import datetime, timezone
import pytz

TIMEZONE = pytz.timezone("Europe/Berlin")

def get_time_now():
    return datetime.now().astimezone(TIMEZONE).strftime("%H:%M")

def get_timestamp_now():
    return datetime.now().astimezone(TIMEZONE).isoformat()

def get_timestamp_now_offset():
    return TIMEZONE.utcoffset(datetime.now()).total_seconds()

def get_timestamp_now_epoche():
    from datetime import datetime
    return int(datetime.now().timestamp() + get_timestamp_now_offset())