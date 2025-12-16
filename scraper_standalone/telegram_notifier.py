"""
Telegram Notification Module for SmartXFlow
Single responsibility: Send messages to Telegram with retry and rate limit handling
"""

import os
import time
import logging
from typing import Optional
from datetime import datetime
from io import BytesIO

try:
    import httpx
    USE_HTTPX = True
except ImportError:
    import requests
    USE_HTTPX = False

try:
    import pytz
    TURKEY_TZ = pytz.timezone('Europe/Istanbul')
except ImportError:
    TURKEY_TZ = None

try:
    from scraper_standalone.image_generator import generate_alarm_card
    IMAGE_GENERATOR_AVAILABLE = True
except ImportError:
    try:
        from image_generator import generate_alarm_card
        IMAGE_GENERATOR_AVAILABLE = True
    except ImportError:
        IMAGE_GENERATOR_AVAILABLE = False

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"
TELEGRAM_PHOTO_URL = "https://api.telegram.org/bot{token}/sendPhoto"

def get_telegram_credentials() -> tuple:
    """Get Telegram credentials from environment"""
    token = os.environ.get('TELEGRAM_BOT_TOKEN') or os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    return token, chat_id

def send_telegram_message(text: str, token: Optional[str] = None, chat_id: Optional[str] = None) -> bool:
    """
    Send a message to Telegram with retry and rate limit handling.
    
    Args:
        text: Message text to send
        token: Bot token (optional, reads from env if not provided)
        chat_id: Chat ID (optional, reads from env if not provided)
    
    Returns:
        True if message sent successfully, False otherwise
    """
    if not token:
        token, env_chat_id = get_telegram_credentials()
        if not chat_id:
            chat_id = env_chat_id
    
    if not token or not chat_id:
        logger.warning("[Telegram] Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
        return False
    
    url = TELEGRAM_API_URL.format(token=token)
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
        "parse_mode": "HTML"
    }
    
    max_retries = 3
    retry_delays = [2, 5, 10]
    
    for attempt in range(max_retries):
        try:
            if USE_HTTPX:
                response = httpx.post(url, json=payload, timeout=30)
                status_code = response.status_code
                response_json = response.json() if response.status_code == 200 else {}
            else:
                response = requests.post(url, json=payload, timeout=30)
                status_code = response.status_code
                response_json = response.json() if response.status_code == 200 else {}
            
            if status_code == 200:
                logger.info(f"[Telegram] Message sent successfully")
                return True
            
            elif status_code == 429:
                retry_after = response_json.get('parameters', {}).get('retry_after', retry_delays[attempt])
                logger.warning(f"[Telegram] Rate limited. Waiting {retry_after}s before retry {attempt + 1}/{max_retries}")
                time.sleep(retry_after)
                continue
            
            else:
                logger.error(f"[Telegram] Failed with status {status_code}: {response.text}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delays[attempt])
                    continue
                return False
                
        except Exception as e:
            logger.error(f"[Telegram] Error on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delays[attempt])
                continue
            return False
    
    return False


def send_telegram_photo(
    photo: BytesIO,
    caption: str = "",
    token: Optional[str] = None,
    chat_id: Optional[str] = None
) -> bool:
    """
    Send a photo to Telegram with retry and rate limit handling.
    
    Args:
        photo: BytesIO buffer containing the image
        caption: Optional caption for the photo
        token: Bot token (optional, reads from env if not provided)
        chat_id: Chat ID (optional, reads from env if not provided)
    
    Returns:
        True if photo sent successfully, False otherwise
    """
    if not token:
        token, env_chat_id = get_telegram_credentials()
        if not chat_id:
            chat_id = env_chat_id
    
    if not token or not chat_id:
        logger.warning("[Telegram] Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
        return False
    
    url = TELEGRAM_PHOTO_URL.format(token=token)
    
    max_retries = 3
    retry_delays = [2, 5, 10]
    
    for attempt in range(max_retries):
        try:
            photo.seek(0)
            files = {"photo": ("alarm.png", photo, "image/png")}
            data = {"chat_id": chat_id}
            if caption:
                data["caption"] = caption
                data["parse_mode"] = "HTML"
            
            if USE_HTTPX:
                response = httpx.post(url, files=files, data=data, timeout=30)
                status_code = response.status_code
                response_json = response.json() if response.status_code == 200 else {}
            else:
                response = requests.post(url, files=files, data=data, timeout=30)
                status_code = response.status_code
                response_json = response.json() if response.status_code == 200 else {}
            
            if status_code == 200:
                logger.info(f"[Telegram] Photo sent successfully")
                return True
            
            elif status_code == 429:
                retry_after = response_json.get('parameters', {}).get('retry_after', retry_delays[attempt])
                logger.warning(f"[Telegram] Rate limited. Waiting {retry_after}s before retry {attempt + 1}/{max_retries}")
                time.sleep(retry_after)
                continue
            
            else:
                logger.error(f"[Telegram] Photo failed with status {status_code}: {response.text}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delays[attempt])
                    continue
                return False
                
        except Exception as e:
            logger.error(f"[Telegram] Photo error on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delays[attempt])
                continue
            return False
    
    return False


def format_alarm_message(
    alarm_type: str,
    home: str,
    away: str,
    market: str,
    selection: str,
    delta: float = 0,
    old_odds: float = 0,
    new_odds: float = 0,
    drop_pct: float = 0,
    level: str = "",
    extra_info: str = ""
) -> str:
    """
    Format alarm message for Telegram.
    
    Returns formatted message string.
    """
    if TURKEY_TZ:
        now = datetime.now(TURKEY_TZ)
    else:
        now = datetime.utcnow()
    
    timestamp = now.strftime('%Y-%m-%d %H:%M')
    
    emoji_map = {
        'SHARP': '🎯',
        'INSIDER': '🕵️',
        'BIG_MONEY': '💰',
        'BIGMONEY': '💰',
        'VOLUME_SHOCK': '⚡',
        'VOLUMESHOCK': '⚡',
        'DROPPING': '📉',
        'PUBLIC_MOVE': '👥',
        'PUBLICMOVE': '👥',
        'VOLUME_LEADER': '🏆',
        'VOLUMELEADER': '🏆',
        'MIM': '🔄'
    }
    
    emoji = emoji_map.get(alarm_type.upper(), '🚨')
    level_str = f" ({level})" if level else ""
    
    lines = [
        f"{emoji} <b>{alarm_type.upper()}</b>{level_str}",
        f"<b>{home}</b> vs <b>{away}</b>",
        f"Market: {market} / {selection}"
    ]
    
    if delta > 0:
        lines.append(f"Money: +£{delta:,.0f} (son 10dk)")
    
    if old_odds > 0 and new_odds > 0:
        lines.append(f"Odds: {old_odds:.2f} → {new_odds:.2f} ({drop_pct:.1f}%)")
    
    if extra_info:
        lines.append(extra_info)
    
    lines.append(f"TR: {timestamp}")
    
    return "\n".join(lines)

def send_alarm_with_image(
    alarm_type: str,
    home: str,
    away: str,
    market: str,
    selection: str,
    alarm_time: str = None,
    money: float = 0,
    total_money: float = None,
    previous_alarms: list = None,
    old_odds: float = 0,
    new_odds: float = 0,
    drop_pct: float = 0,
    extra_info: str = ""
) -> bool:
    """
    Send alarm notification with visual card image.
    Falls back to text message if image generation fails.
    
    Args:
        alarm_type: Type of alarm (bigmoney, sharp, insider, etc.)
        home: Home team name
        away: Away team name
        market: Market type (1X2, OU25, BTTS)
        selection: Selection (1, X, 2, O, U, Y, N)
        alarm_time: Alarm time in ISO format
        money: Money amount for BigMoney alarms
        total_money: Total accumulated money
        previous_alarms: List of previous alarms for history
        old_odds: Opening odds (for dropping alarms)
        new_odds: Current odds (for dropping alarms)
        drop_pct: Drop percentage
        extra_info: Additional info to display
    
    Returns:
        True if notification sent successfully
    """
    if not IMAGE_GENERATOR_AVAILABLE:
        logger.warning("[Telegram] Image generator not available, falling back to text")
        msg = format_alarm_message(
            alarm_type=alarm_type,
            home=home,
            away=away,
            market=market,
            selection=selection,
            delta=money,
            old_odds=old_odds,
            new_odds=new_odds,
            drop_pct=drop_pct,
            extra_info=extra_info
        )
        return send_telegram_message(msg)
    
    try:
        if alarm_type.lower() == 'dropping':
            odds_info = f"{old_odds:.2f} → {new_odds:.2f} ({drop_pct:.1f}%)" if old_odds > 0 else ""
            image_buffer = generate_alarm_card(
                alarm_type=alarm_type,
                home_team=home,
                away_team=away,
                market=market,
                selection=selection,
                alarm_time=alarm_time,
                odds_info=odds_info
            )
        elif alarm_type.lower() == 'bigmoney':
            image_buffer = generate_alarm_card(
                alarm_type=alarm_type,
                home_team=home,
                away_team=away,
                market=market,
                selection=selection,
                alarm_time=alarm_time,
                money=money,
                total_money=total_money,
                previous_alarms=previous_alarms
            )
        else:
            image_buffer = generate_alarm_card(
                alarm_type=alarm_type,
                home_team=home,
                away_team=away,
                market=market,
                selection=selection,
                alarm_time=alarm_time,
                extra_info=extra_info
            )
        
        if TURKEY_TZ:
            now = datetime.now(TURKEY_TZ)
        else:
            now = datetime.utcnow()
        
        caption = f"⚽ {home} vs {away}\n🕐 {now.strftime('%d.%m %H:%M')} TR"
        
        result = send_telegram_photo(image_buffer, caption)
        
        if not result:
            logger.warning("[Telegram] Photo send failed, falling back to text")
            msg = format_alarm_message(
                alarm_type=alarm_type,
                home=home,
                away=away,
                market=market,
                selection=selection,
                delta=money,
                old_odds=old_odds,
                new_odds=new_odds,
                drop_pct=drop_pct,
                extra_info=extra_info
            )
            return send_telegram_message(msg)
        
        return result
        
    except Exception as e:
        logger.error(f"[Telegram] Image generation failed: {e}, falling back to text")
        msg = format_alarm_message(
            alarm_type=alarm_type,
            home=home,
            away=away,
            market=market,
            selection=selection,
            delta=money,
            old_odds=old_odds,
            new_odds=new_odds,
            drop_pct=drop_pct,
            extra_info=extra_info
        )
        return send_telegram_message(msg)


def send_test_message() -> bool:
    """Send a test message to verify Telegram configuration."""
    return send_telegram_message("✅ SmartXFlow Telegram test başarılı!")


def send_test_image() -> bool:
    """Send a test BigMoney image to verify image notification."""
    return send_alarm_with_image(
        alarm_type="bigmoney",
        home="Arsenal",
        away="Chelsea",
        market="1X2",
        selection="2",
        alarm_time=datetime.utcnow().isoformat() + "Z",
        money=50000,
        total_money=485780,
        previous_alarms=[
            {"time": "2025-12-14T21:59:00Z", "money": 37170},
            {"time": "2025-12-14T21:49:00Z", "money": 106308},
            {"time": "2025-12-14T21:40:00Z", "money": 20612},
        ]
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Sending test image...")
    result = send_test_image()
    print(f"Test result: {'Success' if result else 'Failed'}")
