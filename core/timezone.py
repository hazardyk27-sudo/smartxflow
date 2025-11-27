"""
SmartXFlow Timezone Configuration
All timestamps use Turkey timezone (Europe/Istanbul)
"""

import pytz
from datetime import datetime

TURKEY_TZ = pytz.timezone('Europe/Istanbul')

def now_turkey() -> datetime:
    """Get current time in Turkey timezone"""
    return datetime.now(TURKEY_TZ)

def now_turkey_iso() -> str:
    """Get current time in Turkey timezone as ISO string"""
    return now_turkey().isoformat()

def now_turkey_formatted() -> str:
    """Get current time in Turkey timezone as DD.MM.YYYY HH:MM format"""
    return now_turkey().strftime('%d.%m.%Y %H:%M')

def utc_to_turkey(dt: datetime) -> datetime:
    """Convert UTC datetime to Turkey timezone"""
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    return dt.astimezone(TURKEY_TZ)

def parse_to_turkey(timestamp_str: str) -> datetime:
    """Parse ISO timestamp string and convert to Turkey timezone"""
    if not timestamp_str:
        return now_turkey()
    
    try:
        timestamp_str = timestamp_str.replace('Z', '+00:00')
        
        if '+' in timestamp_str or '-' in timestamp_str[10:]:
            dt = datetime.fromisoformat(timestamp_str)
        else:
            dt = datetime.fromisoformat(timestamp_str)
            dt = pytz.utc.localize(dt)
        
        return dt.astimezone(TURKEY_TZ)
    except Exception:
        return now_turkey()

def format_turkey_time(timestamp_str: str, format_str: str = '%d.%m.%Y %H:%M') -> str:
    """Parse timestamp and format in Turkey timezone"""
    dt = parse_to_turkey(timestamp_str)
    return dt.strftime(format_str)

def format_time_only(timestamp_str: str) -> str:
    """Parse timestamp and return only time in HH:MM format (Turkey timezone)"""
    return format_turkey_time(timestamp_str, '%H:%M')

def format_date_only(timestamp_str: str) -> str:
    """Parse timestamp and return only date in DD.MM.YYYY format (Turkey timezone)"""
    return format_turkey_time(timestamp_str, '%d.%m.%Y')

def today_start_turkey() -> datetime:
    """Get today's start (00:00:00) in Turkey timezone"""
    now = now_turkey()
    return TURKEY_TZ.localize(datetime(now.year, now.month, now.day, 0, 0, 0))

def today_end_turkey() -> datetime:
    """Get today's end (23:59:59) in Turkey timezone"""
    now = now_turkey()
    return TURKEY_TZ.localize(datetime(now.year, now.month, now.day, 23, 59, 59))

def is_today_turkey(timestamp_str: str) -> bool:
    """Check if timestamp is from today (Turkey timezone)"""
    if not timestamp_str:
        return False
    try:
        dt = parse_to_turkey(timestamp_str)
        today = now_turkey().date()
        return dt.date() == today
    except Exception:
        return False
