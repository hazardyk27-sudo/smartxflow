"""
SmartXFlow Timezone Configuration
All timestamps use Turkey timezone (Europe/Istanbul)
"""

import pytz
from datetime import datetime
from typing import Optional

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

def parse_match_datetime(match_date_str: str) -> Optional[datetime]:
    """
    Parse match date string to datetime object in Turkey timezone.
    
    Handles various formats:
    - "DD.Mon HH:MM:SS" (with space)
    - "DD.MonHH:MM:SS" (without space, from dropping markets)
    - "DD.MM HH:MM"
    - "DD.MMHH:MM" (without space)
    
    Args:
        match_date_str: Match date string in various formats (Turkey time)
    
    Returns:
        datetime object in Turkey timezone, or None if parsing fails
    """
    if not match_date_str:
        return None
    
    try:
        import re
        
        match_date_str = match_date_str.strip()
        today = now_turkey()
        current_year = today.year
        
        month_map = {
            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
            'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
            '01': 1, '02': 2, '03': 3, '04': 4, '05': 5, '06': 6,
            '07': 7, '08': 8, '09': 9, '10': 10, '11': 11, '12': 12,
            '1': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6,
            '7': 7, '8': 8, '9': 9
        }
        
        patterns = [
            r'^(\d{1,2})\.(\w{3})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?',
            r'^(\d{1,2})\.(\w{3})(\d{1,2}):(\d{2})(?::(\d{2}))?',
            r'^(\d{1,2})\.(\d{1,2})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?',
            r'^(\d{1,2})\.(\d{1,2})(\d{1,2}):(\d{2})(?::(\d{2}))?',
        ]
        
        for pattern in patterns:
            match = re.match(pattern, match_date_str, re.IGNORECASE)
            if match:
                day = int(match.group(1))
                month_part = match.group(2)
                hour = int(match.group(3))
                minute = int(match.group(4))
                second = int(match.group(5)) if match.group(5) else 0
                
                month_lower = month_part.lower()[:3] if not month_part.isdigit() else month_part
                month = month_map.get(month_lower, today.month)
                
                match_dt = TURKEY_TZ.localize(datetime(current_year, month, day, hour, minute, second))
                return match_dt
        
        return None
        
    except Exception as e:
        print(f"[Timezone] Error parsing match datetime '{match_date_str}': {e}")
        return None


def is_match_started(match_date_str: str) -> bool:
    """
    Check if match has already started (kickoff time passed).
    
    CRITICAL: This checks if the match kickoff time has passed.
    Used to prevent processing data for matches that have already started.
    
    Args:
        match_date_str: Match date in format "DD.Mon HH:MM:SS" or "DD.Mon HH:MM" (Turkey time)
    
    Returns:
        True if match has started (kickoff time passed), False otherwise
    """
    kickoff_dt = parse_match_datetime(match_date_str)
    if not kickoff_dt:
        return False
    
    now = now_turkey()
    return now >= kickoff_dt


def get_kickoff_utc(match_date_str: str) -> Optional[str]:
    """
    Convert match kickoff time from Turkey timezone to UTC ISO format.
    
    Args:
        match_date_str: Match date in format "DD.Mon HH:MM:SS" (Turkey time)
    
    Returns:
        UTC ISO format string, or None if parsing fails
    """
    kickoff_tr = parse_match_datetime(match_date_str)
    if not kickoff_tr:
        return None
    
    kickoff_utc = kickoff_tr.astimezone(pytz.UTC)
    return kickoff_utc.strftime('%Y-%m-%dT%H:%M:%S')


def is_match_today_or_future(match_date_str: str) -> bool:
    """
    Check if match date is today or in the future (Turkey timezone).
    Used for filtering matches that haven't happened yet.
    
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

def _extract_match_date(match_date_str: str):
    """
    Internal helper to extract date from match date string.
    Returns (day, month, year) tuple or None if parsing fails.
    """
    if not match_date_str:
        return None
    
    try:
        import re
        from datetime import date
        
        today = now_turkey().date()
        current_year = today.year
        
        match_date_str = match_date_str.strip()
        
        day_match = re.match(r'^(\d{1,2})\.(\w+)', match_date_str)
        if not day_match:
            return None
            
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
        
        return date(current_year, month, day)
        
    except Exception:
        return None


def is_match_today(match_date_str: str) -> bool:
    """
    Check if match date is today (D) - Turkey timezone.
    
    Per REFERANS DOKÜMANI Section 3:
    - D (Today): fixture_date == today
    - Shows in "Gunun Maclari"
    - Can receive data (if in arbworld)
    
    Args:
        match_date_str: Match date in format "DD.Mon HH:MM:SS" etc.
    
    Returns:
        True if match is today, False otherwise
    """
    match_date = _extract_match_date(match_date_str)
    if not match_date:
        return False
    
    today = now_turkey().date()
    return match_date == today


def is_yesterday_turkey(match_date_str: str) -> bool:
    """
    Check if match date is yesterday (D-1) - Turkey timezone.
    
    Per REFERANS DOKÜMANI Section 3:
    - D-1 (Yesterday): fixture_date == yesterday
    - Shows in "Dunun Maclari"
    - NO new data (static mode only)
    
    Args:
        match_date_str: Match date in format "DD.Mon HH:MM:SS" etc.
    
    Returns:
        True if match is yesterday, False otherwise
    """
    match_date = _extract_match_date(match_date_str)
    if not match_date:
        return False
    
    from datetime import timedelta
    today = now_turkey().date()
    yesterday = today - timedelta(days=1)
    
    return match_date == yesterday


def is_match_d2_or_older(match_date_str: str) -> bool:
    """
    Check if match date is D-2 or older - Turkey timezone.
    
    Per REFERANS DOKÜMANI Section 3:
    - D-2+ (Old): fixture_date <= D-2
    - Should NOT be shown in UI
    
    Args:
        match_date_str: Match date in format "DD.Mon HH:MM:SS" etc.
    
    Returns:
        True if match is D-2 or older, False otherwise
    """
    match_date = _extract_match_date(match_date_str)
    if not match_date:
        return False
    
    from datetime import timedelta
    today = now_turkey().date()
    d_minus_2 = today - timedelta(days=2)
    
    return match_date <= d_minus_2


def get_match_lifecycle_status(match_date_str: str) -> str:
    """
    Get the lifecycle status of a match based on its date.
    
    Per REFERANS DOKÜMANI Section 3:
    - "D": Today's match (can show, can update if in arbworld)
    - "D-1": Yesterday's match (can show, static only)
    - "D-2+": Old match (should not show)
    - "FUTURE": Future match
    
    Args:
        match_date_str: Match date in format "DD.Mon HH:MM:SS" etc.
    
    Returns:
        Lifecycle status string
    """
    match_date = _extract_match_date(match_date_str)
    if not match_date:
        return "UNKNOWN"
    
    from datetime import timedelta
    today = now_turkey().date()
    yesterday = today - timedelta(days=1)
    
    if match_date > today:
        return "FUTURE"
    elif match_date == today:
        return "D"
    elif match_date == yesterday:
        return "D-1"
    else:
        return "D-2+"
