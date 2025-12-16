"""
Alarm Card Image Generator for Telegram Notifications
Generates visual alarm cards matching the web UI design exactly
Uses Inter font for perfect match
"""

from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from datetime import datetime
import pytz
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(SCRIPT_DIR, 'fonts')

CARD_WIDTH = 380
CARD_PADDING = 20

BG_COLOR = (13, 17, 23)
CARD_BG = (22, 27, 34)
DIVIDER_COLOR = (48, 54, 61)
TEXT_WHITE = (255, 255, 255)
TEXT_SECONDARY = (139, 148, 158)
TEXT_MUTED = (110, 118, 129)
ORANGE = (249, 115, 22)
GREEN = (34, 197, 94)
GREEN_BOX_TOP = (15, 35, 24)
GREEN_BOX_BOTTOM = (10, 26, 18)
GREEN_BORDER = (30, 74, 42)
BUTTON_GREEN = (34, 163, 74)

MONTHS_TR = ['Oca', 'Şub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Ağu', 'Eyl', 'Eki', 'Kas', 'Ara']


def get_font(size, weight='regular'):
    weight_map = {
        'regular': 'Inter-Regular.ttf',
        'medium': 'Inter-Medium.ttf',
        'semibold': 'Inter-SemiBold.ttf',
        'bold': 'Inter-Bold.ttf',
    }
    
    font_file = weight_map.get(weight, 'Inter-Regular.ttf')
    font_path = os.path.join(FONTS_DIR, font_file)
    
    fallback_paths = [
        font_path,
        os.path.join(os.path.dirname(__file__), 'fonts', font_file),
        f"/tmp/inter/extras/ttf/{font_file}",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    
    for path in fallback_paths:
        try:
            return ImageFont.truetype(path, size)
        except:
            continue
    
    return ImageFont.load_default()


def format_money(amount):
    if amount is None:
        return "£0"
    formatted = f"{amount:,.0f}".replace(",", ".")
    return f"£{formatted}"


def format_tr_datetime(utc_time_str):
    try:
        if isinstance(utc_time_str, str):
            utc_time_str = utc_time_str.replace('Z', '+00:00')
            if '+' not in utc_time_str and '-' not in utc_time_str[10:]:
                utc_time_str = utc_time_str + '+00:00'
            dt = datetime.fromisoformat(utc_time_str)
        else:
            dt = utc_time_str
        tr_tz = pytz.timezone('Europe/Istanbul')
        tr_time = dt.astimezone(tr_tz)
        return tr_time.strftime("%d.%m %H:%M")
    except:
        return ""


def format_kickoff(kickoff_utc):
    try:
        if isinstance(kickoff_utc, str):
            kickoff_utc = kickoff_utc.replace('Z', '+00:00')
            if '+' not in kickoff_utc and '-' not in kickoff_utc[10:]:
                kickoff_utc = kickoff_utc + '+00:00'
            dt = datetime.fromisoformat(kickoff_utc)
        else:
            dt = kickoff_utc
        tr_tz = pytz.timezone('Europe/Istanbul')
        tr_time = dt.astimezone(tr_tz)
        day = tr_time.day
        month = MONTHS_TR[tr_time.month - 1]
        time_str = tr_time.strftime("%H:%M")
        return f"{day} {month} • {time_str}"
    except:
        return ""


def draw_rounded_rect(draw, xy, radius, fill):
    x1, y1, x2, y2 = xy
    draw.rectangle([x1 + radius, y1, x2 - radius, y2], fill=fill)
    draw.rectangle([x1, y1 + radius, x2, y2 - radius], fill=fill)
    draw.ellipse([x1, y1, x1 + radius * 2, y1 + radius * 2], fill=fill)
    draw.ellipse([x2 - radius * 2, y1, x2, y1 + radius * 2], fill=fill)
    draw.ellipse([x1, y2 - radius * 2, x1 + radius * 2, y2], fill=fill)
    draw.ellipse([x2 - radius * 2, y2 - radius * 2, x2, y2], fill=fill)


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
    prev_section_height = (prev_count * 30) + 35 if prev_count > 0 else 0
    
    card_height = (
        16 +
        35 +
        35 +
        20 +
        1 +
        30 +
        90 +
        (35 if total_money else 0) +
        prev_section_height +
        (25 if multiplier else 0) +
        50 +
        16
    )
    
    img = Image.new('RGB', (CARD_WIDTH, card_height), BG_COLOR)
    draw = ImageDraw.Draw(img)
    
    draw_rounded_rect(draw, (0, 0, CARD_WIDTH, card_height), 12, CARD_BG)
    
    font_tiny = get_font(11, 'regular')
    font_small = get_font(12, 'regular')
    font_normal = get_font(13, 'regular')
    font_medium = get_font(14, 'medium')
    font_semibold = get_font(16, 'semibold')
    font_large = get_font(22, 'bold')
    font_xlarge = get_font(36, 'bold')
    
    y = 16
    
    dot_x = CARD_PADDING
    draw.ellipse([dot_x, y + 4, dot_x + 8, y + 12], fill=ORANGE)
    
    label_x = dot_x + 14
    draw.text((label_x, y), "BIG MONEY", fill=ORANGE, font=font_semibold)
    
    if alarm_time:
        time_str = format_tr_datetime(alarm_time)
        time_width = draw.textlength(time_str, font=font_small)
        draw.text((CARD_WIDTH - CARD_PADDING - time_width, y + 2), time_str, fill=TEXT_SECONDARY, font=font_small)
    
    y += 32
    
    match_text = f"{home_team} – {away_team}"
    draw.text((CARD_PADDING, y), match_text, fill=TEXT_WHITE, font=font_semibold)
    
    money_text = format_money(current_money)
    money_width = draw.textlength(money_text, font=font_large)
    draw.text((CARD_WIDTH - CARD_PADDING - money_width, y - 2), money_text, fill=ORANGE, font=font_large)
    
    y += 28
    market_text = f"{market} · {selection}"
    draw.text((CARD_PADDING, y), market_text, fill=TEXT_SECONDARY, font=font_normal)
    
    y += 25
    draw.line([(CARD_PADDING, y), (CARD_WIDTH - CARD_PADDING, y)], fill=DIVIDER_COLOR, width=1)
    
    y += 15
    if kickoff_utc:
        kickoff_str = format_kickoff(kickoff_utc)
        draw.text((CARD_PADDING, y), kickoff_str, fill=TEXT_SECONDARY, font=font_normal)
    
    y += 25
    
    box_margin = 15
    box_height = 75
    box_left = box_margin
    box_right = CARD_WIDTH - box_margin
    box_top = y
    box_bottom = y + box_height
    
    for i in range(box_height):
        ratio = i / box_height
        r = int(GREEN_BOX_TOP[0] * (1 - ratio) + GREEN_BOX_BOTTOM[0] * ratio)
        g = int(GREEN_BOX_TOP[1] * (1 - ratio) + GREEN_BOX_BOTTOM[1] * ratio)
        b = int(GREEN_BOX_TOP[2] * (1 - ratio) + GREEN_BOX_BOTTOM[2] * ratio)
        draw.line([(box_left + 10, box_top + i), (box_right - 10, box_top + i)], fill=(r, g, b))
    
    draw_rounded_rect(draw, (box_left, box_top, box_right, box_bottom), 10, None)
    
    for i in range(box_height):
        ratio = i / box_height
        r = int(GREEN_BOX_TOP[0] * (1 - ratio) + GREEN_BOX_BOTTOM[0] * ratio)
        g = int(GREEN_BOX_TOP[1] * (1 - ratio) + GREEN_BOX_BOTTOM[1] * ratio)
        b = int(GREEN_BOX_TOP[2] * (1 - ratio) + GREEN_BOX_BOTTOM[2] * ratio)
        
        for j in range(10):
            left_x = box_left + j
            right_x = box_right - 10 + j
            if box_top + i >= box_top and box_top + i <= box_bottom:
                draw.point((left_x, box_top + i), fill=(r, g, b))
                draw.point((right_x, box_top + i), fill=(r, g, b))
    
    draw_rounded_rect(draw, (box_left, box_top, box_right, box_bottom), 10, None)
    
    for i in range(box_height):
        ratio = i / box_height
        r = int(GREEN_BOX_TOP[0] * (1 - ratio) + GREEN_BOX_BOTTOM[0] * ratio)
        g = int(GREEN_BOX_TOP[1] * (1 - ratio) + GREEN_BOX_BOTTOM[1] * ratio)
        b = int(GREEN_BOX_TOP[2] * (1 - ratio) + GREEN_BOX_BOTTOM[2] * ratio)
        draw.line([(box_left, box_top + i), (box_right, box_top + i)], fill=(r, g, b))
    
    draw.rounded_rectangle([box_left, box_top, box_right, box_bottom], radius=10, outline=GREEN_BORDER, width=1)
    
    display_money = total_money if total_money else current_money
    money_big = format_money(display_money)
    money_big_width = draw.textlength(money_big, font=font_xlarge)
    money_big_x = (CARD_WIDTH - money_big_width) / 2
    draw.text((money_big_x, box_top + 12), money_big, fill=ORANGE, font=font_xlarge)
    
    label_text = "BÜYÜK PARA GİRİŞİ"
    label_width = draw.textlength(label_text, font=font_tiny)
    label_x = (CARD_WIDTH - label_width) / 2
    draw.text((label_x, box_top + 52), label_text, fill=ORANGE, font=font_tiny)
    
    y = box_bottom + 15
    
    if total_money and total_money != current_money:
        total_str = format_money(total_money)
        total_width = draw.textlength(total_str, font=font_medium)
        toplam_text = "TOPLAM"
        toplam_width = draw.textlength(toplam_text, font=font_small)
        combined_width = total_width + 8 + toplam_width
        start_x = (CARD_WIDTH - combined_width) / 2
        
        draw.text((start_x, y), total_str, fill=TEXT_SECONDARY, font=font_medium)
        draw.text((start_x + total_width + 8, y + 1), toplam_text, fill=GREEN, font=font_small)
        
        y += 30
    
    if previous_alarms and len(previous_alarms) > 0:
        y += 5
        draw.text((CARD_PADDING, y), "ÖNCEKİ", fill=TEXT_MUTED, font=font_tiny)
        y += 20
        
        for prev in previous_alarms[:5]:
            prev_time = format_tr_datetime(prev.get('time', ''))
            prev_money = format_money(prev.get('money', 0))
            
            draw.ellipse([CARD_PADDING, y + 5, CARD_PADDING + 6, y + 11], fill=ORANGE)
            
            draw.text((CARD_PADDING + 14, y), prev_time, fill=TEXT_SECONDARY, font=font_normal)
            
            money_w = draw.textlength(prev_money, font=font_normal)
            draw.text((CARD_WIDTH - CARD_PADDING - money_w, y), prev_money, fill=ORANGE, font=font_normal)
            
            y += 30
    
    if multiplier and multiplier > 1:
        y += 5
        mult_text = f"×{multiplier}"
        draw.text((CARD_PADDING, y), mult_text, fill=TEXT_MUTED, font=font_small)
        y += 20
    
    y += 5
    btn_height = 38
    btn_margin = 15
    btn_left = btn_margin
    btn_right = CARD_WIDTH - btn_margin
    btn_top = y
    btn_bottom = y + btn_height
    
    draw.rounded_rectangle([btn_left, btn_top, btn_right, btn_bottom], radius=19, fill=BUTTON_GREEN)
    
    btn_text = "Maç Sayfasını Aç"
    btn_font = get_font(13, 'semibold')
    btn_text_width = draw.textlength(btn_text, font=btn_font)
    btn_text_x = (CARD_WIDTH - btn_text_width) / 2
    draw.text((btn_text_x, btn_top + 10), btn_text, fill=TEXT_WHITE, font=btn_font)
    
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
    
    return generate_bigmoney_card(
        home_team=home_team,
        away_team=away_team,
        market=market,
        selection=selection,
        current_money=kwargs.get('money', 0),
        alarm_time=alarm_time,
        kickoff_utc=kickoff_utc
    )


if __name__ == "__main__":
    img_buffer = generate_bigmoney_card(
        home_team="Arsenal",
        away_team="Wolves",
        market="1X2",
        selection="1",
        current_money=21462,
        total_money=302078,
        alarm_time="2025-12-09T01:06:00Z",
        kickoff_utc="2025-12-13T20:00:00Z",
        previous_alarms=[
            {"time": "2025-12-11T19:29:00Z", "money": 25025},
            {"time": "2025-12-11T11:37:00Z", "money": 25569},
            {"time": "2025-12-09T01:06:00Z", "money": 27176},
            {"time": "2025-12-09T00:29:00Z", "money": 43366},
        ],
        multiplier=5
    )
    
    with open("/tmp/test_bigmoney_card.png", "wb") as f:
        f.write(img_buffer.getvalue())
    
    print("Test image saved to /tmp/test_bigmoney_card.png")
