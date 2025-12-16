"""
Alarm Card Image Generator for Telegram Notifications
Generates visual alarm cards similar to the web UI
"""

from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from datetime import datetime
import pytz
import os

CARD_WIDTH = 400
CARD_PADDING = 20
LINE_HEIGHT = 28
HEADER_HEIGHT = 50

BG_COLOR = (30, 32, 36)
HEADER_BG = (40, 42, 48)
TEXT_WHITE = (255, 255, 255)
TEXT_GRAY = (150, 150, 150)
TEXT_MUTED = (100, 100, 100)
ORANGE = (255, 140, 0)
GREEN = (76, 175, 80)
RED = (244, 67, 54)
BLUE = (33, 150, 243)
DIVIDER_COLOR = (60, 62, 68)

ALARM_COLORS = {
    'bigmoney': ORANGE,
    'sharp': BLUE,
    'insider': (156, 39, 176),
    'dropping': RED,
    'volumeshock': (255, 193, 7),
    'publicmove': (0, 188, 212),
    'volumeleader': GREEN,
    'mim': (233, 30, 99),
}

ALARM_ICONS = {
    'bigmoney': '💰',
    'sharp': '🎯',
    'insider': '🔮',
    'dropping': '📉',
    'volumeshock': '⚡',
    'publicmove': '👥',
    'volumeleader': '🏆',
    'mim': '🔄',
}

ALARM_LABELS = {
    'bigmoney': 'BIG MONEY',
    'sharp': 'SHARP',
    'insider': 'INSIDER',
    'dropping': 'DROPPING',
    'volumeshock': 'VOLUME SHOCK',
    'publicmove': 'PUBLIC MOVE',
    'volumeleader': 'VOLUME LEADER',
    'mim': 'MIM',
}


def get_font(size, bold=False):
    try:
        if bold:
            return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
    except:
        return ImageFont.load_default()


def format_money(amount):
    if amount >= 1000000:
        return f"£{amount/1000000:.1f}M"
    elif amount >= 1000:
        return f"£{amount:,.0f}"
    return f"£{amount:.0f}"


def format_tr_time(utc_time):
    try:
        if isinstance(utc_time, str):
            utc_time = datetime.fromisoformat(utc_time.replace('Z', '+00:00'))
        tr_tz = pytz.timezone('Europe/Istanbul')
        tr_time = utc_time.astimezone(tr_tz)
        return tr_time.strftime("%d.%m %H:%M")
    except:
        return ""


def generate_bigmoney_card(
    home_team: str,
    away_team: str,
    market: str,
    selection: str,
    current_money: float,
    total_money: float = None,
    alarm_time: str = None,
    previous_alarms: list = None
) -> BytesIO:
    """
    Generate BigMoney alarm card image
    
    Args:
        home_team: Home team name
        away_team: Away team name
        market: Market type (1X2, OU25, BTTS)
        selection: Selection (1, X, 2, O, U, Y, N)
        current_money: Current alarm money amount
        total_money: Total accumulated money (optional)
        alarm_time: Alarm time in UTC (optional)
        previous_alarms: List of previous alarms [{"time": str, "money": float}, ...] (optional)
    
    Returns:
        BytesIO: PNG image buffer
    """
    prev_count = len(previous_alarms) if previous_alarms else 0
    prev_section_height = prev_count * LINE_HEIGHT + 40 if prev_count > 0 else 0
    
    card_height = (
        HEADER_HEIGHT +
        120 +
        (80 if total_money else 0) +
        prev_section_height +
        40
    )
    
    img = Image.new('RGB', (CARD_WIDTH, card_height), BG_COLOR)
    draw = ImageDraw.Draw(img)
    
    font_small = get_font(12)
    font_normal = get_font(14)
    font_medium = get_font(16)
    font_bold = get_font(16, bold=True)
    font_large = get_font(24, bold=True)
    font_xlarge = get_font(36, bold=True)
    
    draw.rectangle([0, 0, CARD_WIDTH, HEADER_HEIGHT], fill=HEADER_BG)
    
    alarm_color = ALARM_COLORS['bigmoney']
    draw.ellipse([CARD_PADDING, 15, CARD_PADDING + 10, 25], fill=alarm_color)
    
    header_text = f"BIG MONEY"
    draw.text((CARD_PADDING + 18, 12), header_text, fill=alarm_color, font=font_bold)
    
    if alarm_time:
        time_str = format_tr_time(alarm_time)
        draw.text((CARD_PADDING + 120, 14), f"• {time_str}", fill=TEXT_GRAY, font=font_small)
    
    y = HEADER_HEIGHT + 15
    
    match_text = f"{home_team} – {away_team}"
    draw.text((CARD_PADDING, y), match_text, fill=TEXT_WHITE, font=font_bold)
    
    money_text = format_money(current_money)
    money_width = draw.textlength(money_text, font=font_large)
    draw.text((CARD_WIDTH - CARD_PADDING - money_width, y), money_text, fill=alarm_color, font=font_large)
    
    y += 30
    market_text = f"{market} • {selection}"
    draw.text((CARD_PADDING, y), market_text, fill=TEXT_GRAY, font=font_normal)
    
    y += 45
    draw.line([(CARD_PADDING, y), (CARD_WIDTH - CARD_PADDING, y)], fill=DIVIDER_COLOR, width=1)
    y += 15
    
    if total_money:
        box_margin = 30
        box_height = 60
        draw.rounded_rectangle(
            [box_margin, y, CARD_WIDTH - box_margin, y + box_height],
            radius=8,
            fill=(40, 45, 50)
        )
        
        total_text = format_money(total_money)
        total_width = draw.textlength(total_text, font=font_xlarge)
        draw.text(
            ((CARD_WIDTH - total_width) / 2, y + 8),
            total_text,
            fill=alarm_color,
            font=font_xlarge
        )
        
        label_text = "BÜYÜK PARA GİRİŞİ"
        label_width = draw.textlength(label_text, font=font_small)
        draw.text(
            ((CARD_WIDTH - label_width) / 2, y + 42),
            label_text,
            fill=alarm_color,
            font=font_small
        )
        
        y += box_height + 20
    
    if previous_alarms and len(previous_alarms) > 0:
        y += 10
        draw.text((CARD_PADDING, y), "ÖNCEKİ", fill=TEXT_MUTED, font=font_small)
        y += 25
        
        for prev in previous_alarms[:5]:
            prev_time = format_tr_time(prev.get('time', ''))
            prev_money = format_money(prev.get('money', 0))
            
            draw.ellipse([CARD_PADDING, y + 4, CARD_PADDING + 6, y + 10], fill=alarm_color)
            draw.text((CARD_PADDING + 12, y - 2), prev_time, fill=TEXT_GRAY, font=font_normal)
            
            money_width = draw.textlength(prev_money, font=font_normal)
            draw.text((CARD_WIDTH - CARD_PADDING - money_width, y - 2), prev_money, fill=alarm_color, font=font_normal)
            
            y += LINE_HEIGHT
    
    buffer = BytesIO()
    img.save(buffer, format='PNG', quality=95)
    buffer.seek(0)
    
    return buffer


def generate_alarm_card(
    alarm_type: str,
    home_team: str,
    away_team: str,
    market: str,
    selection: str,
    alarm_time: str = None,
    **kwargs
) -> BytesIO:
    """
    Generate generic alarm card image
    
    Args:
        alarm_type: Type of alarm (sharp, insider, dropping, etc.)
        home_team: Home team name
        away_team: Away team name
        market: Market type
        selection: Selection
        alarm_time: Alarm time in UTC
        **kwargs: Additional alarm-specific data
    
    Returns:
        BytesIO: PNG image buffer
    """
    alarm_type = alarm_type.lower()
    
    if alarm_type == 'bigmoney':
        return generate_bigmoney_card(
            home_team=home_team,
            away_team=away_team,
            market=market,
            selection=selection,
            current_money=kwargs.get('money', 0),
            total_money=kwargs.get('total_money'),
            alarm_time=alarm_time,
            previous_alarms=kwargs.get('previous_alarms')
        )
    
    card_height = 140
    
    img = Image.new('RGB', (CARD_WIDTH, card_height), BG_COLOR)
    draw = ImageDraw.Draw(img)
    
    font_small = get_font(12)
    font_normal = get_font(14)
    font_bold = get_font(16, bold=True)
    font_large = get_font(24, bold=True)
    
    draw.rectangle([0, 0, CARD_WIDTH, HEADER_HEIGHT], fill=HEADER_BG)
    
    alarm_color = ALARM_COLORS.get(alarm_type, BLUE)
    alarm_label = ALARM_LABELS.get(alarm_type, alarm_type.upper())
    
    draw.ellipse([CARD_PADDING, 15, CARD_PADDING + 10, 25], fill=alarm_color)
    draw.text((CARD_PADDING + 18, 12), alarm_label, fill=alarm_color, font=font_bold)
    
    if alarm_time:
        time_str = format_tr_time(alarm_time)
        draw.text((CARD_PADDING + 150, 14), f"• {time_str}", fill=TEXT_GRAY, font=font_small)
    
    y = HEADER_HEIGHT + 15
    
    match_text = f"{home_team} – {away_team}"
    draw.text((CARD_PADDING, y), match_text, fill=TEXT_WHITE, font=font_bold)
    
    y += 30
    market_text = f"{market} • {selection}"
    draw.text((CARD_PADDING, y), market_text, fill=TEXT_GRAY, font=font_normal)
    
    if alarm_type == 'dropping':
        odds_info = kwargs.get('odds_info', '')
        if odds_info:
            y += 25
            draw.text((CARD_PADDING, y), odds_info, fill=RED, font=font_normal)
    
    elif alarm_type in ['sharp', 'insider', 'volumeshock', 'volumeleader']:
        extra_info = kwargs.get('extra_info', '')
        if extra_info:
            info_width = draw.textlength(extra_info, font=font_large)
            draw.text((CARD_WIDTH - CARD_PADDING - info_width, HEADER_HEIGHT + 15), extra_info, fill=alarm_color, font=font_large)
    
    buffer = BytesIO()
    img.save(buffer, format='PNG', quality=95)
    buffer.seek(0)
    
    return buffer


if __name__ == "__main__":
    img_buffer = generate_bigmoney_card(
        home_team="Arsenal",
        away_team="Chelsea",
        market="1X2",
        selection="2",
        current_money=50000,
        total_money=485780,
        alarm_time="2025-12-14T23:00:00Z",
        previous_alarms=[
            {"time": "2025-12-14T21:59:00Z", "money": 37170},
            {"time": "2025-12-14T21:49:00Z", "money": 106308},
            {"time": "2025-12-14T21:40:00Z", "money": 20612},
            {"time": "2025-12-13T14:05:00Z", "money": 31553},
        ]
    )
    
    with open("/tmp/test_bigmoney_card.png", "wb") as f:
        f.write(img_buffer.getvalue())
    
    print("Test image saved to /tmp/test_bigmoney_card.png")
