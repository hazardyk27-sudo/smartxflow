"""
Telegram Card Renderer - HTML to PNG
Renders alarm cards exactly like the web UI using Playwright
For use in Admin.exe (Windows environment where Playwright works)
"""

import asyncio
import logging
from io import BytesIO
from datetime import datetime
from typing import Optional, List, Dict
import os

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

try:
    import pytz
    TURKEY_TZ = pytz.timezone('Europe/Istanbul')
except ImportError:
    TURKEY_TZ = None

logger = logging.getLogger(__name__)

MONTHS_TR = ['Oca', 'Şub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Ağu', 'Eyl', 'Eki', 'Kas', 'Ara']

_browser_instance = None
_playwright_instance = None
_browser_lock = asyncio.Lock()
_chromium_available = None


def check_chromium_available() -> bool:
    """
    Check if Chromium binary is available for Playwright.
    Returns cached result after first check.
    Uses simple file existence check to avoid spawning processes.
    """
    global _chromium_available
    if _chromium_available is not None:
        return _chromium_available
    
    if not PLAYWRIGHT_AVAILABLE:
        _chromium_available = False
        return False
    
    try:
        import os
        import sys
        
        if sys.platform == 'win32':
            local_browsers = os.path.expanduser('~/.cache/ms-playwright')
            if not os.path.exists(local_browsers):
                local_browsers = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'ms-playwright')
            
            if os.path.exists(local_browsers):
                for item in os.listdir(local_browsers):
                    if item.startswith('chromium'):
                        _chromium_available = True
                        logger.info("[CardRenderer] Chromium binary found")
                        return True
        else:
            cache_paths = [
                os.path.expanduser('~/.cache/ms-playwright'),
                '/tmp/playwright-browsers'
            ]
            for cache_path in cache_paths:
                if os.path.exists(cache_path):
                    for item in os.listdir(cache_path):
                        if item.startswith('chromium'):
                            _chromium_available = True
                            logger.info("[CardRenderer] Chromium binary found")
                            return True
        
        _chromium_available = None
        logger.info("[CardRenderer] Chromium check inconclusive, will verify on first use")
        return True
        
    except Exception as e:
        logger.warning(f"[CardRenderer] Chromium check failed: {e}")
        _chromium_available = None
        return True


def mark_chromium_unavailable():
    """Mark Chromium as unavailable after a runtime failure."""
    global _chromium_available
    _chromium_available = False
    logger.warning("[CardRenderer] Chromium marked as unavailable for this session")


def format_money(amount):
    if amount is None:
        return "£0"
    formatted = f"{int(amount):,}".replace(",", ".")
    return f"£{formatted}"


def format_datetime_tr(utc_time_str):
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
        return tr_time.strftime("%d.%m %H:%M")
    except:
        return ""


def format_kickoff_tr(kickoff_utc):
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


def generate_bigmoney_html(
    home_team: str,
    away_team: str,
    market: str,
    selection: str,
    delta_money: float,
    total_money: float = None,
    alarm_time: str = None,
    kickoff_utc: str = None,
    previous_entries: List[Dict] = None,
    match_url: str = None,
    multiplier: int = None
) -> str:
    alarm_time_str = format_datetime_tr(alarm_time) if alarm_time else ""
    kickoff_str = format_kickoff_tr(kickoff_utc) if kickoff_utc else ""
    display_money = total_money if total_money else delta_money
    
    prev_html = ""
    if previous_entries and len(previous_entries) > 0:
        # Mevcut alarmı filtrele - aynı para değeri veya aynı zaman olan kayıtları atla
        filtered_prev = []
        for prev in previous_entries:
            prev_money_val = prev.get('money', 0) or prev.get('delta_money', 0) or prev.get('incoming_money', 0)
            prev_time_val = prev.get('time', '') or prev.get('created_at', '') or prev.get('trigger_at', '')
            
            # Mevcut alarmla aynı para değeri VE aynı zaman ise atla
            if prev_money_val == delta_money and prev_time_val == alarm_time:
                continue
            # Sadece aynı para değeri ise ve çok yakın zamanda ise atla (5 dakika içinde)
            if prev_money_val == delta_money:
                try:
                    from datetime import datetime
                    if prev_time_val and alarm_time:
                        prev_dt = datetime.fromisoformat(prev_time_val.replace('Z', '+00:00'))
                        alarm_dt = datetime.fromisoformat(alarm_time.replace('Z', '+00:00'))
                        diff_minutes = abs((alarm_dt - prev_dt).total_seconds() / 60)
                        if diff_minutes < 5:
                            continue
                except:
                    pass
            filtered_prev.append(prev)
        
        # Filtreleme sonrası gerçekten önceki kayıt varsa göster
        if filtered_prev:
            prev_items = ""
            for prev in filtered_prev[:4]:
                prev_time = format_datetime_tr(prev.get('time', '') or prev.get('created_at', '') or prev.get('trigger_at', ''))
                prev_money = format_money(prev.get('money', 0) or prev.get('delta_money', 0) or prev.get('incoming_money', 0))
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
    if total_money:
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
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0d1117;
            padding: 8px;
            margin: 0;
        }}
        .card {{
            background: #161b22;
            border-radius: 12px;
            padding: 16px 18px;
            width: 360px;
            color: #fff;
            border-left: 3px solid #f97316;
        }}
        .header {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 14px;
        }}
        .status-dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #f97316;
            flex-shrink: 0;
        }}
        .alarm-type {{
            font-size: 13px;
            font-weight: 600;
            color: #f97316;
            letter-spacing: 0.3px;
        }}
        .alarm-time {{
            font-size: 11px;
            color: #8b949e;
            margin-left: auto;
        }}
        .match-row {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 4px;
        }}
        .match-teams {{
            font-size: 15px;
            font-weight: 600;
            color: #fff;
            line-height: 1.3;
        }}
        .match-money {{
            font-size: 20px;
            font-weight: 700;
            color: #f97316;
            white-space: nowrap;
            margin-left: 12px;
        }}
        .market-info {{
            font-size: 12px;
            color: #8b949e;
            margin-bottom: 12px;
        }}
        .divider {{
            height: 1px;
            background: #30363d;
            margin: 12px 0;
        }}
        .kickoff {{
            font-size: 12px;
            color: #8b949e;
            margin-bottom: 14px;
        }}
        .money-box {{
            background: linear-gradient(180deg, #0f2318 0%, #0a1a12 100%);
            border: 1px solid #1e4a2a;
            border-radius: 10px;
            padding: 14px 16px;
            text-align: center;
            margin-bottom: 14px;
        }}
        .money-big {{
            font-size: 32px;
            font-weight: 700;
            color: #f97316;
            margin-bottom: 2px;
            line-height: 1.1;
        }}
        .money-label {{
            font-size: 10px;
            color: #f97316;
            letter-spacing: 1.2px;
            opacity: 0.85;
        }}
        .total-section {{
            text-align: center;
            margin-bottom: 14px;
        }}
        .total-amount {{
            font-size: 14px;
            color: #8b949e;
            font-weight: 500;
        }}
        .total-label {{
            font-size: 11px;
            color: #22c55e;
            font-weight: 600;
            margin-left: 6px;
            letter-spacing: 0.5px;
        }}
        .prev-section {{
            margin-bottom: 10px;
        }}
        .prev-title {{
            font-size: 10px;
            color: #6e7681;
            letter-spacing: 1px;
            margin-bottom: 8px;
        }}
        .prev-item {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 5px 0;
        }}
        .prev-left {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .prev-dot {{
            width: 5px;
            height: 5px;
            border-radius: 50%;
            background: #f97316;
            flex-shrink: 0;
        }}
        .prev-time {{
            font-size: 12px;
            color: #8b949e;
        }}
        .prev-money {{
            font-size: 12px;
            color: #f97316;
            font-weight: 500;
        }}
        .multiplier {{
            font-size: 11px;
            color: #6e7681;
            margin-bottom: 10px;
        }}
        .button {{
            background: linear-gradient(180deg, #22c55e 0%, #16a34a 100%);
            border-radius: 999px;
            padding: 11px 20px;
            text-align: center;
            font-size: 12px;
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
            <span class="match-money">{format_money(delta_money)}</span>
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


async def get_browser():
    global _browser_instance, _playwright_instance
    async with _browser_lock:
        if _browser_instance is None or not _browser_instance.is_connected():
            if not PLAYWRIGHT_AVAILABLE:
                raise RuntimeError("Playwright not available")
            
            if _playwright_instance is None:
                _playwright_instance = await async_playwright().start()
            
            try:
                _browser_instance = await _playwright_instance.chromium.launch(headless=True)
                logger.info("[CardRenderer] Browser instance created")
            except Exception as e:
                logger.error(f"[CardRenderer] Failed to launch browser: {e}")
                raise RuntimeError(f"Chromium not available: {e}")
        
        return _browser_instance


async def close_browser():
    global _browser_instance, _playwright_instance
    async with _browser_lock:
        if _browser_instance and _browser_instance.is_connected():
            await _browser_instance.close()
            _browser_instance = None
            logger.info("[CardRenderer] Browser instance closed")
        
        if _playwright_instance:
            await _playwright_instance.stop()
            _playwright_instance = None
            logger.info("[CardRenderer] Playwright instance stopped")


async def render_html_to_png_async(html: str) -> bytes:
    if not PLAYWRIGHT_AVAILABLE:
        raise RuntimeError("Playwright not available - install with: pip install playwright && playwright install chromium")
    
    browser = await get_browser()
    page = await browser.new_page(viewport={'width': 400, 'height': 800})
    
    try:
        await page.set_content(html)
        await page.wait_for_load_state('networkidle')
        await asyncio.sleep(0.5)
        
        card = await page.query_selector('.card')
        if card:
            screenshot = await card.screenshot(type='png')
        else:
            screenshot = await page.screenshot(type='png')
        
        return screenshot
    finally:
        await page.close()


def render_html_to_png(html: str) -> bytes:
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(render_html_to_png_async(html))


def render_bigmoney_card_png(
    home_team: str,
    away_team: str,
    market: str,
    selection: str,
    delta_money: float,
    total_money: float = None,
    alarm_time: str = None,
    kickoff_utc: str = None,
    previous_entries: List[Dict] = None,
    match_url: str = None,
    multiplier: int = None
) -> bytes:
    html = generate_bigmoney_html(
        home_team=home_team,
        away_team=away_team,
        market=market,
        selection=selection,
        delta_money=delta_money,
        total_money=total_money,
        alarm_time=alarm_time,
        kickoff_utc=kickoff_utc,
        previous_entries=previous_entries,
        match_url=match_url,
        multiplier=multiplier
    )
    
    return render_html_to_png(html)


def render_alarm_card_png(
    alarm_type: str,
    home_team: str,
    away_team: str,
    market: str,
    selection: str,
    alarm_time: str = None,
    kickoff_utc: str = None,
    **kwargs
) -> bytes:
    alarm_type = alarm_type.lower()
    
    if alarm_type == 'bigmoney':
        return render_bigmoney_card_png(
            home_team=home_team,
            away_team=away_team,
            market=market,
            selection=selection,
            delta_money=kwargs.get('delta_money', 0) or kwargs.get('money', 0),
            total_money=kwargs.get('total_money'),
            alarm_time=alarm_time,
            kickoff_utc=kickoff_utc,
            previous_entries=kwargs.get('previous_entries') or kwargs.get('previous_alarms'),
            match_url=kwargs.get('match_url'),
            multiplier=kwargs.get('multiplier')
        )
    
    return render_bigmoney_card_png(
        home_team=home_team,
        away_team=away_team,
        market=market,
        selection=selection,
        delta_money=kwargs.get('delta_money', 0) or kwargs.get('money', 0),
        alarm_time=alarm_time,
        kickoff_utc=kickoff_utc
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Testing BigMoney card render...")
    
    try:
        png_bytes = render_bigmoney_card_png(
            home_team="Arsenal",
            away_team="Wolves",
            market="1X2",
            selection="1",
            delta_money=21462,
            total_money=302078,
            alarm_time="2025-12-09T01:06:00Z",
            kickoff_utc="2025-12-13T20:00:00Z",
            previous_entries=[
                {"time": "2025-12-11T19:29:00Z", "money": 25025},
                {"time": "2025-12-11T11:37:00Z", "money": 25569},
                {"time": "2025-12-09T01:06:00Z", "money": 27176},
                {"time": "2025-12-09T00:29:00Z", "money": 43366},
            ],
            multiplier=5
        )
        
        with open("/tmp/test_bigmoney_playwright.png", "wb") as f:
            f.write(png_bytes)
        
        print(f"Test image saved to /tmp/test_bigmoney_playwright.png ({len(png_bytes)} bytes)")
        
    except Exception as e:
        print(f"Error: {e}")
        print("Note: This module requires Playwright with Chromium installed.")
        print("Run: pip install playwright && playwright install chromium")
