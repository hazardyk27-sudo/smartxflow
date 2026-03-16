#!/usr/bin/env python3
"""
SmartXFlow Live Scraper
Canlı maç verilerini 3 dakikada bir Arbworld'den çeker.
1X2 Live + Over/Under Multiple Live
Prematch scraper'dan bağımsız çalışır.
"""
import os
import sys
import time
import re
import hashlib
import requests
import traceback
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scraper_standalone'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'desktop', 'scraper_standalone'))

try:
    import certifi
    SSL_VERIFY = certifi.where()
except:
    SSL_VERIFY = True

try:
    import pytz
    TURKEY_TZ = pytz.timezone('Europe/Istanbul')
except ImportError:
    TURKEY_TZ = None

HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

arbworld_cookie = os.environ.get('ARBWORLD_COOKIE', '')
if arbworld_cookie:
    HEADERS['Cookie'] = arbworld_cookie
    print(f"[Live Cookie] ARBWORLD_COOKIE enjekte edildi ({len(arbworld_cookie)} karakter)")
else:
    print("[Live Cookie] ARBWORLD_COOKIE bulunamadi - cookie'siz devam ediliyor")

LIVE_URLS = {
    "live-1x2": "https://arbworld.net/en/moneyway/football-1-x-2-live",
    "live-ou": "https://arbworld.net/en/moneyway/football-over-under-multiple-live",
}

INTERVAL_MINUTES = 3
INTERVAL_SECONDS = INTERVAL_MINUTES * 60
WATCHDOG_MINUTES = 7
WATCHDOG_SECONDS = WATCHDOG_MINUTES * 60
MAX_RETRIES = 3
RETRY_DELAYS = [3, 6, 12]
SCRAPER_SOURCE = "replit-live"

_kickoff_cache = {}


def get_turkey_now() -> str:
    if TURKEY_TZ:
        return datetime.now(TURKEY_TZ).strftime('%Y-%m-%dT%H:%M:%S+03:00')
    return datetime.now().strftime('%Y-%m-%dT%H:%M:%S+03:00')


def log(msg: str):
    ts = datetime.now(TURKEY_TZ).strftime('%H:%M:%S') if TURKEY_TZ else datetime.now().strftime('%H:%M:%S')
    print(f"[Live {ts}] {msg}", flush=True)


def send_telegram(message: str, is_error: bool = False) -> bool:
    bot_token = os.environ.get('PAYMENT_BOT_TOKEN')
    chat_id = os.environ.get('PAYMENT_CHAT_ID')
    if not bot_token or not chat_id:
        return False
    try:
        emoji = "🔴" if is_error else "🟢"
        url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
        data = {'chat_id': chat_id, 'text': f"{emoji} {message}", 'parse_mode': 'HTML'}
        r = requests.post(url, data=data, timeout=10)
        return r.status_code == 200
    except Exception as e:
        log(f"[Telegram] Hata: {e}")
        return False


def normalize_field(s: str) -> str:
    if not s:
        return ""
    s = s.strip().lower()
    s = re.sub(r'\s+', ' ', s)
    return s


def make_live_match_hash(home: str, away: str, league: str) -> str:
    h = normalize_field(home)
    a = normalize_field(away)
    l = normalize_field(league)
    canonical = f"{l}|{h}|{a}"
    return hashlib.md5(canonical.encode('utf-8')).hexdigest()[:12]


def _text(node) -> str:
    return node.get_text(strip=True) if node else ""


def _parse_pct_amt(td) -> tuple:
    joined = " ".join(list(td.stripped_strings))
    m_pct = re.search(r"(\d+(?:\.\d+)?)\s*%", joined)
    pct = float(m_pct.group(1)) if m_pct else 0.0
    m_amt = re.search(r"£\s*([\d\s\.]+\s*[MKmk]?)", joined)
    amt_str = m_amt.group(1).strip() if m_amt else ""
    amt = _parse_volume(f"£ {amt_str}") if amt_str else 0.0
    return pct, amt


def _parse_volume(vol_str: str) -> float:
    if not vol_str:
        return 0.0
    vol_str = vol_str.replace('£', '').replace(',', '').strip()
    vol_str = re.sub(r'\s+', '', vol_str)
    multiplier = 1.0
    if vol_str.upper().endswith('M'):
        multiplier = 1000000
        vol_str = vol_str[:-1]
    elif vol_str.upper().endswith('K'):
        multiplier = 1000
        vol_str = vol_str[:-1]
    try:
        return float(vol_str.strip()) * multiplier
    except:
        return 0.0


def _parse_odds(s: str) -> Optional[float]:
    if not s:
        return None
    s = s.strip()
    try:
        return float(s)
    except:
        return None


def _parse_minute(date_str: str) -> str:
    """Parse minute/time from tdate column. Format: '16.Mar14:31:49' or '16.Mar HT' etc."""
    if not date_str:
        return ""
    m = re.search(r'(\d{1,2}):(\d{2}):(\d{2})$', date_str)
    if m:
        return f"{m.group(1)}:{m.group(2)}:{m.group(3)}"
    for marker in ['HT', 'FT', '1H', '2H', 'ET', 'PEN']:
        if marker in date_str.upper():
            return marker
    return date_str.strip()


def fetch_table(url: str, session: requests.Session) -> BeautifulSoup:
    resp = session.get(url, headers=HEADERS, timeout=30, verify=SSL_VERIFY)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.select_one("table#matches.table_matches")
    if not table:
        table = soup.find("table", id="matches") or soup.find("table", class_="table_matches")
    if not table:
        raise RuntimeError(f"Tablo bulunamadi: {url}")
    return table


def extract_live_1x2(table: BeautifulSoup) -> List[Dict[str, Any]]:
    rows = []
    for tr in table.select("tbody tr"):
        league = _text(tr.select_one("td.tleague"))
        if not league:
            continue
        date_text = _text(tr.select_one("td.tdate"))
        home = _text(tr.select_one("td.thome"))
        away = _text(tr.select_one("td.taway"))
        volume_text = _text(tr.select_one("td.tvol"))
        volume = _parse_volume(volume_text)

        odds_small = [td.get_text(strip=True) for td in tr.select("td.odds_col_small")][:3]
        while len(odds_small) < 3:
            odds_small.append("")

        pct_cells = tr.select("td.odds_col")[:3]
        pct_amt_values = [_parse_pct_amt(td) for td in pct_cells]
        while len(pct_amt_values) < 3:
            pct_amt_values.append((0.0, 0.0))

        match_hash = make_live_match_hash(home, away, league)

        rows.append({
            "match_id_hash": match_hash,
            "league": league,
            "date_text": date_text,
            "home": home,
            "away": away,
            "volume": volume,
            "volume_text": volume_text,
            "odds1": _parse_odds(odds_small[0]),
            "oddsx": _parse_odds(odds_small[1]),
            "odds2": _parse_odds(odds_small[2]),
            "pct1": pct_amt_values[0][0],
            "amt1": pct_amt_values[0][1],
            "pctx": pct_amt_values[1][0],
            "amtx": pct_amt_values[1][1],
            "pct2": pct_amt_values[2][0],
            "amt2": pct_amt_values[2][1],
        })
    return rows


def extract_live_ou(table: BeautifulSoup) -> List[Dict[str, Any]]:
    rows = []
    for tr in table.select("tbody tr"):
        league = _text(tr.select_one("td.tleague"))
        if not league:
            continue
        date_text = _text(tr.select_one("td.tdate"))
        home = _text(tr.select_one("td.thome"))
        away = _text(tr.select_one("td.taway"))
        volume_text = _text(tr.select_one("td.tvol"))
        volume = _parse_volume(volume_text)

        small = [td.get_text(strip=True) for td in tr.select("td.odds_col_small")]
        under_odds = _parse_odds(small[0]) if len(small) > 0 else None
        line = small[1] if len(small) > 1 else ""
        over_odds = _parse_odds(small[2]) if len(small) > 2 else None

        pct_cells = tr.select("td.odds_col")
        pct_under, amt_under = _parse_pct_amt(pct_cells[0]) if len(pct_cells) > 0 else (0.0, 0.0)
        pct_over, amt_over = _parse_pct_amt(pct_cells[1]) if len(pct_cells) > 1 else (0.0, 0.0)

        match_hash = make_live_match_hash(home, away, league)

        rows.append({
            "match_id_hash": match_hash,
            "league": league,
            "date_text": date_text,
            "home": home,
            "away": away,
            "volume": volume,
            "volume_text": volume_text,
            "line": line,
            "under_odds": under_odds,
            "over_odds": over_odds,
            "pct_under": pct_under,
            "amt_under": amt_under,
            "pct_over": pct_over,
            "amt_over": amt_over,
        })
    return rows


class LiveSupabaseWriter:
    def __init__(self, url: str, key: str):
        self.url = url.rstrip('/')
        self.key = key
        self.supabase_url = url
        self.supabase_key = key

    def _headers(self) -> Dict[str, str]:
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json"
        }

    def _rest_url(self, table: str) -> str:
        return f"{self.url}/rest/v1/{table}"

    def upsert_live_fixtures(self, fixtures: List[Dict]) -> bool:
        if not fixtures:
            return True
        try:
            headers = self._headers()
            headers["Prefer"] = "resolution=merge-duplicates"
            url = f"{self._rest_url('live_fixtures')}?on_conflict=match_id_hash"
            resp = requests.post(url, headers=headers, json=fixtures, timeout=30, verify=SSL_VERIFY)
            if resp.status_code in [200, 201, 204]:
                return True
            else:
                log(f"[Fixtures UPSERT] HTTP {resp.status_code}: {resp.text[:200]}")
                return False
        except Exception as e:
            log(f"[Fixtures UPSERT] Hata: {e}")
            return False

    def insert_live_snapshots(self, snapshots: List[Dict]) -> bool:
        if not snapshots:
            return True
        try:
            headers = self._headers()
            url = self._rest_url('live_snapshots')
            resp = requests.post(url, headers=headers, json=snapshots, timeout=30, verify=SSL_VERIFY)
            if resp.status_code in [200, 201, 204]:
                return True
            else:
                log(f"[Snapshots INSERT] HTTP {resp.status_code}: {resp.text[:200]}")
                return False
        except Exception as e:
            log(f"[Snapshots INSERT] Hata: {e}")
            return False


def update_heartbeat(supabase_url: str, supabase_key: str, status: str, match_count: int = 0, error_msg: Optional[str] = None) -> bool:
    try:
        now = datetime.now(timezone.utc).isoformat()
        data = {
            "source": SCRAPER_SOURCE,
            "last_heartbeat": now,
            "status": status,
            "match_count": match_count,
            "error_message": error_msg,
            "updated_at": now
        }
        url = f"{supabase_url.rstrip('/')}/rest/v1/scraper_heartbeat?on_conflict=source"
        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation,resolution=merge-duplicates"
        }
        r = requests.post(url, json=data, headers=headers, timeout=10)
        success = r.status_code in [200, 201]
        if success:
            log(f"[Heartbeat] {status} - {match_count} canlı maç")
        return success
    except Exception as e:
        log(f"[Heartbeat] Hata: {e}")
        return False


def run_live_scrape(writer: LiveSupabaseWriter) -> int:
    log("CANLI SCRAPE BAŞLIYOR...")
    session = requests.Session()
    now_utc = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+00:00')
    today_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    all_fixtures = {}
    all_snapshots = []
    total_matches = 0

    for dataset_key, url in LIVE_URLS.items():
        try:
            log(f"  {dataset_key} çekiliyor...")
            table = fetch_table(url, session)

            if dataset_key == "live-1x2":
                rows = extract_live_1x2(table)
                for row in rows:
                    h = row["match_id_hash"]
                    if h not in all_fixtures:
                        if h not in _kickoff_cache:
                            _kickoff_cache[h] = now_utc
                        all_fixtures[h] = {
                            "match_id_hash": h,
                            "home_team": row["home"][:100],
                            "away_team": row["away"][:100],
                            "league": row["league"][:150],
                            "score": "",
                            "minute": _parse_minute(row["date_text"]),
                            "status": "live",
                            "kickoff_utc": _kickoff_cache[h],
                            "fixture_date": today_str,
                            "updated_at": now_utc,
                        }

                    for sel, odds, share, vol in [
                        ('1', row["odds1"], row["pct1"], row["amt1"]),
                        ('X', row["oddsx"], row["pctx"], row["amtx"]),
                        ('2', row["odds2"], row["pct2"], row["amt2"]),
                    ]:
                        all_snapshots.append({
                            "match_id_hash": h,
                            "snapshot_at": now_utc,
                            "market": "1X2",
                            "selection": sel,
                            "odds": odds,
                            "share": share,
                            "volume": vol,
                            "ou_line": None,
                        })

                log(f"  [OK] live-1x2: {len(rows)} maç")
                total_matches += len(rows)

            elif dataset_key == "live-ou":
                rows = extract_live_ou(table)
                for row in rows:
                    h = row["match_id_hash"]
                    if h not in all_fixtures:
                        if h not in _kickoff_cache:
                            _kickoff_cache[h] = now_utc
                        all_fixtures[h] = {
                            "match_id_hash": h,
                            "home_team": row["home"][:100],
                            "away_team": row["away"][:100],
                            "league": row["league"][:150],
                            "score": "",
                            "minute": _parse_minute(row["date_text"]),
                            "status": "live",
                            "kickoff_utc": _kickoff_cache[h],
                            "fixture_date": today_str,
                            "updated_at": now_utc,
                        }

                    line = row.get("line", "")
                    for sel, odds, share, vol in [
                        ('U', row["under_odds"], row["pct_under"], row["amt_under"]),
                        ('O', row["over_odds"], row["pct_over"], row["amt_over"]),
                    ]:
                        all_snapshots.append({
                            "match_id_hash": h,
                            "snapshot_at": now_utc,
                            "market": "OU",
                            "selection": sel,
                            "odds": odds,
                            "share": share,
                            "volume": vol,
                            "ou_line": line,
                        })

                log(f"  [OK] live-ou: {len(rows)} maç")
                total_matches += len(rows)

        except Exception as e:
            log(f"  [HATA] {dataset_key}: {e}")
            traceback.print_exc()

    if all_fixtures:
        fixtures_list = list(all_fixtures.values())
        if writer.upsert_live_fixtures(fixtures_list):
            log(f"  [FIXTURES] {len(fixtures_list)} canlı maç yazıldı")
        else:
            log(f"  [HATA] Fixtures yazılamadı!")

    if all_snapshots:
        if writer.insert_live_snapshots(all_snapshots):
            log(f"  [SNAPSHOTS] {len(all_snapshots)} snapshot yazıldı")
        else:
            log(f"  [HATA] Snapshots yazılamadı!")

    stale_keys = [k for k in _kickoff_cache if k not in all_fixtures]
    for k in stale_keys:
        del _kickoff_cache[k]

    log(f"Canlı scrape tamamlandı - {len(all_fixtures)} maç, {len(all_snapshots)} snapshot")
    return len(all_fixtures)


def check_live_master_status(supabase_url: str, supabase_key: str) -> tuple:
    """Check if another live scraper instance is active (master/slave arbitration)."""
    try:
        url = f"{supabase_url}/rest/v1/scraper_heartbeat?select=*"
        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}"
        }
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return True, "api_error_fallback"

        rows = r.json()
        if not rows:
            return True, "no_master"

        now = datetime.now(timezone.utc)

        for row in rows:
            src = row.get("source", "")
            if src == SCRAPER_SOURCE:
                continue
            if not src.endswith("-live"):
                continue
            beat_str = row.get("last_heartbeat", "")
            if not beat_str:
                continue
            try:
                beat_time = datetime.fromisoformat(beat_str.replace("Z", "+00:00"))
                if beat_time.tzinfo is None:
                    beat_time = beat_time.replace(tzinfo=timezone.utc)
                diff_minutes = (now - beat_time).total_seconds() / 60
                if diff_minutes < 5 and row.get("status") == "active":
                    return False, f"{src} is master ({diff_minutes:.1f} min ago)"
            except:
                continue

        return True, "i_am_master"
    except Exception as e:
        log(f"[Master Check] Hata: {e}, devam ediyorum")
        return True, "error_fallback"


def main():
    log("=" * 50)
    log("SmartXFlow Live Scraper")
    log(f"Zaman: {datetime.now(timezone.utc).isoformat()}")
    log("=" * 50)

    supabase_url = os.environ.get('SUPABASE_URL')
    supabase_key = os.environ.get('SUPABASE_ANON_KEY')

    if not supabase_url or not supabase_key:
        error_msg = "SUPABASE_URL veya SUPABASE_ANON_KEY eksik!"
        log(f"[FATAL] {error_msg}")
        send_telegram(f"LIVE SCRAPER FATAL: {error_msg}", is_error=True)
        return False

    is_master, reason = check_live_master_status(supabase_url, supabase_key)
    if not is_master:
        log(f"[Master] Başka bir live scraper aktif: {reason}")
        log("[Master] Slave modunda, veri yazmıyorum")
        update_heartbeat(supabase_url, supabase_key, "standby", 0, reason)
        return True

    log(f"[Master] Ben master oluyorum: {reason}")
    update_heartbeat(supabase_url, supabase_key, "starting", 0)

    try:
        writer = LiveSupabaseWriter(supabase_url, supabase_key)
        log("[Supabase] Writer oluşturuldu")
    except Exception as e:
        error_msg = f"Writer hatası: {e}"
        log(f"[FATAL] {error_msg}")
        send_telegram(f"LIVE SCRAPER FATAL: {error_msg}", is_error=True)
        return False

    last_error = None
    match_count = 0
    for attempt in range(MAX_RETRIES):
        try:
            log(f"[Deneme] {attempt + 1}/{MAX_RETRIES}")
            match_count = run_live_scrape(writer)
            if match_count >= 0:
                update_heartbeat(supabase_url, supabase_key, "active", match_count)
                return True
        except Exception as e:
            last_error = str(e)[:200]
            log(f"[HATA] {last_error}")
            traceback.print_exc()

        if attempt < MAX_RETRIES - 1:
            delay = RETRY_DELAYS[attempt]
            log(f"{delay} saniye bekleniyor...")
            time.sleep(delay)

    if last_error:
        send_telegram(f"LIVE SCRAPER HATA ({MAX_RETRIES} retry):\n{last_error}", is_error=True)
        update_heartbeat(supabase_url, supabase_key, "error", 0, last_error)

    return False


def run_loop():
    log(f"Live Scraper {INTERVAL_MINUTES} dakikada bir çalışacak")
    log(f"Watchdog: {WATCHDOG_MINUTES} dk veri gelmezse Telegram uyarısı")

    last_successful = None
    watchdog_sent = False

    while True:
        ok = False
        try:
            result = main()
            ok = result if isinstance(result, bool) else True
            if ok:
                last_successful = datetime.now(timezone.utc)
                if watchdog_sent:
                    send_telegram("<b>LIVE SCRAPER TEKRAR ÇALIŞIYOR</b>\nCanlı veri akışı normale döndü.", is_error=False)
                    watchdog_sent = False
        except Exception as e:
            log(f"[Loop] main() hatası: {e}")
            traceback.print_exc()

        if not ok or last_successful is None:
            now = datetime.now(timezone.utc)
            elapsed = (now - last_successful).total_seconds() if last_successful else WATCHDOG_SECONDS + 1
            if elapsed >= WATCHDOG_SECONDS and not watchdog_sent:
                send_telegram(
                    f"<b>⚠️ LIVE SCRAPER UYARI</b>\n"
                    f"Canlı scraper <b>{elapsed/60:.0f} dakikadır</b> veri çekemiyor!\n"
                    f"Son başarılı: {last_successful.strftime('%H:%M UTC') if last_successful else 'Hiç'}",
                    is_error=True
                )
                watchdog_sent = True
                log(f"[Watchdog] Telegram uyarısı gönderildi ({elapsed/60:.0f} dk)")

        log(f"Sonraki çalışma {INTERVAL_MINUTES} dakika sonra...")
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    run_loop()
