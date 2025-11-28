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
    """Parse ISO timestamp string and convert to Turkey timezone.
    
    Note: Standalone scraper saves timestamps in TR time without offset.
    So if no offset is present, assume it's already TR time (not UTC).
    """
    if not timestamp_str:
        return now_turkey()
    
    try:
        if 'Z' in timestamp_str:
            timestamp_str = timestamp_str.replace('Z', '+00:00')
            dt = datetime.fromisoformat(timestamp_str)
            return dt.astimezone(TURKEY_TZ)
        
        if '+03:00' in timestamp_str:
            dt = datetime.fromisoformat(timestamp_str)
            return dt.replace(tzinfo=TURKEY_TZ)
        
        if '+' in timestamp_str or '-' in timestamp_str[10:]:
            dt = datetime.fromisoformat(timestamp_str)
            return dt.astimezone(TURKEY_TZ)
        
        dt = datetime.fromisoformat(timestamp_str)
        return TURKEY_TZ.localize(dt)
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

def is_match_today_or_future(match_date_str: str) -> bool:
    """
    Check if match date is today or in the future (Turkey timezone).
    Used for alarm filtering - show alarms for matches that haven't happened yet.
    
    Args:
        match_date_str: Match date in format "DD.Mon HH:MM:SS" or "DD.MM HH:MM" etc.
    
    Returns:
        True if match is today or future, False if match is in the past
    """
    if not match_date_str:
        return True
    
    try:
        today = now_turkey().date()
        current_year = today.year
        
        import re
        
        match_date_str = match_date_str.strip()
        
        day_match = re.match(r'^(\d{1,2})\.(\w+)', match_date_str)
        if day_match:
            day = int(day_match.group(1))
            month_part = day_match.group(2)
            
            month_map = {
                'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
                '01': 1, '02': 2, '03': 3, '04': 4, '05': 5, '06': 6,
                '07': 7, '08': 8, '09': 9, '10': 10, '11': 11, '12': 12,
                '1': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6,
                '7': 7, '8': 8, '9': 9
            }
            
            month_lower = month_part.lower()[:3] if not month_part.isdigit() else month_part
            month = month_map.get(month_lower, today.month)
            
            from datetime import date
            match_date = date(current_year, month, day)
            
            if match_date < today:
                if month < today.month or (month == today.month and day < today.day):
                    pass
            
            return match_date >= today
        
        return True
        
    except Exception as e:
        return True

def is_yesterday_turkey(match_date_str: str) -> bool:
    """
    Check if match date is yesterday (Turkey timezone).
    Used for "Yesterday's Matches" filter.
    """
    if not match_date_str:
        return False
    
    try:
        from datetime import timedelta
        today = now_turkey().date()
        yesterday = today - timedelta(days=1)
        current_year = today.year
        
        import re
        
        match_date_str = match_date_str.strip()
        
        day_match = re.match(r'^(\d{1,2})\.(\w+)', match_date_str)
        if day_match:
            day = int(day_match.group(1))
            month_part = day_match.group(2)
            
            month_map = {
                'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
                '01': 1, '02': 2, '03': 3, '04': 4, '05': 5, '06': 6,
                '07': 7, '08': 8, '09': 9, '10': 10, '11': 11, '12': 12,
                '1': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6,
                '7': 7, '8': 8, '9': 9
            }
            
            month_lower = month_part.lower()[:3] if not month_part.isdigit() else month_part
            month = month_map.get(month_lower, today.month)
            
            from datetime import date
            match_date = date(current_year, month, day)
            
            return match_date == yesterday
        
        return False
        
    except Exception:
        return False
