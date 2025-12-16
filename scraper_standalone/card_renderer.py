"""
HTML-based Alarm Card Renderer
Renders alarm cards as HTML and captures screenshots for Telegram notifications
Uses the exact same styling as the web UI
"""

import os
import asyncio
from io import BytesIO
from datetime import datetime
from typing import Optional, List, Dict
import pytz

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

MONTHS_TR = ['Oca', 'Şub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Ağu', 'Eyl', 'Eki', 'Kas', 'Ara']


def format_money(amount):
    if amount is None:
        return "£0"
    return f"£{amount:,.0f}".replace(",", ".")


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
        day = tr_time.day
        month = MONTHS_TR[tr_time.month - 1]
        time_str = tr_time.strftime("%H:%M")
        return f"{day:02d}.{tr_time.month:02d} {time_str}"
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


def generate_bigmoney_html(
    home_team: str,
    away_team: str,
    market: str,
    selection: str,
    current_money: float,
    total_money: float = None,
    alarm_time: str = None,
    kickoff_utc: str = None,
    previous_alarms: List[Dict] = None,
    multiplier: int = None
) -> str:
    alarm_time_str = format_tr_datetime(alarm_time) if alarm_time else ""
    kickoff_str = format_kickoff(kickoff_utc) if kickoff_utc else ""
    display_money = total_money if total_money else current_money
    
    prev_html = ""
    if previous_alarms and len(previous_alarms) > 0:
        prev_items = ""
        for prev in previous_alarms[:5]:
            prev_time = format_tr_datetime(prev.get('time', ''))
            prev_money = format_money(prev.get('money', 0))
            prev_items += f'''
            <div class="prev-item">
                <div class="prev-left">
                    <span class="prev-dot"></span>
                    <span class="prev-time">{prev_time}</span>
                </div>
                <span class="prev-money">{prev_money}</span>
            </div>
            '''
        prev_html = f'''
        <div class="prev-section">
            <div class="prev-title">ÖNCEKİ</div>
            {prev_items}
        </div>
        '''
    
    multiplier_html = ""
    if multiplier and multiplier > 1:
        multiplier_html = f'<div class="multiplier">×{multiplier}</div>'
    
    total_html = ""
    if total_money and total_money != current_money:
        total_html = f'''
        <div class="total-section">
            <span class="total-amount">{format_money(total_money)}</span>
            <span class="total-label">TOPLAM</span>
        </div>
        '''
    
    html = f'''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #0d1117;
            padding: 0;
            margin: 0;
        }}
        .card {{
            background: #161b22;
            border-radius: 12px;
            padding: 16px 20px;
            width: 380px;
            color: #fff;
        }}
        .header {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 12px;
        }}
        .status-dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #f97316;
        }}
        .alarm-type {{
            font-size: 14px;
            font-weight: 600;
            color: #f97316;
            letter-spacing: 0.5px;
        }}
        .alarm-time {{
            font-size: 12px;
            color: #8b949e;
            margin-left: auto;
        }}
        .match-row {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 6px;
        }}
        .match-teams {{
            font-size: 16px;
            font-weight: 600;
            color: #fff;
        }}
        .match-money {{
            font-size: 22px;
            font-weight: 700;
            color: #f97316;
        }}
        .market-info {{
            font-size: 13px;
            color: #8b949e;
            margin-bottom: 12px;
        }}
        .divider {{
            height: 1px;
            background: #30363d;
            margin: 12px 0;
        }}
        .kickoff {{
            font-size: 13px;
            color: #8b949e;
            margin-bottom: 16px;
        }}
        .money-box {{
            background: linear-gradient(180deg, #0f2318 0%, #0a1a12 100%);
            border: 1px solid #1e4a2a;
            border-radius: 10px;
            padding: 16px;
            text-align: center;
            margin-bottom: 16px;
        }}
        .money-big {{
            font-size: 36px;
            font-weight: 700;
            color: #f97316;
            margin-bottom: 4px;
        }}
        .money-label {{
            font-size: 11px;
            color: #f97316;
            letter-spacing: 1px;
            opacity: 0.9;
        }}
        .total-section {{
            text-align: center;
            margin-bottom: 16px;
        }}
        .total-amount {{
            font-size: 15px;
            color: #8b949e;
            font-weight: 500;
        }}
        .total-label {{
            font-size: 12px;
            color: #22c55e;
            font-weight: 600;
            margin-left: 6px;
            letter-spacing: 0.5px;
        }}
        .prev-section {{
            margin-bottom: 12px;
        }}
        .prev-title {{
            font-size: 11px;
            color: #6e7681;
            letter-spacing: 1px;
            margin-bottom: 10px;
        }}
        .prev-item {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 6px 0;
        }}
        .prev-left {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .prev-dot {{
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: #f97316;
        }}
        .prev-time {{
            font-size: 13px;
            color: #8b949e;
        }}
        .prev-money {{
            font-size: 13px;
            color: #f97316;
            font-weight: 500;
        }}
        .multiplier {{
            font-size: 12px;
            color: #6e7681;
            margin-bottom: 12px;
        }}
        .button {{
            background: linear-gradient(180deg, #22c55e 0%, #16a34a 100%);
            border-radius: 999px;
            padding: 12px 24px;
            text-align: center;
            font-size: 13px;
            font-weight: 600;
            color: #fff;
            cursor: pointer;
        }}
    </style>
</head>
<body>
    <div class="card">
        <div class="header">
            <span class="status-dot"></span>
            <span class="alarm-type">BIG MONEY</span>
            <span class="alarm-time">{alarm_time_str}</span>
        </div>
        
        <div class="match-row">
            <span class="match-teams">{home_team} – {away_team}</span>
            <span class="match-money">{format_money(current_money)}</span>
        </div>
        
        <div class="market-info">{market} · {selection}</div>
        
        <div class="divider"></div>
        
        <div class="kickoff">{kickoff_str}</div>
        
        <div class="money-box">
            <div class="money-big">{format_money(display_money)}</div>
            <div class="money-label">BÜYÜK PARA GİRİŞİ</div>
        </div>
        
        {total_html}
        
        {prev_html}
        
        {multiplier_html}
        
        <div class="button">Maç Sayfasını Aç</div>
    </div>
</body>
</html>
'''
    return html


async def render_html_to_image(html: str) -> BytesIO:
    if not PLAYWRIGHT_AVAILABLE:
        raise RuntimeError("Playwright not available")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width': 420, 'height': 800})
        
        await page.set_content(html)
        await page.wait_for_load_state('networkidle')
        await asyncio.sleep(0.3)
        
        card = await page.query_selector('.card')
        if card:
            screenshot = await card.screenshot(type='png')
        else:
            screenshot = await page.screenshot(type='png')
        
        await browser.close()
        
        buffer = BytesIO(screenshot)
        buffer.seek(0)
        return buffer


def render_bigmoney_card(
    home_team: str,
    away_team: str,
    market: str,
    selection: str,
    current_money: float,
    total_money: float = None,
    alarm_time: str = None,
    kickoff_utc: str = None,
    previous_alarms: List[Dict] = None,
    multiplier: int = None
) -> BytesIO:
    html = generate_bigmoney_html(
        home_team=home_team,
        away_team=away_team,
        market=market,
        selection=selection,
        current_money=current_money,
        total_money=total_money,
        alarm_time=alarm_time,
        kickoff_utc=kickoff_utc,
        previous_alarms=previous_alarms,
        multiplier=multiplier
    )
    
    return asyncio.get_event_loop().run_until_complete(render_html_to_image(html))


def render_alarm_card(
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
        return render_bigmoney_card(
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
    
    return render_bigmoney_card(
        home_team=home_team,
        away_team=away_team,
        market=market,
        selection=selection,
        current_money=kwargs.get('money', 0),
        alarm_time=alarm_time,
        kickoff_utc=kickoff_utc
    )


if __name__ == "__main__":
    print("Testing BigMoney card render...")
    
    buffer = render_bigmoney_card(
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
    
    with open("/tmp/test_bigmoney_html.png", "wb") as f:
        f.write(buffer.getvalue())
    
    print("Test image saved to /tmp/test_bigmoney_html.png")
