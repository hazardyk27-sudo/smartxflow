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

try:
    from scraper_standalone.telegram_card_renderer import render_alarm_card_png, PLAYWRIGHT_AVAILABLE, check_chromium_available, mark_chromium_unavailable
    CARD_RENDERER_AVAILABLE = PLAYWRIGHT_AVAILABLE
except ImportError:
    try:
        from telegram_card_renderer import render_alarm_card_png, PLAYWRIGHT_AVAILABLE, check_chromium_available, mark_chromium_unavailable
        CARD_RENDERER_AVAILABLE = PLAYWRIGHT_AVAILABLE
    except ImportError:
        CARD_RENDERER_AVAILABLE = False
        def render_alarm_card_png(*args, **kwargs):
            raise RuntimeError("Card renderer not available")
        def check_chromium_available():
            return False
        def mark_chromium_unavailable():
            pass

logger = logging.getLogger(__name__)

TELEGRAM_MESSAGE_MODE = os.environ.get('TELEGRAM_MESSAGE_MODE', 'image')

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


MONTHS_TR = ['Oca', 'Şub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Ağu', 'Eyl', 'Eki', 'Kas', 'Ara']


def format_money(amount):
    """Format money with dots as thousand separators (£21.462)"""
    if amount is None:
        return "£0"
    formatted = f"{int(amount):,}".replace(",", ".")
    return f"£{formatted}"


def format_datetime_tr(utc_time_str):
    """Format UTC datetime to Turkish format (11.12 • 22:29)"""
    try:
        if isinstance(utc_time_str, str):
            utc_time_str = utc_time_str.replace('Z', '+00:00')
            if '+' not in utc_time_str and '-' not in utc_time_str[10:]:
                utc_time_str = utc_time_str + '+00:00'
            dt = datetime.fromisoformat(utc_time_str)
        else:
            dt = utc_time_str
        if TURKEY_TZ:
            tr_time = dt.astimezone(TURKEY_TZ)
        else:
            tr_time = dt
        return tr_time.strftime("%d.%m • %H:%M")
    except:
        return ""


def format_kickoff_tr(kickoff_utc):
    """Format kickoff to Turkish format (13 Ara • 20:00)"""
    try:
        if isinstance(kickoff_utc, str):
            kickoff_utc = kickoff_utc.replace('Z', '+00:00')
            if '+' not in kickoff_utc and '-' not in kickoff_utc[10:]:
                kickoff_utc = kickoff_utc + '+00:00'
            dt = datetime.fromisoformat(kickoff_utc)
        else:
            dt = kickoff_utc
        if TURKEY_TZ:
            tr_time = dt.astimezone(TURKEY_TZ)
        else:
            tr_time = dt
        day = tr_time.day
        month = MONTHS_TR[tr_time.month - 1]
        time_str = tr_time.strftime("%H:%M")
        return f"{day} {month} • {time_str}"
    except:
        return ""


def format_bigmoney_text(
    home: str,
    away: str,
    market: str,
    selection: str,
    money: float,
    alarm_time: str = None,
    total_money: float = None,
    kickoff_utc: str = None,
    previous_alarms: list = None,
    multiplier: int = None,
    volumes: dict = None
) -> str:
    """
    Format BigMoney alarm as rich text message matching card design.
    
    Args:
        home: Home team name
        away: Away team name
        market: Market type (1X2, OU25, BTTS)
        selection: Selection (1, X, 2, O, U, Y, N)
        money: Money amount (delta)
        alarm_time: Alarm time in ISO format
        total_money: Total accumulated money
        kickoff_utc: Match kickoff time
        previous_alarms: List of previous alarms
        multiplier: Alarm count
        volumes: Dict with selection volumes {selection: {volume, share}, total: X}
    """
    lines = []
    
    lines.append(f"🟠 <b>BIG MONEY</b> — {market}-{selection} seçeneğine yüksek para girişi oldu")
    
    if alarm_time:
        time_str = format_datetime_tr(alarm_time)
        lines.append(f"🕐 {time_str}")
    
    lines.append("")
    lines.append(f"⚽ <b>{home} – {away}</b>")
    lines.append("")
    
    lines.append(f"💰 {selection} {format_money(money)}")
    
    if total_money and total_money > money:
        lines.append(f"📈 Toplam: {format_money(total_money)}")
    
    lines.append("")
    
    if kickoff_utc:
        kickoff_str = format_kickoff_tr(kickoff_utc)
        lines.append(f"📅 Maç: {kickoff_str}")
        lines.append("")
    
    if previous_alarms and len(previous_alarms) > 0:
        lines.append("⏱️ Önceki:")
        for prev in previous_alarms[:4]:
            prev_time = format_datetime_tr(prev.get('time', ''))
            prev_money = format_money(prev.get('money', 0))
            lines.append(f"  • {prev_time} → {prev_money}")
        lines.append("")
    
    if multiplier and multiplier > 1:
        lines.append(f"×{multiplier} tetikleme")
        lines.append("")
    
    if volumes:
        lines.append("━━━━━━━━━━━━━━━━")
        lines.append("📊 Hacimler:")
        
        selections_order = ['1', 'X', '2', 'O', 'U', 'Y', 'N']
        for sel in selections_order:
            if sel in volumes and sel != 'total':
                vol_data = volumes[sel]
                if isinstance(vol_data, dict):
                    vol = vol_data.get('volume', 0)
                    share = vol_data.get('share', 0)
                    lines.append(f"  {sel}: {format_money(vol)} ({share:.0f}%)")
                else:
                    lines.append(f"  {sel}: {format_money(vol_data)}")
        
        if 'total' in volumes:
            lines.append(f"  Total: {format_money(volumes['total'])}")
    
    return "\n".join(lines)


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
    kickoff_utc: str = None,
    match_url: str = None,
    multiplier: int = None,
    old_odds: float = 0,
    new_odds: float = 0,
    drop_pct: float = 0,
    extra_info: str = "",
    message_mode: str = None
) -> bool:
    """
    Send alarm notification with visual card image using Playwright HTML screenshot.
    Falls back to Pillow image, then to text message if all fail.
    
    Args:
        alarm_type: Type of alarm (bigmoney, sharp, insider, etc.)
        home: Home team name
        away: Away team name
        market: Market type (1X2, OU25, BTTS)
        selection: Selection (1, X, 2, O, U, Y, N)
        alarm_time: Alarm time in ISO format
        money: Money amount for BigMoney alarms (delta)
        total_money: Total accumulated money
        previous_alarms: List of previous alarms for history
        kickoff_utc: Match kickoff time in UTC
        match_url: URL to match page
        multiplier: Alarm count multiplier
        old_odds: Opening odds (for dropping alarms)
        new_odds: Current odds (for dropping alarms)
        drop_pct: Drop percentage
        extra_info: Additional info to display
        message_mode: 'image' or 'text' (overrides env setting)
    
    Returns:
        True if notification sent successfully
    """
    mode = message_mode or TELEGRAM_MESSAGE_MODE
    
    if mode == 'text':
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
    
    caption = f"<b>🟠 {alarm_type.upper()}</b> — <i>{home} – {away}</i>"
    if match_url:
        caption += f'\n<a href="{match_url}">Maç linki</a>'
    
    if CARD_RENDERER_AVAILABLE and check_chromium_available():
        try:
            logger.info("[Telegram] Using Playwright card renderer...")
            png_bytes = render_alarm_card_png(
                alarm_type=alarm_type,
                home_team=home,
                away_team=away,
                market=market,
                selection=selection,
                alarm_time=alarm_time,
                kickoff_utc=kickoff_utc,
                delta_money=money,
                total_money=total_money,
                previous_entries=previous_alarms,
                match_url=match_url,
                multiplier=multiplier
            )
            
            image_buffer = BytesIO(png_bytes)
            result = send_telegram_photo(image_buffer, caption)
            
            if result:
                logger.info("[Telegram] Playwright card sent successfully")
                return True
            else:
                logger.warning("[Telegram] Playwright photo send failed, trying fallback...")
                
        except Exception as e:
            logger.warning(f"[Telegram] Playwright render failed: {e}, trying Pillow fallback...")
            mark_chromium_unavailable()
    
    if IMAGE_GENERATOR_AVAILABLE:
        try:
            logger.info("[Telegram] Using Pillow image generator...")
            image_buffer = generate_alarm_card(
                alarm_type=alarm_type,
                home_team=home,
                away_team=away,
                market=market,
                selection=selection,
                alarm_time=alarm_time,
                kickoff_utc=kickoff_utc,
                money=money,
                total_money=total_money,
                previous_alarms=previous_alarms,
                multiplier=multiplier
            )
            
            result = send_telegram_photo(image_buffer, caption)
            
            if result:
                logger.info("[Telegram] Pillow image sent successfully")
                return True
            else:
                logger.warning("[Telegram] Pillow photo send failed, falling back to text...")
                
        except Exception as e:
            logger.warning(f"[Telegram] Pillow image failed: {e}, falling back to text...")
    
    logger.info("[Telegram] Sending text message as final fallback")
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


def send_bigmoney_text(
    home: str,
    away: str,
    market: str,
    selection: str,
    money: float,
    alarm_time: str = None,
    total_money: float = None,
    kickoff_utc: str = None,
    previous_alarms: list = None,
    multiplier: int = None,
    volumes: dict = None
) -> bool:
    """
    Send BigMoney alarm as formatted text message.
    
    Args:
        home: Home team name
        away: Away team name
        market: Market type (1X2, OU25, BTTS)
        selection: Selection (1, X, 2, O, U, Y, N)
        money: Money amount (delta)
        alarm_time: Alarm time in ISO format
        total_money: Total accumulated money
        kickoff_utc: Match kickoff time
        previous_alarms: List of previous alarms
        multiplier: Alarm count
        volumes: Dict with selection volumes
    
    Returns:
        True if sent successfully
    """
    msg = format_bigmoney_text(
        home=home,
        away=away,
        market=market,
        selection=selection,
        money=money,
        alarm_time=alarm_time,
        total_money=total_money,
        kickoff_utc=kickoff_utc,
        previous_alarms=previous_alarms,
        multiplier=multiplier,
        volumes=volumes
    )
    return send_telegram_message(msg)


def send_test_bigmoney_text() -> bool:
    """Send a test BigMoney text message with sample data."""
    return send_bigmoney_text(
        home="Arsenal",
        away="Wolves",
        market="1X2",
        selection="1",
        money=21462,
        alarm_time=datetime.utcnow().isoformat() + "Z",
        total_money=302078,
        kickoff_utc="2025-12-13T20:00:00Z",
        previous_alarms=[
            {"time": "2025-12-11T19:29:00Z", "money": 25025},
            {"time": "2025-12-11T11:37:00Z", "money": 25569},
            {"time": "2025-12-09T01:06:00Z", "money": 27176},
        ],
        multiplier=5,
        volumes={
            '1': {'volume': 150234, 'share': 48},
            'X': {'volume': 85120, 'share': 27},
            '2': {'volume': 78450, 'share': 25},
            'total': 313804
        }
    )


def send_test_image(message_mode: str = None) -> bool:
    """
    Send a test BigMoney image to verify image notification.
    
    Args:
        message_mode: 'image' or 'text' (overrides env setting)
    """
    return send_alarm_with_image(
        alarm_type="bigmoney",
        home="Arsenal",
        away="Wolves",
        market="1X2",
        selection="1",
        alarm_time=datetime.utcnow().isoformat() + "Z",
        money=21462,
        total_money=302078,
        kickoff_utc="2025-12-13T20:00:00Z",
        multiplier=5,
        message_mode=message_mode,
        previous_alarms=[
            {"time": "2025-12-11T19:29:00Z", "money": 25025},
            {"time": "2025-12-14T21:49:00Z", "money": 106308},
            {"time": "2025-12-14T21:40:00Z", "money": 20612},
        ]
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Sending test image...")
    result = send_test_image()
    print(f"Test result: {'Success' if result else 'Failed'}")
