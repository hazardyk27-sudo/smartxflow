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

CARD_WIDTH = 360
CARD_PADDING = 18
LEFT_BORDER_WIDTH = 4

BG_COLOR = (13, 17, 23)
CARD_BG = (38, 44, 52)
BORDER_COLOR = (48, 54, 61)
TEXT_WHITE = (230, 237, 243)
TEXT_SECONDARY = (139, 148, 158)
TEXT_MUTED = (110, 118, 129)
ORANGE = (240, 138, 36)
ORANGE_LIGHT = (249, 115, 22)
GREEN = (74, 222, 128)

HERO_BG_START = (38, 26, 18)
HERO_BG_END = (30, 22, 15)
HERO_BORDER = (60, 45, 30)

MONTHS_TR = ['Oca', 'Şub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Ağu', 'Eyl', 'Eki', 'Kas', 'Ara']


def get_font(size, weight='regular'):
    weight_map = {
        'regular': 'Inter-Regular.ttf',
        'medium': 'Inter-Medium.ttf',
        'semibold': 'Inter-SemiBold.ttf',
        'bold': 'Inter-Bold.ttf',
        'extrabold': 'Inter-ExtraBold.ttf',
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


def format_money_uk(amount):
    if amount is None:
        return "£0"
    formatted = f"{int(amount):,}".replace(",", ".")
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
        return tr_time.strftime("%d.%m • %H:%M")
    except:
        return ""


def format_prev_datetime(utc_time_str):
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
        return tr_time.strftime("%d.%m • %H:%M")
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


def draw_rounded_rect(draw, xy, radius, fill, outline=None, width=1):
    x1, y1, x2, y2 = xy
    if fill:
        draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=fill)
    if outline:
        draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, outline=outline, width=width)


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
    prev_count = min(len(previous_alarms) if previous_alarms else 0, 4)
    
    base_height = 14 + 30 + 12 + 22 + 8 + 20 + 12 + 80 + 12
    kickoff_section = 24 if kickoff_utc else 0
    total_section = 30 if total_money and total_money != current_money else 0
    prev_section = (prev_count * 26 + 24) if prev_count > 0 else 0
    multiplier_section = 24 if multiplier and multiplier > 1 else 0
    cta_section = 48
    
    card_height = base_height + kickoff_section + total_section + prev_section + multiplier_section + cta_section + 10
    
    img = Image.new('RGB', (CARD_WIDTH, card_height), BG_COLOR)
    draw = ImageDraw.Draw(img)
    
    draw_rounded_rect(draw, (0, 0, CARD_WIDTH, card_height), 16, CARD_BG)
    
    draw.rectangle([0, 8, LEFT_BORDER_WIDTH, card_height - 8], fill=ORANGE)
    
    font_badge = get_font(10, 'bold')
    font_time = get_font(12, 'regular')
    font_match = get_font(16, 'semibold')
    font_market = get_font(12, 'regular')
    font_hero = get_font(28, 'extrabold')
    font_hero_label = get_font(11, 'medium')
    font_total_val = get_font(14, 'semibold')
    font_total_lbl = get_font(11, 'medium')
    font_prev_title = get_font(10, 'medium')
    font_prev = get_font(12, 'regular')
    font_mult = get_font(11, 'bold')
    
    y = 14
    
    badge_text = "BIG MONEY"
    badge_width = draw.textlength(badge_text, font=font_badge) + 16
    badge_height = 20
    badge_x = CARD_PADDING + LEFT_BORDER_WIDTH
    
    badge_bg = (48, 35, 22)
    draw_rounded_rect(draw, (badge_x, y, badge_x + badge_width, y + badge_height), 6, badge_bg)
    draw.text((badge_x + 8, y + 4), badge_text, fill=ORANGE, font=font_badge)
    
    if alarm_time:
        time_str = format_tr_datetime(alarm_time)
        time_width = draw.textlength(time_str, font=font_time)
        draw.text((CARD_WIDTH - CARD_PADDING - time_width, y + 4), time_str, fill=TEXT_SECONDARY, font=font_time)
    
    dot_x = CARD_WIDTH - CARD_PADDING - 40
    draw.ellipse([dot_x, y + 6, dot_x + 8, y + 14], fill=ORANGE)
    
    y += 30
    
    y += 12
    match_text = f"{home_team} – {away_team}"
    draw.text((CARD_PADDING + LEFT_BORDER_WIDTH, y), match_text, fill=TEXT_WHITE, font=font_match)
    
    y += 22
    
    market_text = f"{market} · {selection}"
    draw.text((CARD_PADDING + LEFT_BORDER_WIDTH, y), market_text, fill=TEXT_SECONDARY, font=font_market)
    
    y += 16
    y += 8
    
    hero_margin = CARD_PADDING + LEFT_BORDER_WIDTH
    hero_width = CARD_WIDTH - hero_margin - CARD_PADDING
    hero_height = 70
    hero_top = y
    hero_bottom = y + hero_height
    hero_radius = 8
    
    hero_img = Image.new('RGBA', (hero_width, hero_height), (0, 0, 0, 0))
    hero_draw = ImageDraw.Draw(hero_img)
    
    for i in range(hero_height):
        ratio = i / hero_height
        r = int(HERO_BG_START[0] * (1 - ratio) + HERO_BG_END[0] * ratio)
        g = int(HERO_BG_START[1] * (1 - ratio) + HERO_BG_END[1] * ratio)
        b = int(HERO_BG_START[2] * (1 - ratio) + HERO_BG_END[2] * ratio)
        hero_draw.line([(0, i), (hero_width, i)], fill=(r, g, b, 255))
    
    mask = Image.new('L', (hero_width, hero_height), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([0, 0, hero_width, hero_height], radius=hero_radius, fill=255)
    
    hero_img.putalpha(mask)
    img.paste(hero_img, (hero_margin, hero_top), hero_img)
    
    draw.rounded_rectangle([hero_margin, hero_top, hero_margin + hero_width, hero_bottom], radius=hero_radius, outline=HERO_BORDER, width=1)
    
    display_money = total_money if total_money else current_money
    money_text = format_money_uk(display_money)
    money_width = draw.textlength(money_text, font=font_hero)
    money_x = hero_margin + (hero_width - money_width) / 2
    draw.text((money_x, hero_top + 14), money_text, fill=ORANGE, font=font_hero)
    
    label_text = "Büyük Para Girişi"
    label_width = draw.textlength(label_text, font=font_hero_label)
    label_x = hero_margin + (hero_width - label_width) / 2
    draw.text((label_x, hero_top + 48), label_text, fill=ORANGE, font=font_hero_label)
    
    y = hero_bottom + 12
    
    if total_money and total_money != current_money:
        total_str = format_money_uk(total_money)
        toplam_text = "Toplam"
        
        total_val_width = draw.textlength(total_str, font=font_total_val)
        toplam_width = draw.textlength(toplam_text, font=font_total_lbl)
        combined_width = total_val_width + 8 + toplam_width
        start_x = (CARD_WIDTH - combined_width) / 2
        
        draw.text((start_x, y), total_str, fill=TEXT_SECONDARY, font=font_total_val)
        draw.text((start_x + total_val_width + 8, y + 2), toplam_text, fill=GREEN, font=font_total_lbl)
        
        y += 28
    
    if previous_alarms and len(previous_alarms) > 0:
        y += 4
        draw.text((CARD_PADDING + LEFT_BORDER_WIDTH, y), "ÖNCEKİ", fill=TEXT_MUTED, font=font_prev_title)
        y += 18
        
        for prev in previous_alarms[:4]:
            prev_time = format_prev_datetime(prev.get('time', ''))
            prev_money = format_money_uk(prev.get('money', 0))
            
            draw.ellipse([CARD_PADDING + LEFT_BORDER_WIDTH, y + 4, CARD_PADDING + LEFT_BORDER_WIDTH + 6, y + 10], fill=ORANGE)
            
            draw.text((CARD_PADDING + LEFT_BORDER_WIDTH + 12, y), prev_time, fill=TEXT_SECONDARY, font=font_prev)
            
            money_w = draw.textlength(prev_money, font=font_prev)
            draw.text((CARD_WIDTH - CARD_PADDING - money_w, y), prev_money, fill=ORANGE, font=font_prev)
            
            y += 26
    
    if multiplier and multiplier > 1:
        mult_text = f"x{multiplier}"
        mult_width = draw.textlength(mult_text, font=font_mult) + 12
        mult_height = 20
        mult_x = CARD_WIDTH - CARD_PADDING - mult_width
        mult_y = 14
        
        mult_bg = (48, 35, 22)
        draw_rounded_rect(draw, (mult_x, mult_y, mult_x + mult_width, mult_y + mult_height), 10, mult_bg)
        draw.text((mult_x + 6, mult_y + 3), mult_text, fill=ORANGE, font=font_mult)
    
    if kickoff_utc:
        font_kickoff = get_font(12, 'regular')
        kickoff_str = format_kickoff(kickoff_utc)
        draw.text((CARD_PADDING + LEFT_BORDER_WIDTH, y), kickoff_str, fill=TEXT_SECONDARY, font=font_kickoff)
        y += 24
    
    y += 8
    btn_height = 36
    btn_margin = CARD_PADDING + LEFT_BORDER_WIDTH
    btn_left = btn_margin
    btn_right = CARD_WIDTH - CARD_PADDING
    btn_top = y
    btn_bottom = y + btn_height
    
    btn_bg = (30, 30, 32)
    draw_rounded_rect(draw, (btn_left, btn_top, btn_right, btn_bottom), 8, btn_bg, (48, 54, 61), 1)
    
    btn_text = "Maç Detayı"
    font_btn = get_font(12, 'semibold')
    btn_text_width = draw.textlength(btn_text, font=font_btn)
    btn_text_x = btn_left + (btn_right - btn_left - btn_text_width) / 2
    draw.text((btn_text_x, btn_top + 10), btn_text, fill=ORANGE, font=font_btn)
    
    arrow_x = btn_text_x + btn_text_width + 6
    draw.text((arrow_x, btn_top + 10), "→", fill=ORANGE, font=font_btn)
    
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
