"""
Alarm Card Image Generator for Telegram Notifications
Generates visual alarm cards matching the web UI design exactly
"""

from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from datetime import datetime
import pytz
import os

CARD_WIDTH = 420
CARD_PADDING = 20

BG_COLOR = (13, 17, 23)
CARD_BG = (22, 27, 34)
HEADER_BG = (22, 27, 34)
DIVIDER_COLOR = (48, 54, 61)
TEXT_WHITE = (255, 255, 255)
TEXT_SECONDARY = (139, 148, 158)
TEXT_MUTED = (110, 118, 129)
ORANGE = (249, 115, 22)
GREEN = (34, 197, 94)
GREEN_DARK = (15, 31, 22)
GREEN_DARKER = (11, 21, 16)
BUTTON_GREEN = (34, 163, 74)

ALARM_COLORS = {
    'bigmoney': ORANGE,
    'sharp': (59, 130, 246),
    'insider': (168, 85, 247),
    'dropping': (239, 68, 68),
    'volumeshock': (234, 179, 8),
    'publicmove': (6, 182, 212),
    'volumeleader': GREEN,
    'mim': (236, 72, 153),
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
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except:
            continue
    return ImageFont.load_default()


def format_money(amount):
    if amount is None:
        return "£0"
    if amount >= 1000000:
        return f"£{amount/1000000:,.1f}M"
    elif amount >= 1000:
        return f"£{amount:,.0f}"
    return f"£{int(amount)}"


def format_tr_time(utc_time):
    try:
        if isinstance(utc_time, str):
            utc_time = utc_time.replace('Z', '+00:00')
            if '+' not in utc_time and '-' not in utc_time[10:]:
                utc_time = utc_time + '+00:00'
            utc_time = datetime.fromisoformat(utc_time)
        tr_tz = pytz.timezone('Europe/Istanbul')
        tr_time = utc_time.astimezone(tr_tz)
        return tr_time.strftime("%d.%m %H:%M")
    except:
        return ""


def format_kickoff(kickoff_utc):
    try:
        if isinstance(kickoff_utc, str):
            kickoff_utc = kickoff_utc.replace('Z', '+00:00')
            if '+' not in kickoff_utc and '-' not in kickoff_utc[10:]:
                kickoff_utc = kickoff_utc + '+00:00'
            kickoff_utc = datetime.fromisoformat(kickoff_utc)
        tr_tz = pytz.timezone('Europe/Istanbul')
        tr_time = kickoff_utc.astimezone(tr_tz)
        months_tr = ['Oca', 'Şub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Ağu', 'Eyl', 'Eki', 'Kas', 'Ara']
        day = tr_time.day
        month = months_tr[tr_time.month - 1]
        time_str = tr_time.strftime("%H:%M")
        return f"{day} {month} • {time_str}"
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
    kickoff_utc: str = None,
    previous_alarms: list = None,
    multiplier: int = None
) -> BytesIO:
    prev_count = len(previous_alarms) if previous_alarms else 0
    prev_section_height = (prev_count * 32) + 40 if prev_count > 0 else 0
    
    card_height = (
        60 +
        45 +
        25 +
        1 +
        30 +
        100 +
        (50 if total_money else 0) +
        prev_section_height +
        (30 if multiplier else 0) +
        60 +
        20
    )
    
    img = Image.new('RGB', (CARD_WIDTH, card_height), BG_COLOR)
    draw = ImageDraw.Draw(img)
    
    draw.rounded_rectangle([10, 10, CARD_WIDTH - 10, card_height - 10], radius=12, fill=CARD_BG)
    
    font_small = get_font(11)
    font_normal = get_font(13)
    font_medium = get_font(14)
    font_semibold = get_font(16, bold=True)
    font_large = get_font(20, bold=True)
    font_xlarge = get_font(32, bold=True)
    font_tiny = get_font(10)
    
    y = 25
    
    dot_x = CARD_PADDING + 10
    draw.ellipse([dot_x, y + 3, dot_x + 8, y + 11], fill=ORANGE)
    
    label_x = dot_x + 14
    draw.text((label_x, y - 2), "BIG MONEY", fill=ORANGE, font=font_semibold)
    
    if alarm_time:
        time_str = format_tr_time(alarm_time)
        time_width = draw.textlength(time_str, font=font_small)
        draw.text((CARD_WIDTH - CARD_PADDING - 10 - time_width, y + 1), time_str, fill=TEXT_SECONDARY, font=font_small)
    
    y += 35
    
    match_text = f"{home_team} – {away_team}"
    draw.text((CARD_PADDING + 10, y), match_text, fill=TEXT_WHITE, font=font_semibold)
    
    money_text = format_money(current_money)
    money_width = draw.textlength(money_text, font=font_large)
    draw.text((CARD_WIDTH - CARD_PADDING - 10 - money_width, y - 2), money_text, fill=ORANGE, font=font_large)
    
    y += 28
    market_text = f"{market} · {selection}"
    draw.text((CARD_PADDING + 10, y), market_text, fill=TEXT_SECONDARY, font=font_normal)
    
    y += 30
    draw.line([(CARD_PADDING + 10, y), (CARD_WIDTH - CARD_PADDING - 10, y)], fill=DIVIDER_COLOR, width=1)
    
    y += 15
    if kickoff_utc:
        kickoff_str = format_kickoff(kickoff_utc)
        draw.text((CARD_PADDING + 10, y), kickoff_str, fill=TEXT_SECONDARY, font=font_normal)
    
    y += 30
    
    box_margin = 25
    box_height = 75
    box_left = box_margin
    box_right = CARD_WIDTH - box_margin
    box_top = y
    box_bottom = y + box_height
    
    for i in range(box_height):
        ratio = i / box_height
        r = int(GREEN_DARK[0] * (1 - ratio) + GREEN_DARKER[0] * ratio)
        g = int(GREEN_DARK[1] * (1 - ratio) + GREEN_DARKER[1] * ratio)
        b = int(GREEN_DARK[2] * (1 - ratio) + GREEN_DARKER[2] * ratio)
        draw.line([(box_left, box_top + i), (box_right, box_top + i)], fill=(r, g, b))
    
    draw.rounded_rectangle([box_left, box_top, box_right, box_bottom], radius=10, outline=(30, 60, 40), width=1)
    
    display_money = total_money if total_money else current_money
    money_big = format_money(display_money)
    money_big_width = draw.textlength(money_big, font=font_xlarge)
    money_big_x = (CARD_WIDTH - money_big_width) / 2
    draw.text((money_big_x, box_top + 12), money_big, fill=ORANGE, font=font_xlarge)
    
    label_text = "BÜYÜK PARA GİRİŞİ"
    label_width = draw.textlength(label_text, font=font_tiny)
    label_x = (CARD_WIDTH - label_width) / 2
    draw.text((label_x, box_top + 50), label_text, fill=ORANGE, font=font_tiny)
    
    y = box_bottom + 15
    
    if total_money and total_money != current_money:
        total_str = format_money(total_money)
        total_label = f"{total_str}"
        total_width = draw.textlength(total_label, font=font_medium)
        total_x = (CARD_WIDTH - total_width - 60) / 2
        draw.text((total_x, y), total_label, fill=TEXT_SECONDARY, font=font_medium)
        
        toplam_text = "TOPLAM"
        draw.text((total_x + total_width + 8, y + 1), toplam_text, fill=GREEN, font=font_small)
        
        y += 35
    
    if previous_alarms and len(previous_alarms) > 0:
        y += 5
        draw.text((CARD_PADDING + 10, y), "ÖNCEKİ", fill=TEXT_MUTED, font=font_tiny)
        y += 22
        
        for prev in previous_alarms[:5]:
            prev_time = format_tr_time(prev.get('time', ''))
            prev_money = format_money(prev.get('money', 0))
            
            draw.ellipse([CARD_PADDING + 10, y + 5, CARD_PADDING + 16, y + 11], fill=ORANGE)
            
            draw.text((CARD_PADDING + 24, y), prev_time, fill=TEXT_SECONDARY, font=font_normal)
            
            money_w = draw.textlength(prev_money, font=font_normal)
            draw.text((CARD_WIDTH - CARD_PADDING - 10 - money_w, y), prev_money, fill=ORANGE, font=font_normal)
            
            y += 32
    
    if multiplier and multiplier > 1:
        y += 5
        mult_text = f"×{multiplier}"
        mult_width = draw.textlength(mult_text, font=font_small)
        mult_x = CARD_PADDING + 10
        draw.text((mult_x, y), mult_text, fill=TEXT_MUTED, font=font_small)
        y += 25
    
    y += 10
    btn_height = 38
    btn_margin = 25
    btn_left = btn_margin
    btn_right = CARD_WIDTH - btn_margin
    btn_top = y
    btn_bottom = y + btn_height
    
    draw.rounded_rectangle([btn_left, btn_top, btn_right, btn_bottom], radius=19, fill=BUTTON_GREEN)
    
    btn_text = "Maç Sayfasını Aç"
    btn_font = get_font(12, bold=True)
    btn_text_width = draw.textlength(btn_text, font=btn_font)
    btn_text_x = (CARD_WIDTH - btn_text_width) / 2
    draw.text((btn_text_x, btn_top + 11), btn_text, fill=TEXT_WHITE, font=btn_font)
    
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
    kickoff_utc: str = None,
    **kwargs
) -> BytesIO:
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
            kickoff_utc=kickoff_utc,
            previous_alarms=kwargs.get('previous_alarms'),
            multiplier=kwargs.get('multiplier')
        )
    
    card_height = 160
    
    img = Image.new('RGB', (CARD_WIDTH, card_height), BG_COLOR)
    draw = ImageDraw.Draw(img)
    
    draw.rounded_rectangle([10, 10, CARD_WIDTH - 10, card_height - 10], radius=12, fill=CARD_BG)
    
    font_small = get_font(11)
    font_normal = get_font(13)
    font_semibold = get_font(16, bold=True)
    font_large = get_font(20, bold=True)
    
    alarm_color = ALARM_COLORS.get(alarm_type, (59, 130, 246))
    alarm_label = ALARM_LABELS.get(alarm_type, alarm_type.upper())
    
    y = 25
    dot_x = CARD_PADDING + 10
    draw.ellipse([dot_x, y + 3, dot_x + 8, y + 11], fill=alarm_color)
    draw.text((dot_x + 14, y - 2), alarm_label, fill=alarm_color, font=font_semibold)
    
    if alarm_time:
        time_str = format_tr_time(alarm_time)
        time_width = draw.textlength(time_str, font=font_small)
        draw.text((CARD_WIDTH - CARD_PADDING - 10 - time_width, y + 1), time_str, fill=TEXT_SECONDARY, font=font_small)
    
    y += 35
    match_text = f"{home_team} – {away_team}"
    draw.text((CARD_PADDING + 10, y), match_text, fill=TEXT_WHITE, font=font_semibold)
    
    extra_info = kwargs.get('extra_info', '')
    if extra_info:
        info_width = draw.textlength(extra_info, font=font_large)
        draw.text((CARD_WIDTH - CARD_PADDING - 10 - info_width, y - 2), extra_info, fill=alarm_color, font=font_large)
    
    y += 28
    market_text = f"{market} · {selection}"
    draw.text((CARD_PADDING + 10, y), market_text, fill=TEXT_SECONDARY, font=font_normal)
    
    if alarm_type == 'dropping':
        odds_info = kwargs.get('odds_info', '')
        if odds_info:
            y += 25
            draw.text((CARD_PADDING + 10, y), odds_info, fill=alarm_color, font=font_normal)
    
    buffer = BytesIO()
    img.save(buffer, format='PNG', quality=95)
    buffer.seek(0)
    
    return buffer


if __name__ == "__main__":
    img_buffer = generate_bigmoney_card(
        home_team="Alaves",
        away_team="Real Madrid",
        market="1X2",
        selection="2",
        current_money=42646,
        total_money=485780,
        alarm_time="2025-12-13T14:05:00Z",
        kickoff_utc="2025-12-14T20:00:00Z",
        previous_alarms=[
            {"time": "2025-12-14T21:59:00Z", "money": 37170},
            {"time": "2025-12-14T21:49:00Z", "money": 106308},
            {"time": "2025-12-14T21:40:00Z", "money": 20612},
            {"time": "2025-12-13T14:05:00Z", "money": 31553},
        ],
        multiplier=5
    )
    
    with open("/tmp/test_bigmoney_card.png", "wb") as f:
        f.write(img_buffer.getvalue())
    
    print("Test image saved to /tmp/test_bigmoney_card.png")
