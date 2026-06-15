#!/usr/bin/env python3
"""
SmartXFlow Live Scraper
Canlı maç verilerini Betwatch.fr'den çeker (Betfair exchange oranları + para + skor + dakika).
Tüm veriler tek kaynak: Betwatch API v1 (live_info ile skor/dakika doğrudan gelir).
Prematch scraper'dan bağımsız çalışır.
"""
import os
import sys
import time
import re
import json
import hashlib
import requests
import traceback
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any


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

BETWATCH_V1_BASE = "https://api.betwatch.fr/api/v1"
print("[Betwatch] API v1 aktif — Token auth kullanılıyor", flush=True)

INTERVAL_MINUTES = 1
INTERVAL_SECONDS = INTERVAL_MINUTES * 60
WATCHDOG_MINUTES = 5
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
            for fix in list(fixtures):
                for field in ['score', 'minute']:
                    if not fix.get(field):
                        fix.pop(field, None)
            groups = {}
            for fix in fixtures:
                key = tuple(sorted(fix.keys()))
                groups.setdefault(key, []).append(fix)
            headers = self._headers()
            headers["Prefer"] = "resolution=merge-duplicates"
            url = f"{self._rest_url('live_fixtures')}?on_conflict=match_id_hash"
            for key_set, batch in groups.items():
                resp = requests.post(url, headers=headers, json=batch, timeout=30, verify=SSL_VERIFY)
                if resp.status_code not in [200, 201, 204]:
                    log(f"[Fixtures UPSERT] HTTP {resp.status_code}: {resp.text[:200]}")
                    return False
            return True
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

    def get_live_fixture_hashes(self) -> List[str]:
        try:
            headers = self._headers()
            url = f"{self._rest_url('live_fixtures')}?status=eq.live&select=match_id_hash"
            resp = requests.get(url, headers=headers, timeout=15, verify=SSL_VERIFY)
            if resp.status_code == 200:
                return [r['match_id_hash'] for r in resp.json()]
            return []
        except Exception as e:
            log(f"[GET live hashes] Hata: {e}")
            return []

    def get_live_fixture_info(self) -> Dict[str, str]:
        """Status=live olan maçların hash → kickoff_utc eşlemesini döndürür."""
        try:
            headers = self._headers()
            url = f"{self._rest_url('live_fixtures')}?status=eq.live&select=match_id_hash,kickoff_utc"
            resp = requests.get(url, headers=headers, timeout=15, verify=SSL_VERIFY)
            if resp.status_code == 200:
                return {r['match_id_hash']: r.get('kickoff_utc', '') for r in resp.json()}
            return {}
        except Exception as e:
            log(f"[GET live info] Hata: {e}")
            return {}

    def get_ft_fixture_hashes(self) -> set:
        try:
            headers = self._headers()
            url = f"{self._rest_url('live_fixtures')}?status=eq.ft&select=match_id_hash"
            resp = requests.get(url, headers=headers, timeout=15, verify=SSL_VERIFY)
            if resp.status_code == 200:
                return set(r['match_id_hash'] for r in resp.json())
            return set()
        except Exception:
            return set()

    def get_fixtures_by_hashes(self, hashes: List[str]) -> List[Dict]:
        if not hashes:
            return []
        try:
            headers = self._headers()
            hash_list = ','.join(hashes[:100])
            url = f"{self._rest_url('live_fixtures')}?match_id_hash=in.({hash_list})&select=match_id_hash,home_team,away_team,score"
            resp = requests.get(url, headers=headers, timeout=15, verify=SSL_VERIFY)
            if resp.status_code == 200:
                return resp.json()
            return []
        except Exception:
            return []

    def unmark_ft(self, hashes: List[str], fixtures_data: Dict[str, Dict]) -> int:
        if not hashes:
            return 0
        now_utc = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+00:00')
        recovered = 0
        headers = self._headers()
        for h in hashes:
            try:
                fix = fixtures_data.get(h, {})
                url = f"{self._rest_url('live_fixtures')}?match_id_hash=eq.{h}"
                patch = {"status": "live", "updated_at": now_utc}
                if fix.get('minute'):
                    patch['minute'] = fix['minute']
                if fix.get('score'):
                    patch['score'] = fix['score']
                resp = requests.patch(url, headers=headers, json=patch, timeout=10, verify=SSL_VERIFY)
                if resp.status_code in [200, 204]:
                    recovered += 1
            except Exception:
                pass
        return recovered

    def mark_fixtures_finished(self, hashes: List[str], final_scores: Dict[str, str] = None) -> int:
        if not hashes:
            return 0
        if final_scores is None:
            final_scores = {}
        now_utc = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+00:00')
        marked = 0
        headers = self._headers()
        for h in hashes:
            try:
                url = f"{self._rest_url('live_fixtures')}?match_id_hash=eq.{h}"
                patch = {"status": "ft", "minute": "FT", "updated_at": now_utc}
                if h in final_scores and final_scores[h]:
                    patch["score"] = final_scores[h]
                resp = requests.patch(url, headers=headers, json=patch, timeout=10, verify=SSL_VERIFY)
                if resp.status_code in [200, 204]:
                    marked += 1
            except Exception:
                pass
        return marked


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


def _betwatch_ko_to_utc(ce_val: str, fallback: str) -> str:
    """Betwatch'ın UTC kickoff zamanını UTC+3'e çevirir (uygulama TR saatiyle çalışır)."""
    if not ce_val:
        return fallback
    try:
        if ce_val.endswith('Z'):
            utc_time = datetime.fromisoformat(ce_val.replace('Z', '+00:00'))
            tr_time = utc_time + timedelta(hours=3)
            return tr_time.strftime('%Y-%m-%dT%H:%M:%S+03:00')
        dt = datetime.fromisoformat(ce_val)
        if dt.tzinfo is None:
            tr_time = dt + timedelta(hours=3)
            return tr_time.strftime('%Y-%m-%dT%H:%M:%S+03:00')
        return ce_val
    except Exception:
        return fallback


def _get_betwatch_v1_headers() -> dict:
    api_key = os.environ.get("Betwach_api_key", "")
    return {
        "Authorization": f"Token {api_key}",
        "Accept": "application/json",
        "User-Agent": "SmartXFlow/2.0",
    }


def _fetch_betwatch_v1_live() -> list:
    """Betwatch API v1 /football/live — canlı maçlar, live_info dahil."""
    try:
        resp = requests.get(
            f"{BETWATCH_V1_BASE}/football/live",
            headers=_get_betwatch_v1_headers(),
            timeout=30,
            verify=SSL_VERIFY,
        )
        if resp.status_code != 200:
            log(f"  [BW-v1] HTTP {resp.status_code}: {resp.text[:100]}")
            return []
        data = resp.json()
        matches = data if isinstance(data, list) else []
        log(f"  [BW-v1] {len(matches)} canlı maç alındı")
        return matches
    except Exception as e:
        log(f"  [BW-v1] Hata: {e}")
        return []


def _bw_v1_minute(live_info: dict) -> str:
    """live_info → dakika string."""
    if not live_info:
        return ""
    if live_info.get("finished"):
        return "FT"
    if live_info.get("is_ht"):
        return "HT"
    t = live_info.get("time", 0) or 0
    return f"{t}'"


def _bw_v1_score(live_info: dict) -> str:
    """live_info → skor string."""
    if not live_info:
        return ""
    g1 = live_info.get("goal_v1", 0) or 0
    g2 = live_info.get("goal_v2", 0) or 0
    return f"{g1}-{g2}"


def _map_live_market(mkt_name: str, runners: list):
    """Betwatch v1 market adı → (market_key, [(sel_code, runner), ...])"""
    name = (mkt_name or "").strip()
    if name == "Match Odds":
        if len(runners) < 2:
            return None, []
        sels = []
        for i, r in enumerate(runners):
            r_name = (r.get("name") or "").lower()
            if "draw" in r_name:
                sels.append(("X", r))
            elif not sels:
                sels.append(("1", r))
            else:
                sels.append(("2", r))
        if len(sels) == 3 and sels[1][0] != "X":
            sels[1] = ("X", sels[1][1])
        return "1X2", sels
    elif name.startswith("Over/Under"):
        line_m = re.search(r"([\d.]+)", name.replace("Over/Under", ""))
        line = line_m.group(1) if line_m else ""
        sels = []
        for r in runners:
            r_name = (r.get("name") or "").lower()
            if "over" in r_name:
                sels.append(("O", r))
            elif "under" in r_name:
                sels.append(("U", r))
        return ("OU", sels, line) if sels else (None, [], "")
    elif name == "Both teams to Score?":
        sels = []
        for r in runners:
            r_name = (r.get("name") or "").lower()
            if r_name in ("yes", "y"):
                sels.append(("Y", r))
            elif r_name in ("no", "n"):
                sels.append(("N", r))
        return ("BTTS", sels) if sels else (None, [])
    return None, []


def _process_betwatch_v1_live(matches: list, now_utc: str, today_str: str) -> tuple:
    """Betwatch v1 live maçları → (all_fixtures, all_snapshots, match_count).
    live_info'dan skor ve dakika doğrudan okunur — tek kaynak Betwatch.
    """
    all_fixtures = {}
    all_snapshots = []
    match_count = 0

    for match in matches:
        teams = match.get("teams", {}) or {}
        home = (teams.get("v1") or "").strip()
        away = (teams.get("v2") or "").strip()
        league = (match.get("league") or "").strip()
        kickoff_raw = match.get("kickoff", "") or ""
        live_info = match.get("live_info", {}) or {}

        if not home or not away:
            continue

        ko_utc = kickoff_raw.replace("Z", "+00:00") if kickoff_raw.endswith("Z") else kickoff_raw
        h = make_live_match_hash(home, away, league)

        minute = _bw_v1_minute(live_info)
        score = _bw_v1_score(live_info)
        status = "ft" if live_info.get("finished") else "live"

        all_fixtures[h] = {
            "match_id_hash": h,
            "home_team": home[:100],
            "away_team": away[:100],
            "league": league[:150],
            "score": score,
            "minute": minute,
            "status": status,
            "kickoff_utc": ko_utc,
            "fixture_date": today_str,
            "updated_at": now_utc,
        }
        match_count += 1

        markets = match.get("markets", []) or []
        for mkt in markets:
            mkt_name = mkt.get("name", "")
            runners = mkt.get("runners", []) or []

            mapped = _map_live_market(mkt_name, runners)
            if mapped[0] is None:
                continue

            if mapped[0] == "OU":
                market_key, sels, ou_line = mapped
            else:
                market_key, sels = mapped
                ou_line = None

            total_vol = sum(float(r.get("volume") or 0) for r in runners)

            for sel_code, runner in sels:
                vol = float(runner.get("volume") or 0)
                odd = runner.get("odd")
                odd_f = float(odd) if odd is not None else None
                share = round(vol / total_vol * 100, 1) if total_vol > 0 else 0.0

                all_snapshots.append({
                    "match_id_hash": h,
                    "snapshot_at": now_utc,
                    "market": market_key,
                    "selection": sel_code,
                    "odds": odd_f,
                    "share": share,
                    "volume": vol,
                    "ou_line": ou_line,
                })

    log(f"  [BW-v1] {match_count} maç, {len(all_snapshots)} snapshot işlendi")
    return all_fixtures, all_snapshots, match_count


def run_live_scrape(writer: LiveSupabaseWriter) -> int:
    """Betwatch API v1'den canlı maçları çeker (oranlar + para + skor + dakika).
    Tüm veri Betwatch API v1'den gelir — live_info ile skor/dakika dahil."""
    log("CANLI SCRAPE BAŞLIYOR...")
    now_utc = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+00:00')
    today_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    log("  Betwatch v1 live verisi çekiliyor...")
    matches = _fetch_betwatch_v1_live()

    bw_result = {"fetch_ok": bool(matches)}

    all_fixtures, all_snapshots, total_matches = _process_betwatch_v1_live(matches, now_utc, today_str)

    if all_fixtures:
        now_dt = datetime.now(timezone.utc)
        auto_ft_count = 0
        auto_ft_skipped = 0
        for h, fix in all_fixtures.items():
            if fix.get('status') == 'ft':
                continue
            ko_str = fix.get('kickoff_utc', '')
            if ko_str:
                try:
                    ko_time = datetime.fromisoformat(ko_str)
                    diff_min = (now_dt - ko_time).total_seconds() / 60
                    if diff_min >= 120:
                        fix_min = fix.get('minute', '')
                        if fix_min and fix_min not in ('FT', 'MS', 'AET', 'PEN'):
                            auto_ft_skipped += 1
                            continue
                        fix['status'] = 'ft'
                        if not fix.get('minute') or fix['minute'] not in ('FT', 'MS', 'AET', 'PEN'):
                            fix['minute'] = 'FT'
                        auto_ft_count += 1
                except Exception:
                    pass
        if auto_ft_count:
            log(f"  [AUTO-FT] {auto_ft_count} maç 120+ dk geçtiği için otomatik FT yapıldı")
        if auto_ft_skipped:
            log(f"  [AUTO-FT SKIP] {auto_ft_skipped} maç 120+ dk ama dakika bilgisi aktif, atlandı")
        already_ft = writer.get_ft_fixture_hashes()
        ft_skipped = 0
        ft_recovered = []
        fixtures_list = []
        for h, fix in all_fixtures.items():
            if h in already_ft and fix.get('status') != 'ft':
                fix_minute = fix.get('minute', '')
                if fix_minute and fix_minute not in ('FT', 'MS', 'AET', 'PEN'):
                    ft_recovered.append(h)
                    log(f"  [FT-RECOVERY] {fix.get('home_team','')[:20]} vs {fix.get('away_team','')[:20]} | dk={fix_minute} skor={fix.get('score','')} | FT geri alınıyor")
                    fixtures_list.append(fix)
                else:
                    ft_skipped += 1
                    continue
            else:
                fixtures_list.append(fix)
        if ft_recovered:
            recovered_count = writer.unmark_ft(ft_recovered, all_fixtures)
            log(f"  [FT-RECOVERY] {recovered_count}/{len(ft_recovered)} maç FT'den live'a döndürüldü")
        if ft_skipped:
            log(f"  [SKIP] {ft_skipped} zaten FT olan maç atlandı")
        if fixtures_list:
            if writer.upsert_live_fixtures(fixtures_list):
                log(f"  [FIXTURES] {len(fixtures_list)} canlı maç yazıldı")
            else:
                log(f"  [HATA] Fixtures yazılamadı!")

    if all_snapshots:
        for snap in all_snapshots:
            fix = all_fixtures.get(snap['match_id_hash'])
            if fix:
                snap['score'] = fix.get('score', '')
                snap['minute'] = str(fix.get('minute', ''))
            else:
                snap['score'] = ''
                snap['minute'] = ''

        odds_by_match = {}
        for snap in all_snapshots:
            h = snap['match_id_hash']
            if h not in odds_by_match:
                odds_by_match[h] = {}
            if snap.get('market') == '1X2' and snap.get('selection') == '1':
                odds_by_match[h]['odds1'] = snap.get('odds', '')
            elif snap.get('market') == '1X2' and snap.get('selection') == 'X':
                odds_by_match[h]['oddsX'] = snap.get('odds', '')
            elif snap.get('market') == '1X2' and snap.get('selection') == '2':
                odds_by_match[h]['odds2'] = snap.get('odds', '')
        log(f"  [DEBUG] BW snapshot özet:")
        for h, fix in all_fixtures.items():
            o = odds_by_match.get(h, {})
            o1 = o.get('odds1', '-')
            oX = o.get('oddsX', '-')
            o2 = o.get('odds2', '-')
            log(f"    {fix.get('home_team','')[:15]:15s} vs {fix.get('away_team','')[:15]:15s} | dk={fix.get('minute','?'):5s} skor={fix.get('score','?'):5s} | 1={o1} X={oX} 2={o2}")

        if writer.insert_live_snapshots(all_snapshots):
            log(f"  [SNAPSHOTS] {len(all_snapshots)} snapshot yazıldı")
        else:
            log(f"  [HATA] Snapshots yazılamadı!")

    stale_keys = [k for k in _kickoff_cache if k not in all_fixtures]
    for k in stale_keys:
        del _kickoff_cache[k]

    if bw_result.get("fetch_ok"):
        existing_live_info = writer.get_live_fixture_info()
        current_hashes = set(all_fixtures.keys())
        now_dt = datetime.now(timezone.utc)
        stale_hashes = []
        skipped_early = []
        for h, ko_str in existing_live_info.items():
            if h in current_hashes:
                continue
            elapsed_min = 999
            if ko_str:
                try:
                    ko_time = datetime.fromisoformat(ko_str)
                    elapsed_min = (now_dt - ko_time).total_seconds() / 60
                except Exception:
                    pass
            if elapsed_min < 89:
                skipped_early.append((h, elapsed_min))
                continue
            stale_hashes.append(h)
        if skipped_early:
            log(f"  [KORUMA] {len(skipped_early)} maç erken FT'den korundu (89 dk dolmadı):")
            for h, em in skipped_early:
                info = existing_live_info.get(h, '')
                log(f"    hash={h} kickoff={info} elapsed={em:.0f}dk")
        if stale_hashes:
            marked = writer.mark_fixtures_finished(stale_hashes)
            log(f"  [MS] {marked}/{len(stale_hashes)} biten maç FT olarak işaretlendi")
    else:
        log("  [UYARI] Betwatch verisi alınamadı, FT işaretleme atlanıyor")

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
