#!/usr/bin/env python3
"""
excapper_scraper.py — Excapper.com Betfair MoneyWay scraper
Arbworld IP block'u sonrası Replit'ten erişilebilen alternatif kaynak.

Veri kaynağı: https://www.excapper.com (Betfair exchange)
Marketler: Match Odds (1X2), Over/Under 2.5 Goals (OU25), Both teams to Score? (BTTS)

Yöntem:
  1. Ana sayfa → prematch maç listesi (game_id, ekip, lig, tarih)
  2. Her maç için game detail sayfası → .charts-bk__item-coef parse
     Format: "8304€ - 2.34" (hacim€ - oran)
  3. graphsData JS → eski oranlar (dropping tespiti)
  4. Aynı Supabase tablo/alan formatını kullan (Arbworld ile uyumlu)
"""

import os
import re
import time
import random
import requests
import concurrent.futures
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any
from bs4 import BeautifulSoup

BASE_URL = "https://www.excapper.com"

def _get_headers() -> dict:
    """Cookie'yi her çağrıda env'den taze oku (import-time değil runtime)."""
    cookie = os.environ.get('excapper_cookie', '').strip()
    h = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/124.0.0.0 Safari/537.36'
        ),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Cache-Control': 'max-age=0',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Referer': 'https://www.excapper.com/',
    }
    if cookie:
        h['Cookie'] = cookie
    return h

def _get_detail_headers() -> dict:
    """Detail endpoint için cookie'yi runtime'da oku."""
    cookie = os.environ.get('excapper_cookie', '').strip()
    h = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/124.0.0.0 Safari/537.36'
        ),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Cache-Control': 'max-age=0',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'same-origin',
        'Referer': 'https://www.excapper.com/',
    }
    if cookie:
        h['Cookie'] = cookie
    return h

# Geriye dönük uyumluluk için sabit referanslar (eski kod kullanan yerler için)
HEADERS = _get_headers()
DETAIL_HEADERS = _get_detail_headers()
MAX_WORKERS = 2
FETCH_TIMEOUT = 25

# Tab link metni → internal market key
MARKET_TAB_MAP = {
    'Match Odds':            '1x2',
    'Over/Under 2.5 Goals': 'ou25',
    'Both teams to Score?': 'btts',
}

# ── Yardımcı parse fonksiyonları ──────────────────────────────────────────────

def _parse_coef_text(text: str) -> Tuple[float, float]:
    """
    '8304€ - 2.34' → (8304.0, 2.34)
    Hatalı format → (0.0, 0.0)
    """
    text = text.strip()
    m = re.match(r'([\d,\.]+)\s*€\s*[-–]\s*([\d,\.]+)', text)
    if not m:
        return 0.0, 0.0
    try:
        vol = float(m.group(1).replace(',', ''))
        odds = float(m.group(2).replace(',', '.'))
        return vol, (odds if odds > 1.0 else 0.0)
    except Exception:
        return 0.0, 0.0


def _to_vol_str(amount: float) -> str:
    """Float → '£ N' string (downstream _parse_volume ile uyumlu)."""
    if amount <= 0:
        return ""
    if amount == int(amount):
        return f"£ {int(amount)}"
    return f"£ {amount:g}"


def _to_pct_str(pct: float) -> str:
    """Float yüzde → '45.3%' string."""
    if pct <= 0:
        return ""
    return f"{pct:.1f}%"


def _to_odds_str(odds: float) -> str:
    """Float oran → string, geçersizse boş."""
    if not odds or odds <= 1.0:
        return ""
    return f"{odds:g}"


def _trend(cur: float, prev: float) -> str:
    """Oran hareketi: 'up'/'down'/''."""
    if cur <= 0 or prev <= 0 or abs(cur - prev) < 0.001:
        return ""
    return "up" if cur > prev else "down"


def _parse_excapper_date(date_str: str) -> str:
    """
    '14.06.2026 21:30' → '2026-06-14T21:30:00+00:00'
    Excapper Betfair UTC zamanını kullanır.
    """
    if not date_str:
        return ""
    try:
        dt = datetime.strptime(date_str.strip(), "%d.%m.%Y %H:%M")
        return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    except Exception:
        try:
            dt = datetime.strptime(date_str.strip()[:10], "%d.%m.%Y")
            return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        except Exception:
            return date_str


# ── Ana sayfa: maç listesi ────────────────────────────────────────────────────

def fetch_match_list(session: requests.Session) -> List[Dict]:
    """
    Excapper ana sayfasından tüm prematch maçları çek.
    Returns: [{'game_id', 'date_str', 'date_iso', 'league', 'home', 'away'}, ...]
    """
    r = session.get(BASE_URL + '/', headers=_get_headers(), timeout=FETCH_TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, 'html.parser')

    matches = []
    for row in soup.select('#premach tbody tr'):
        game_id = row.get('game_id', '').strip()
        if not game_id:
            continue
        tds = row.find_all('td')
        if len(tds) < 4:
            continue

        date_str = tds[0].get_text(strip=True)
        league = tds[2].get_text(strip=True)
        teams_raw = tds[3].get_text(strip=True)

        # "Home - Away" → home, away
        if ' - ' in teams_raw:
            idx = teams_raw.find(' - ')
            home = teams_raw[:idx].strip()
            away = teams_raw[idx + 3:].strip()
        else:
            home = teams_raw
            away = ""

        if not home or not away:
            continue

        matches.append({
            'game_id': game_id,
            'date_str': date_str,
            'date_iso': _parse_excapper_date(date_str),
            'league': league,
            'home': home,
            'away': away,
        })

    return matches


# ── Maç detay: odds + hacim + dropping ────────────────────────────────────────

def _parse_graphsdata_prev_odds(html: str, tab_id: str) -> Dict[str, float]:
    """
    graphsData JS'inden verilen tab_id için en eski (açılış) oranları çıkar.
    tab_id: 'tab_content_259033049' → numeric_id: '259033049'
    Returns: {'1': 2.50, 'X': 3.20, '2': 3.10, 'Over': 1.80, 'Under': 2.10, ...}
    """
    prev_odds: Dict[str, float] = {}
    try:
        # tab_content_259033049 → 259033049
        m_num = re.search(r'(\d+)', tab_id)
        if not m_num:
            return prev_odds
        nid = m_num.group(1)

        # graphsData[259033049]['odds'] bloğunu bul
        marker = f"graphsData[{nid}]['odds']"
        idx = html.find(marker)
        if idx < 0:
            return prev_odds

        # datasets bloğunun başını bul, sonra her label+data ikilisini doğrudan yakala
        block = html[idx: idx + 12000]

        # datasets: [ ... ] kapsamını bracket sayımıyla bul (iç içe array sorununu önle)
        ds_start = block.find('datasets:')
        if ds_start < 0:
            return prev_odds
        bopen = block.find('[', ds_start)
        if bopen < 0:
            return prev_odds
        depth = 0
        bclose = bopen
        for ci, ch in enumerate(block[bopen:], bopen):
            if ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    bclose = ci
                    break
        datasets_block = block[bopen: bclose + 1]

        # Her dataset: label: '1' ... data: [0, 2.60, ...] — ilk eşleşme kazanır
        for ds in re.finditer(
            r"label\s*:\s*['\"]([^'\"]+)['\"]\s*,.*?data\s*:\s*\[([^\]]*)\]",
            datasets_block, re.DOTALL
        ):
            label = ds.group(1).strip()
            if label in prev_odds:
                continue   # Sonraki bloğun verisi karışmasın
            nums = [
                float(x.strip()) for x in ds.group(2).split(',')
                if x.strip() and x.strip() not in ('0', '0.0', 'null', 'undefined')
            ]
            if nums:
                prev_odds[label] = nums[0]   # En eski non-zero = açılış oranı
    except Exception:
        pass
    return prev_odds


def fetch_match_detail(game_id: str, session: requests.Session) -> Dict[str, Any]:
    """
    Tek maç için excapper detay sayfasını çek ve parse et.

    Returns:
    {
        '1x2': {'1': (vol, odds, prev_odds), 'X': ..., '2': ...},
        'ou25': {'Over': ..., 'Under': ...},
        'btts': {'Yes': ..., 'No': ...},
    }
    Her tuple: (volume_float, current_odds_float, prev_odds_float_or_0)
    """
    try:
        url = f"{BASE_URL}/?action=game&id={game_id}"
        r = session.get(url, headers=_get_detail_headers(), timeout=FETCH_TIMEOUT)
        r.raise_for_status()
    except Exception:
        return {}

    html = r.text
    soup = BeautifulSoup(html, 'html.parser')
    result: Dict[str, Dict[str, Tuple[float, float, float]]] = {}

    for tab_link in soup.select('.smenu a[data-tab]'):
        tab_text = tab_link.get_text(strip=True)
        if tab_text not in MARKET_TAB_MAP:
            continue
        market_key = MARKET_TAB_MAP[tab_text]
        tab_id = tab_link.get('data-tab', '')

        tab_div = soup.find(id=tab_id)
        if not tab_div:
            continue

        # Önceki oranlar graphsData'dan
        prev_map = _parse_graphsdata_prev_odds(html, tab_id)

        # Mevcut oranlar + hacimler charts-bk__item-coef'den
        selections: Dict[str, Tuple[float, float, float]] = {}
        for item in tab_div.select('.charts-bk__item'):
            title_el = item.select_one('.charts-bk__item-title')
            coef_el = item.select_one('.charts-bk__item-coef')
            if not title_el or not coef_el:
                continue
            label = title_el.get_text(strip=True)
            vol, odds = _parse_coef_text(coef_el.get_text(strip=True))
            prev = prev_map.get(label, 0.0)
            selections[label] = (vol, odds, prev)

        if selections:
            result[market_key] = selections

    return result


# ── Row builder'lar ────────────────────────────────────────────────────────────

def _build_base(match: Dict) -> Dict[str, str]:
    return {
        'id': match['game_id'],
        'league': match['league'],
        'date': match['date_iso'],
        'home': match['home'],
        'away': match['away'],
    }


def build_moneyway_1x2(match: Dict, detail: Dict) -> Optional[Dict]:
    sels = detail.get('1x2', {})
    s1 = sels.get('1', (0, 0, 0))
    sx = sels.get('X', (0, 0, 0))
    s2 = sels.get('2', (0, 0, 0))
    if not (s1[0] or sx[0] or s2[0]):
        return None
    v1, o1, _ = s1
    vx, ox, _ = sx
    v2, o2, _ = s2
    total = v1 + vx + v2
    row = _build_base(match)
    row.update({
        'odds1': _to_odds_str(o1),
        'oddsx': _to_odds_str(ox),
        'odds2': _to_odds_str(o2),
        'pct1':  _to_pct_str(v1 / total * 100 if total else 0),
        'amt1':  _to_vol_str(v1),
        'pctx':  _to_pct_str(vx / total * 100 if total else 0),
        'amtx':  _to_vol_str(vx),
        'pct2':  _to_pct_str(v2 / total * 100 if total else 0),
        'amt2':  _to_vol_str(v2),
        'volume': _to_vol_str(total),
    })
    return row


def build_dropping_1x2(match: Dict, detail: Dict) -> Optional[Dict]:
    sels = detail.get('1x2', {})
    s1 = sels.get('1', (0, 0, 0))
    sx = sels.get('X', (0, 0, 0))
    s2 = sels.get('2', (0, 0, 0))
    if not (s1[0] or sx[0] or s2[0]):
        return None
    v1, o1, p1 = s1
    vx, ox, px = sx
    v2, o2, p2 = s2
    total = v1 + vx + v2
    row = _build_base(match)
    row.update({
        'odds1':      _to_odds_str(o1),
        'odds1_prev': _to_odds_str(p1),
        'oddsx':      _to_odds_str(ox),
        'oddsx_prev': _to_odds_str(px),
        'odds2':      _to_odds_str(o2),
        'odds2_prev': _to_odds_str(p2),
        'trend1':     _trend(o1, p1),
        'trendx':     _trend(ox, px),
        'trend2':     _trend(o2, p2),
        'volume':     _to_vol_str(total),
    })
    return row


def build_moneyway_ou25(match: Dict, detail: Dict) -> Optional[Dict]:
    sels = detail.get('ou25', {})
    sov = sels.get('Over', (0, 0, 0))
    sun = sels.get('Under', (0, 0, 0))
    if not (sov[0] or sun[0]):
        return None
    vov, oov, _ = sov
    vun, oun, _ = sun
    total = vov + vun
    row = _build_base(match)
    row.update({
        'over':    _to_odds_str(oov),
        'line':    '2.5',
        'under':   _to_odds_str(oun),
        'pctover':  _to_pct_str(vov / total * 100 if total else 0),
        'amtover':  _to_vol_str(vov),
        'pctunder': _to_pct_str(vun / total * 100 if total else 0),
        'amtunder': _to_vol_str(vun),
        'volume':   _to_vol_str(total),
    })
    return row


def build_dropping_ou25(match: Dict, detail: Dict) -> Optional[Dict]:
    sels = detail.get('ou25', {})
    sov = sels.get('Over', (0, 0, 0))
    sun = sels.get('Under', (0, 0, 0))
    if not (sov[0] or sun[0]):
        return None
    vov, oov, pov = sov
    vun, oun, pun = sun
    total = vov + vun
    row = _build_base(match)
    row.update({
        'over':      _to_odds_str(oov),
        'over_prev': _to_odds_str(pov),
        'line':      '2.5',
        'under':     _to_odds_str(oun),
        'under_prev': _to_odds_str(pun),
        'trendover':  _trend(oov, pov),
        'trendunder': _trend(oun, pun),
        'pctover':    _to_pct_str(vov / total * 100 if total else 0),
        'amtover':    _to_vol_str(vov),
        'pctunder':   _to_pct_str(vun / total * 100 if total else 0),
        'amtunder':   _to_vol_str(vun),
        'volume':     _to_vol_str(total),
    })
    return row


def build_moneyway_btts(match: Dict, detail: Dict) -> Optional[Dict]:
    sels = detail.get('btts', {})
    sys_ = sels.get('Yes', (0, 0, 0))
    sno  = sels.get('No',  (0, 0, 0))
    if not (sys_[0] or sno[0]):
        return None
    vyes, oyes, _ = sys_
    vno,  ono,  _ = sno
    total = vyes + vno
    row = _build_base(match)
    row.update({
        'yes':    _to_odds_str(oyes),
        'no':     _to_odds_str(ono),
        'pctyes': _to_pct_str(vyes / total * 100 if total else 0),
        'amtyes': _to_vol_str(vyes),
        'pctno':  _to_pct_str(vno  / total * 100 if total else 0),
        'amtno':  _to_vol_str(vno),
        'volume': _to_vol_str(total),
    })
    return row


def build_dropping_btts(match: Dict, detail: Dict) -> Optional[Dict]:
    sels = detail.get('btts', {})
    sys_ = sels.get('Yes', (0, 0, 0))
    sno  = sels.get('No',  (0, 0, 0))
    if not (sys_[0] or sno[0]):
        return None
    vyes, oyes, pyes = sys_
    vno,  ono,  pno  = sno
    total = vyes + vno
    row = _build_base(match)
    row.update({
        'oddsyes':      _to_odds_str(oyes),
        'oddsyes_prev': _to_odds_str(pyes),
        'oddsno':       _to_odds_str(ono),
        'oddsno_prev':  _to_odds_str(pno),
        'trendyes':     _trend(oyes, pyes),
        'trendno':      _trend(ono, pno),
        'pctyes':       _to_pct_str(vyes / total * 100 if total else 0),
        'amtyes':       _to_vol_str(vyes),
        'pctno':        _to_pct_str(vno  / total * 100 if total else 0),
        'amtno':        _to_vol_str(vno),
        'volume':       _to_vol_str(total),
    })
    return row


# ── Ana run fonksiyonu ────────────────────────────────────────────────────────

def run_scrape_excapper(writer, logger_callback=None) -> int:
    """
    Excapper.com'dan veri çek, Supabase'e yaz.
    standalone_scraper.run_scrape() ile aynı interface.
    Returns: toplam yazılan satır sayısı (0 = hata/boş)
    """
    _log = logger_callback if logger_callback else print
    _log("[Excapper] Scrape başlıyor...")

    # standalone_scraper utility'lerini import et
    try:
        import sys, os
        _dir = os.path.dirname(os.path.abspath(__file__))
        if _dir not in sys.path:
            sys.path.insert(0, _dir)
        from standalone_scraper import (
            make_match_id_hash, parse_date_to_kickoff,
            get_turkey_now, _parse_volume, _parse_percent_value,
        )
        scraped_at = get_turkey_now()
    except Exception as e:
        _log(f"[Excapper] standalone_scraper import hatası: {e}")
        import traceback
        _log(traceback.format_exc())
        return 0

    scraped_at_utc = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+00:00')
    session = requests.Session()

    # ── 1. Ana sayfa: maç listesi ──────────────────────────────────────────
    try:
        matches = fetch_match_list(session)
        _log(f"[Excapper]   {len(matches)} prematch maç bulundu")
        time.sleep(3.0)
    except Exception as e:
        _log(f"[Excapper] HATA: Ana sayfa çekilemedi: {e}")
        return 0

    if not matches:
        _log("[Excapper] UYARI: Maç bulunamadı")
        return 0

    # ── 2. Sadece gelecek maçlar ───────────────────────────────────────────
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    future = []
    for m in matches:
        ko_str = m['date_iso']
        try:
            ko_dt = datetime.strptime(ko_str[:19], '%Y-%m-%dT%H:%M:%S')
            if ko_dt > now_utc:
                future.append(m)
        except Exception:
            future.append(m)

    _log(f"[Excapper]   {len(future)} gelecek maç (kickoff geçmemiş)")
    if not future:
        return 0

    # ── 3. Paralel maç detayı çekme ───────────────────────────────────────
    _log(f"[Excapper]   Detaylar çekiliyor ({MAX_WORKERS} paralel)...")
    details: Dict[str, Dict] = {}

    def _fetch_one(match):
        gid = match['game_id']
        try:
            time.sleep(random.uniform(1.0, 2.5))
            return gid, fetch_match_detail(gid, session)
        except Exception as e:
            _log(f"[Excapper]   UYARI: game_id={gid} çekilemedi: {e}")
            return gid, {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        for gid, d in pool.map(_fetch_one, future):
            details[gid] = d

    # ── 4. Row'ları topla ─────────────────────────────────────────────────
    table_rows: Dict[str, List] = {
        'moneyway_1x2': [], 'moneyway_ou25': [], 'moneyway_btts': [],
        'dropping_1x2': [], 'dropping_ou25': [], 'dropping_btts': [],
    }
    all_fixtures: Dict[str, Dict] = {}
    all_snapshots: List[Dict] = []

    BUILDERS = [
        ('moneyway_1x2',  build_moneyway_1x2),
        ('dropping_1x2',  build_dropping_1x2),
        ('moneyway_ou25', build_moneyway_ou25),
        ('dropping_ou25', build_dropping_ou25),
        ('moneyway_btts', build_moneyway_btts),
        ('dropping_btts', build_dropping_btts),
    ]

    for match in future:
        gid = match['game_id']
        detail = details.get(gid, {})
        if not detail:
            continue

        home   = match['home']
        away   = match['away']
        league = match['league']
        date_iso = match['date_iso']

        kickoff_utc = parse_date_to_kickoff(date_iso)
        mhash = make_match_id_hash(home, away, league, kickoff_utc)

        if mhash not in all_fixtures:
            all_fixtures[mhash] = {
                'match_id_hash': mhash,
                'home_team':     home[:100],
                'away_team':     away[:100],
                'league':        league[:150],
                'kickoff_utc':   kickoff_utc,
                'fixture_date':  kickoff_utc[:10],
            }

        for tname, builder in BUILDERS:
            row = builder(match, detail)
            if row:
                table_rows[tname].append(row)

        # Moneyway snapshots (match_id_hash ile)
        def _snap(market, sel, odds_str, pct_str, amt_str):
            odds_f = float(odds_str) if odds_str else None
            vol_f  = _parse_volume(amt_str) if amt_str else None
            shr_f  = _parse_percent_value(pct_str) if pct_str else None
            if odds_f or vol_f or shr_f:
                all_snapshots.append({
                    'match_id_hash': mhash,
                    'market':        market,
                    'selection':     sel,
                    'odds':          odds_f,
                    'volume':        vol_f,
                    'share':         shr_f,
                    'scraped_at_utc': scraped_at_utc,
                })

        mw1 = build_moneyway_1x2(match, detail)
        if mw1:
            _snap('1X2', '1', mw1.get('odds1'), mw1.get('pct1'), mw1.get('amt1'))
            _snap('1X2', 'X', mw1.get('oddsx'), mw1.get('pctx'), mw1.get('amtx'))
            _snap('1X2', '2', mw1.get('odds2'), mw1.get('pct2'), mw1.get('amt2'))

        mwou = build_moneyway_ou25(match, detail)
        if mwou:
            _snap('OU25', 'O', mwou.get('over'), mwou.get('pctover'), mwou.get('amtover'))
            _snap('OU25', 'U', mwou.get('under'), mwou.get('pctunder'), mwou.get('amtunder'))

        mwbt = build_moneyway_btts(match, detail)
        if mwbt:
            _snap('BTTS', 'Y', mwbt.get('yes'), mwbt.get('pctyes'), mwbt.get('amtyes'))
            _snap('BTTS', 'N', mwbt.get('no'),  mwbt.get('pctno'),  mwbt.get('amtno'))

    # ── 5. Supabase'e yaz ─────────────────────────────────────────────────
    total_rows = 0
    write_errors = 0

    # Fixtures
    if all_fixtures:
        fl = list(all_fixtures.values())
        ok = writer.upsert_fixtures(fl)
        if ok:
            _log(f"[Excapper]   [OK] Fixtures: {len(fl)} maç")
        else:
            _log("[Excapper]   [HATA] Fixtures yazılamadı")
            write_errors += 1

    # Market tabloları
    TABLE_ORDER = [
        ('moneyway_1x2',  'moneyway_1x2_history'),
        ('moneyway_ou25', 'moneyway_ou25_history'),
        ('moneyway_btts', 'moneyway_btts_history'),
        ('dropping_1x2',  'dropping_1x2_history'),
        ('dropping_ou25', 'dropping_ou25_history'),
        ('dropping_btts', 'dropping_btts_history'),
    ]
    for main_tbl, hist_tbl in TABLE_ORDER:
        rows = table_rows[main_tbl]
        if not rows:
            _log(f"[Excapper]   [!] {main_tbl}: Veri bulunamadı")
            continue
        ok1 = writer.replace_table(main_tbl, rows)
        ok2 = writer.append_history(hist_tbl, rows, scraped_at)
        if ok1 and ok2:
            _log(f"[Excapper]   [OK] {main_tbl}: {len(rows)} satır")
            total_rows += len(rows)
        else:
            _log(f"[Excapper]   [HATA] {main_tbl}: yazma başarısız (main={ok1}, hist={ok2})")
            write_errors += 1

    # Snapshots
    if all_snapshots:
        ok = writer.insert_snapshots('moneyway_snapshots', all_snapshots)
        if ok:
            _log(f"[Excapper]   [OK] Snapshots: {len(all_snapshots)}")
        else:
            _log("[Excapper]   [HATA] Snapshots yazılamadı")
            write_errors += 1

    if write_errors:
        _log(f"[Excapper] UYARI: {write_errors} tabloda yazma hatası")

    _log(
        f"[Excapper] Scrape tamamlandı — "
        f"{total_rows} satır, {len(all_fixtures)} fixture, "
        f"{len(all_snapshots)} snapshot, {write_errors} hata"
    )
    return total_rows
