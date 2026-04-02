#!/usr/bin/env python3
"""
SmartXFlow Live Scraper
Canlı maç verilerini Betwatch.fr'den çeker (Betfair exchange oranları + para).
Skor/dakika Sofascore'dan gelir.
Prematch scraper'dan bağımsız çalışır.
"""
import os
import sys
import time
import re
import hashlib
import requests
import traceback
import difflib
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
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

BETWATCH_GETMONEY_URL = "https://www.betwatch.fr/football/getMoney"
BETWATCH_GETMAIN_URL = "https://www.betwatch.fr/football/getMain"
BETWATCH_COOKIE = os.environ.get("BETWATCH_COOKIE", "")
BETWATCH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.betwatch.fr/money",
}
if BETWATCH_COOKIE:
    BETWATCH_HEADERS["Cookie"] = BETWATCH_COOKIE
    print(f"[Betwatch] Cookie enjekte edildi ({len(BETWATCH_COOKIE)} karakter)", flush=True)
else:
    print("[Betwatch] UYARI: BETWATCH_COOKIE env bulunamadı!", flush=True)

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


SOFASCORE_URL = "https://api.sofascore.com/api/v1/sport/football/events/live"
SOFASCORE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


_TEAM_ABBREVS = {
    'utd': 'united',
    'muni': 'munich',
    'man': 'manchester',
    'cty': 'city',
    'wed': 'wednesday',
    'ath': 'athletic',
}

def _normalize_team(name: str) -> str:
    if not name:
        return ""
    s = unicodedata.normalize('NFKD', name)
    s = s.encode('ascii', 'ignore').decode('ascii')
    s = re.sub(r'[^a-z0-9 ]', '', s.lower())
    s = re.sub(r'\s+', ' ', s).strip()
    for suffix in [' fc', ' sc', ' fk', ' sk', ' cf', ' ac', ' as', ' bc']:
        if s.endswith(suffix):
            s = s[:-len(suffix)].strip()
    words = s.split()
    expanded = [_TEAM_ABBREVS.get(w, w) for w in words]
    s = ' '.join(expanded)
    if s.endswith(' w'):
        s = s[:-2] + ' women'
    return s


def _calc_sofascore_minute(event: Dict) -> str:
    status = event.get('status', {})
    desc = status.get('description', '')
    code = status.get('code', 0)
    if code == 31 or desc == 'Halftime':
        return 'HT'
    if code == 100 or desc == 'Ended':
        return 'FT'
    if code == 120 or desc == 'AP':
        return 'PEN'
    stype = status.get('type', '')
    if stype == 'notstarted':
        return ''
    time_info = event.get('time', {})
    period_start = time_info.get('currentPeriodStartTimestamp', 0)
    initial = time_info.get('initial', 0)
    now_ts = int(time.time())
    if period_start > 0:
        elapsed_secs = max(0, now_ts - period_start)
        base_min = initial // 60
        current_min = base_min + elapsed_secs // 60
        if code == 6 and current_min > 45:
            return f"45+{current_min - 45}'"
        if code == 7 and current_min > 90:
            return f"90+{current_min - 90}'"
        return f"{current_min}'"
    return ''


def _fetch_sofascore_live() -> Dict[str, Dict]:
    try:
        resp = requests.get(SOFASCORE_URL, headers=SOFASCORE_HEADERS, timeout=15)
        if resp.status_code != 200:
            log(f"  [Sofascore] HTTP {resp.status_code}")
            return {}
        data = resp.json()
        events = data.get('events', [])
        if not isinstance(events, list):
            log(f"  [Sofascore] events beklenen list degil: {type(events)}")
            return {}
        result = {}
        for ev in events:
            home = ev.get('homeTeam', {}).get('name', '')
            away = ev.get('awayTeam', {}).get('name', '')
            if not home or not away:
                continue
            h_score = ev.get('homeScore', {}).get('current', '')
            a_score = ev.get('awayScore', {}).get('current', '')
            score_str = f"{h_score}-{a_score}" if h_score != '' and a_score != '' else ''
            minute_str = _calc_sofascore_minute(ev)
            start_ts = ev.get('startTimestamp', 0)
            kickoff_utc = ''
            if start_ts:
                kickoff_utc = datetime.fromtimestamp(start_ts, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+00:00')
            tournament_name = ev.get('tournament', {}).get('name', '')
            key = _normalize_team(home) + '|' + _normalize_team(away)
            result[key] = {
                'score': score_str,
                'minute': minute_str,
                'home': home,
                'away': away,
                'kickoff_utc': kickoff_utc,
                'league': tournament_name,
            }
        log(f"  [Sofascore] {len(result)} canlı maç bulundu")
        return result
    except Exception as e:
        log(f"  [Sofascore] Hata: {e}")
        return {}


def _team_match_score(arb: str, fs: str) -> float:
    if not arb or not fs:
        return 0.0
    if arb == fs:
        return 1.0
    if fs.startswith(arb) or arb.startswith(fs):
        shorter = min(len(arb), len(fs))
        if shorter >= 4:
            return 0.90
    shorter = min(len(arb), len(fs))
    if shorter >= 4:
        if arb in fs or fs in arb:
            return 0.85
        arb_words = arb.split()
        fs_words = fs.split()
        if len(arb_words) == 1 and arb_words[0] in fs_words:
            return 0.85
        if len(fs_words) == 1 and fs_words[0] in arb_words:
            return 0.85
    return difflib.SequenceMatcher(None, arb, fs).ratio()


def _kickoff_diff_seconds(ko1: str, ko2: str) -> int:
    if not ko1 or not ko2:
        return -1
    try:
        dt1 = datetime.fromisoformat(ko1)
        dt2 = datetime.fromisoformat(ko2)
        return abs(int((dt1 - dt2).total_seconds()))
    except Exception:
        return -1


def _apply_sofascore_results(all_fixtures: Dict[str, Dict], ss_data: Dict[str, Dict]) -> int:
    """Önceden çekilmiş Sofascore verisiyle fixture'ları zenginleştirir."""
    if not all_fixtures or not ss_data:
        return 0
    return _enrich_fixtures_with_ss(all_fixtures, ss_data)


def enrich_with_sofascore(all_fixtures: Dict[str, Dict]) -> int:
    if not all_fixtures:
        return 0
    ss_data = _fetch_sofascore_live()
    if not ss_data:
        return 0
    return _enrich_fixtures_with_ss(all_fixtures, ss_data)


def _minute_to_num(m: str) -> int:
    if not m:
        return -1
    s = str(m).strip().upper().replace("'", "")
    if s == 'HT':
        return 45
    if s == 'FT':
        return 90
    if s in ('ET', 'PEN'):
        return 105
    plus = re.match(r'^(\d+)\+(\d+)$', s)
    if plus:
        return int(plus.group(1)) + int(plus.group(2))
    if s.isdigit():
        return int(s)
    return -1


def _enrich_fixtures_with_ss(all_fixtures: Dict[str, Dict], ss_data: Dict[str, Dict]) -> int:
    enriched = 0
    ss_entries = []
    for sk, sv in ss_data.items():
        parts = sk.split('|')
        ss_entries.append((parts[0], parts[1] if len(parts) > 1 else '', sk))
    matched_ss_keys = set()
    bw_miss_count = 0
    for h, fix in all_fixtures.items():
        arb_home = _normalize_team(fix.get('home_team', ''))
        arb_away = _normalize_team(fix.get('away_team', ''))
        if not arb_home or not arb_away:
            continue
        bw_ko = fix.get('kickoff_utc', '')
        bw_league = fix.get('league', '')
        bw_league_norm = _normalize_team(bw_league) if bw_league else ''
        best_combined = 0.0
        best_key = None
        best_ko_diff = -1
        best_league_sc = 0.0
        top_candidates = []
        for ss_h, ss_a, ss_full_key in ss_entries:
            h_score = _team_match_score(arb_home, ss_h)
            a_score = _team_match_score(arb_away, ss_a)
            combined = (h_score + a_score) / 2
            ssd_tmp = ss_data[ss_full_key]
            ss_ko = ssd_tmp.get('kickoff_utc', '')
            ko_diff = _kickoff_diff_seconds(bw_ko, ss_ko)
            ss_league = ssd_tmp.get('league', '')
            ss_league_norm = _normalize_team(ss_league) if ss_league else ''
            league_sc = _team_match_score(bw_league_norm, ss_league_norm) if bw_league_norm and ss_league_norm else -1.0
            if combined > 0.20:
                top_candidates.append((combined, h_score, a_score, ss_full_key,
                                       ssd_tmp.get('home', ''), ssd_tmp.get('away', ''),
                                       ko_diff, league_sc, ss_league[:25]))
            if h_score < 0.40 or a_score < 0.40:
                continue
            if combined < 0.50:
                continue
            if ko_diff >= 0 and ko_diff > 300:
                continue
            if league_sc >= 0 and league_sc < 0.50:
                continue
            if combined > best_combined:
                best_combined = combined
                best_key = ss_full_key
                best_ko_diff = ko_diff
                best_league_sc = league_sc
        top_candidates.sort(key=lambda x: x[0], reverse=True)
        top3 = top_candidates[:3]
        raw_home = fix.get('home_team', '?')[:25]
        raw_away = fix.get('away_team', '?')[:25]
        if best_key and best_combined >= 0.50:
            ssd = ss_data[best_key]
            arb_min_num = _minute_to_num(fix.get('minute', ''))
            ss_min_num = _minute_to_num(ssd.get('minute', ''))
            if arb_min_num >= 0 and ss_min_num >= 0 and abs(arb_min_num - ss_min_num) > 15:
                log(f"  [MATCH-DBG] BW: \"{raw_home}\" vs \"{raw_away}\" → SKIP dk farkı: arb={arb_min_num} ss={ss_min_num} avg={best_combined:.2f} ko_diff={best_ko_diff}s lig={best_league_sc:.2f}")
                continue
            if ssd['score']:
                fix['score'] = ssd['score']
            ss_min = ssd['minute']
            if ss_min:
                fix['minute'] = ss_min
            if ss_min == 'FT':
                fix['status'] = 'ft'
            if ssd.get('kickoff_utc'):
                fix['kickoff_utc'] = ssd['kickoff_utc']
            matched_ss_keys.add(best_key)
            enriched += 1
        else:
            bw_miss_count += 1
            log(f"  [MATCH-DBG] BW: \"{raw_home}\" vs \"{raw_away}\" lig=\"{bw_league[:30]}\" ko={bw_ko[-8:]}")
            if not top3:
                log(f"  [MATCH-DBG]   → Eşleşme YOK — hiç aday yok")
            else:
                for i, (comb, hs, as_, sk, sh, sa, kd, lsc, sl) in enumerate(top3):
                    fail_reason = []
                    if hs < 0.40:
                        fail_reason.append(f"h<0.40")
                    if as_ < 0.40:
                        fail_reason.append(f"a<0.40")
                    if comb < 0.50:
                        fail_reason.append(f"avg<0.50")
                    if kd >= 0 and kd > 300:
                        fail_reason.append(f"ko>{kd}s")
                    elif kd < 0:
                        fail_reason.append(f"ko=?")
                    if lsc >= 0 and lsc < 0.50:
                        fail_reason.append(f"lig={lsc:.2f}<0.50")
                    elif lsc < 0:
                        fail_reason.append(f"lig=?")
                    reason_str = ', '.join(fail_reason) if fail_reason else "OK"
                    log(f"  [MATCH-DBG]   Aday{i+1}: \"{sh[:20]}\" vs \"{sa[:20]}\" h={hs:.2f} a={as_:.2f} avg={comb:.2f} ko_diff={kd}s lig={lsc:.2f}(\"{sl[:20]}\") — {reason_str}")
                log(f"  [MATCH-DBG]   → Eşleşme YOK (en iyi avg={best_combined:.2f})")
    ss_only_count = 0
    for sk, sv in ss_data.items():
        if sk not in matched_ss_keys:
            ss_only_count += 1
            ss_home = sv.get('home', '?')[:25]
            ss_away = sv.get('away', '?')[:25]
            ss_min = sv.get('minute', '?')
            ss_lg = sv.get('league', '?')[:25]
            log(f"  [MATCH-DBG] SS-ONLY: \"{ss_home}\" vs \"{ss_away}\" dk={ss_min} lig=\"{ss_lg}\"")
    log(f"  [MATCH ÖZET] BW: {len(all_fixtures)} | SS: {len(ss_data)} | Eşleşen: {enriched} | BW-miss: {bw_miss_count} | SS-only: {ss_only_count}")
    return enriched


def _fetch_sofascore_finished_events() -> Dict[str, str]:
    """Sofascore'dan bugün (ve dün gece yarısı) biten tüm maçların skorlarını al."""
    ss_finished = {}
    now_utc = datetime.now(timezone.utc)
    dates = [now_utc.strftime('%Y-%m-%d')]
    yesterday = (now_utc - timedelta(hours=6)).strftime('%Y-%m-%d')
    if yesterday != dates[0]:
        dates.append(yesterday)
    for d in dates:
        try:
            resp = requests.get(
                f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{d}",
                headers=SOFASCORE_HEADERS, timeout=15
            )
            if resp.status_code != 200:
                continue
            for ev in resp.json().get('events', []):
                st = ev.get('status', {})
                if st.get('type') != 'finished':
                    continue
                home = ev.get('homeTeam', {}).get('name', '')
                away = ev.get('awayTeam', {}).get('name', '')
                hs = ev.get('homeScore', {}).get('current', '')
                aws = ev.get('awayScore', {}).get('current', '')
                if home and away and hs != '' and aws != '':
                    key = _normalize_team(home) + '|' + _normalize_team(away)
                    ss_finished[key] = f"{hs}-{aws}"
        except Exception:
            pass
    return ss_finished


def _fetch_final_scores(writer, stale_hashes: List[str]) -> Dict[str, str]:
    """Stale maçların Sofascore'dan son skorlarını al."""
    try:
        fixtures = writer.get_fixtures_by_hashes(stale_hashes)
        if not fixtures:
            return {}
        ss_finished = _fetch_sofascore_finished_events()
        if not ss_finished:
            log(f"  [FINAL-DBG] Sofascore'dan biten maç verisi alınamadı")
            return {}
        final_scores = {}
        for fix in fixtures:
            h = fix['match_id_hash']
            raw_home = fix.get('home_team', '?')[:25]
            raw_away = fix.get('away_team', '?')[:25]
            arb_home = _normalize_team(fix.get('home_team', ''))
            arb_away = _normalize_team(fix.get('away_team', ''))
            best_score = ''
            best_combined = 0.0
            best_ss_key = ''
            for ss_key, score in ss_finished.items():
                ss_h, ss_a = ss_key.split('|', 1)
                h_s = _team_match_score(arb_home, ss_h)
                a_s = _team_match_score(arb_away, ss_a)
                if h_s < 0.55 or a_s < 0.55:
                    continue
                comb = (h_s + a_s) / 2
                if comb > best_combined:
                    best_combined = comb
                    best_score = score
                    best_ss_key = ss_key
            if best_combined >= 0.70 and best_score:
                final_scores[h] = best_score
                log(f"  [FINAL-DBG] \"{raw_home}\" vs \"{raw_away}\" → SS skor: {best_score} (avg={best_combined:.2f})")
            else:
                log(f"  [FINAL-DBG] \"{raw_home}\" vs \"{raw_away}\" → SS skor bulunamadı (en iyi avg={best_combined:.2f})")
        return final_scores
    except Exception as e:
        log(f"  [Final Scores] Hata: {e}")
        return {}


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
    """Betwatch'ın utc=3 parametresiyle döndürdüğü kickoff zamanını gerçek UTC'ye çevirir."""
    if not ce_val:
        return fallback
    try:
        if ce_val.endswith('Z'):
            tr_time = datetime.fromisoformat(ce_val.replace('Z', '+00:00'))
            real_utc = tr_time - timedelta(hours=3)
            return real_utc.strftime('%Y-%m-%dT%H:%M:%S+00:00')
        dt = datetime.fromisoformat(ce_val)
        if dt.tzinfo is None:
            real_utc = dt - timedelta(hours=3)
            return real_utc.strftime('%Y-%m-%dT%H:%M:%S+00:00')
        return ce_val
    except Exception:
        return fallback


def _fetch_sofascore_data() -> Dict[str, Dict]:
    """Sofascore canlı verilerini çeker (thread içinde çalışır)."""
    return _fetch_sofascore_live()


def _get_betwatch_date() -> str:
    """Betwatch utc=3 parametresi kullandığı için tarihi UTC+3 olarak hesapla."""
    utc3_now = datetime.now(timezone.utc) + timedelta(hours=3)
    return utc3_now.strftime('%Y-%m-%d')


def _fetch_betwatch_money() -> list:
    """Betwatch getMoney: Betfair exchange oranları + seçenek bazında para (canlı)."""
    try:
        today = _get_betwatch_date()
        params = {
            "live_only": "true",
            "prematch_only": "false",
            "finished_only": "false",
            "favorite_only": "false",
            "utc": "3",
            "step": "1",
            "date": today,
            "order_by_time": "false",
            "not_countries": "",
            "not_leagues": "",
        }
        resp = requests.get(BETWATCH_GETMONEY_URL, params=params,
                            headers=BETWATCH_HEADERS, timeout=30, verify=SSL_VERIFY)
        if resp.status_code != 200:
            log(f"  [Betwatch Money] HTTP {resp.status_code}")
            return []
        data = resp.json()
        entries = data.get('data', [])
        log(f"  [Betwatch Money] {len(entries)} market entry çekildi")
        return entries
    except Exception as e:
        log(f"  [Betwatch Money] Hata: {e}")
        return []


def _fetch_betwatch_main() -> list:
    """Betwatch getMain: tüm canlı maçların 1X2 oranları (backup)."""
    try:
        today = _get_betwatch_date()
        params = {
            "live_only": "true",
            "prematch_only": "false",
            "finished_only": "false",
            "favorite_only": "false",
            "utc": "3",
            "step": "1",
            "date": today,
            "order_by_time": "false",
            "not_countries": "",
            "not_leagues": "",
        }
        resp = requests.get(BETWATCH_GETMAIN_URL, params=params,
                            headers=BETWATCH_HEADERS, timeout=30, verify=SSL_VERIFY)
        if resp.status_code != 200:
            log(f"  [Betwatch Main] HTTP {resp.status_code}")
            return []
        data = resp.json()
        entries = data.get('data', [])
        log(f"  [Betwatch Main] {len(entries)} canlı maç çekildi")
        return entries
    except Exception as e:
        log(f"  [Betwatch Main] Hata: {e}")
        return []


def _fetch_betwatch_data() -> dict:
    """Betwatch getMoney + getMain paralel çeker."""
    result = {"money": [], "main": [], "errors": [], "fetch_ok": False}
    try:
        with ThreadPoolExecutor(max_workers=2) as ex:
            money_f = ex.submit(_fetch_betwatch_money)
            main_f = ex.submit(_fetch_betwatch_main)
            result["money"] = money_f.result(timeout=45)
            result["main"] = main_f.result(timeout=45)
        if result["main"] or result["money"]:
            result["fetch_ok"] = True
    except Exception as e:
        result["errors"].append(str(e))
    return result


def _process_betwatch_data(bw_result: dict, now_utc: str, today_str: str) -> tuple:
    """Betwatch verilerini fixtures + snapshots'a dönüştürür.
    getMain → tüm maçların fixture + 1X2 oranları (para bilgisi yok)
    getMoney → para/volume bilgisi + tüm marketler (1X2 + OU)
    """
    all_fixtures = {}
    all_snapshots = []
    match_count_1x2 = 0
    match_count_ou = 0
    seen_1x2_events = set()

    main_entries = bw_result.get("main", [])
    for entry in main_entries:
        home = entry.get('htn', '')
        away = entry.get('atn', '')
        league = entry.get('ln', '')
        event_id = entry.get('e', 0)
        if not home or not away:
            continue
        h = make_live_match_hash(home, away, league)
        ko_utc = _betwatch_ko_to_utc(entry.get('ce', ''), '')
        all_fixtures[h] = {
            "match_id_hash": h,
            "home_team": home[:100],
            "away_team": away[:100],
            "league": league[:150],
            "score": "",
            "minute": "",
            "status": "live",
            "kickoff_utc": ko_utc,
            "fixture_date": today_str,
            "updated_at": now_utc,
        }
        sels = entry.get('i', [])
        if len(sels) >= 3:
            odds1 = sels[0][1] if len(sels[0]) > 1 else None
            oddsx = sels[1][1] if len(sels[1]) > 1 else None
            odds2 = sels[2][1] if len(sels[2]) > 1 else None
            for sel, odds in [('1', odds1), ('X', oddsx), ('2', odds2)]:
                all_snapshots.append({
                    "match_id_hash": h,
                    "snapshot_at": now_utc,
                    "market": "1X2",
                    "selection": sel,
                    "odds": odds,
                    "share": 0.0,
                    "volume": 0.0,
                    "ou_line": None,
                })
            seen_1x2_events.add(event_id)
            match_count_1x2 += 1

    money_entries = bw_result.get("money", [])
    money_by_event_market = {}
    for entry in money_entries:
        event_id = entry.get('e', 0)
        market_name = entry.get('n', '')
        money_by_event_market[(event_id, market_name)] = entry

    for (event_id, market_name), entry in money_by_event_market.items():
        home = entry.get('htn', '')
        away = entry.get('atn', '')
        league = entry.get('ln', '')
        if not home or not away:
            continue
        h = make_live_match_hash(home, away, league)
        if h not in all_fixtures:
            ko_utc = _betwatch_ko_to_utc(entry.get('ce', ''), '')
            all_fixtures[h] = {
                "match_id_hash": h,
                "home_team": home[:100],
                "away_team": away[:100],
                "league": league[:150],
                "score": "",
                "minute": "",
                "status": "live",
                "kickoff_utc": ko_utc,
                "fixture_date": today_str,
                "updated_at": now_utc,
            }
        sels = entry.get('i', [])
        total_volume = entry.get('v', 0) or 0

        if market_name == "Match Odds":
            if event_id in seen_1x2_events:
                snap_map = {}
                for snap in all_snapshots:
                    if snap['match_id_hash'] == h and snap['market'] == '1X2':
                        snap_map[snap['selection']] = snap
                for sel_data in sels:
                    if len(sel_data) < 4:
                        continue
                    sel_name = sel_data[0]
                    sel_money = sel_data[1] or 0
                    back_odds = sel_data[2]
                    share = (sel_money / total_volume * 100) if total_volume > 0 else 0
                    if sel_name in snap_map:
                        snap_map[sel_name]['odds'] = back_odds
                        snap_map[sel_name]['share'] = round(share, 1)
                        snap_map[sel_name]['volume'] = sel_money
            else:
                for sel_data in sels:
                    if len(sel_data) < 4:
                        continue
                    sel_name = sel_data[0]
                    sel_money = sel_data[1] or 0
                    back_odds = sel_data[2]
                    share = (sel_money / total_volume * 100) if total_volume > 0 else 0
                    all_snapshots.append({
                        "match_id_hash": h,
                        "snapshot_at": now_utc,
                        "market": "1X2",
                        "selection": sel_name,
                        "odds": back_odds,
                        "share": round(share, 1),
                        "volume": sel_money,
                        "ou_line": None,
                    })
                seen_1x2_events.add(event_id)
                match_count_1x2 += 1

        elif market_name.startswith("Over/Under"):
            line_match = re.search(r'([\d.]+)', market_name.replace("Over/Under", ""))
            line = line_match.group(1) if line_match else ""
            match_count_ou += 1
            for sel_data in sels:
                if len(sel_data) < 4:
                    continue
                sel_name = sel_data[0]
                sel_money = sel_data[1] or 0
                back_odds = sel_data[2]
                sel_code = "U" if sel_name == "Under" else "O"
                share = (sel_money / total_volume * 100) if total_volume > 0 else 0
                all_snapshots.append({
                    "match_id_hash": h,
                    "snapshot_at": now_utc,
                    "market": "OU",
                    "selection": sel_code,
                    "odds": back_odds,
                    "share": round(share, 1),
                    "volume": sel_money,
                    "ou_line": line,
                })

    log(f"  [Betwatch] 1X2: {match_count_1x2} maç, OU: {match_count_ou} market")
    return all_fixtures, all_snapshots, match_count_1x2 + match_count_ou


def run_live_scrape(writer: LiveSupabaseWriter) -> int:
    """Betwatch'dan oranları + para bilgisini çeker, Sofascore'dan skor/dakika ekler.
    Betwatch ve Sofascore paralel olarak çekilir."""
    log("CANLI SCRAPE BAŞLIYOR...")
    now_utc = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+00:00')
    today_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    log("  Betwatch + Sofascore paralel çekiliyor...")
    with ThreadPoolExecutor(max_workers=2) as executor:
        bw_future = executor.submit(_fetch_betwatch_data)
        sofa_future = executor.submit(_fetch_sofascore_data)
        bw_result = bw_future.result(timeout=60)
        sofa_result = sofa_future.result(timeout=60)

    for err in bw_result.get("errors", []):
        log(f"  [HATA] Betwatch: {err}")

    all_fixtures, all_snapshots, total_matches = _process_betwatch_data(bw_result, now_utc, today_str)

    if all_fixtures:
        _apply_sofascore_results(all_fixtures, sofa_result)
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
            log(f"  [AUTO-FT SKIP] {auto_ft_skipped} maç 120+ dk ama Sofascore'da hâlâ aktif")
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
        log(f"  [DEBUG] Betwatch vs Sofascore karşılaştırma:")
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
        ss_protected = []
        existing_fixtures_data = {}
        if existing_live_info:
            db_fixes = writer.get_fixtures_by_hashes(list(existing_live_info.keys()))
            for df in db_fixes:
                existing_fixtures_data[df['match_id_hash']] = df
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
            db_fix = existing_fixtures_data.get(h, {})
            db_home = db_fix.get('home_team', '')
            db_away = db_fix.get('away_team', '')
            if db_home and db_away and sofa_result:
                norm_h = _normalize_team(db_home)
                norm_a = _normalize_team(db_away)
                db_league = db_fix.get('league', '')
                db_league_norm = _normalize_team(db_league) if db_league else ''
                db_ko = db_fix.get('kickoff_utc', '')
                best_score = 0
                best_minute = ''
                best_ss_home = ''
                best_ss_away = ''
                for sk, sv in sofa_result.items():
                    parts = sk.split('|')
                    ss_h = parts[0]
                    ss_a = parts[1] if len(parts) > 1 else ''
                    h_sc = _team_match_score(norm_h, ss_h)
                    a_sc = _team_match_score(norm_a, ss_a)
                    if h_sc < 0.40 or a_sc < 0.40:
                        continue
                    combined = (h_sc + a_sc) / 2
                    if combined < 0.50:
                        continue
                    ss_ko = sv.get('kickoff_utc', '')
                    ko_diff = _kickoff_diff_seconds(db_ko, ss_ko)
                    if ko_diff >= 0 and ko_diff > 300:
                        continue
                    ss_league = sv.get('league', '')
                    ss_league_norm = _normalize_team(ss_league) if ss_league else ''
                    league_sc = _team_match_score(db_league_norm, ss_league_norm) if db_league_norm and ss_league_norm else -1.0
                    if league_sc >= 0 and league_sc < 0.50:
                        continue
                    if combined > best_score:
                        best_score = combined
                        best_minute = sv.get('minute', '')
                        best_ss_home = sv.get('home', '')[:20]
                        best_ss_away = sv.get('away', '')[:20]
                if best_score > 0 and best_minute and best_minute not in ('FT', 'AET', 'PEN'):
                    ss_protected.append(h)
                    log(f"  [SS-KORUMA-DBG] \"{db_home[:20]}\" vs \"{db_away[:20]}\" → SS: \"{best_ss_home}\" vs \"{best_ss_away}\" avg={best_score:.2f} dk={best_minute} — KORUMA")
                    continue
                else:
                    ss_reason = f"avg={best_score:.2f} dk={best_minute}" if best_score > 0 else "SS eşleşme yok"
                    log(f"  [SS-KORUMA-DBG] \"{db_home[:20]}\" vs \"{db_away[:20]}\" → {ss_reason} — STALE")
            else:
                log(f"  [SS-KORUMA-DBG] hash={h} → takım bilgisi yok veya SS verisi yok — STALE")
            stale_hashes.append(h)
        if ss_protected:
            log(f"  [SS-KORUMA] {len(ss_protected)} maç Sofascore'da hâlâ devam ediyor, FT yapılmadı")
        if skipped_early:
            log(f"  [KORUMA] {len(skipped_early)} maç erken FT'den korundu (89 dk dolmadı):")
            for h, em in skipped_early:
                info = existing_live_info.get(h, '')
                log(f"    hash={h} kickoff={info} elapsed={em:.0f}dk")
        if stale_hashes:
            final_scores = _fetch_final_scores(writer, stale_hashes)
            marked = writer.mark_fixtures_finished(stale_hashes, final_scores)
            score_count = sum(1 for s in final_scores.values() if s)
            log(f"  [MS] {marked}/{len(stale_hashes)} biten maç FT olarak işaretlendi ({score_count} skor güncellendi)")
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
