#!/usr/bin/env python3
"""
Matchbook Exchange Scraper
Login-free API'den futbol odds + volume verisi ceker.
9 dakikada bir calisir, scheduled_scraper ile paralel.
Alarm engine'e dahil OLMAZ - sadece gorsel karsilastirma.
"""
import os
import sys
import time
import re
import hashlib
import traceback
import httpx
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any

sys.path.insert(0, os.path.dirname(__file__))
from core.hash_utils import normalize_field, make_match_id_hash

MATCHBOOK_API = "https://api.matchbook.com/edge/rest"
SPORT_ID_FOOTBALL = 15
PER_PAGE = 20
MAX_PAGES = 50
SCRAPE_INTERVAL = 9 * 60

_prev_snapshots: Dict[str, Dict] = {}

def get_supabase_creds():
    try:
        from services import embedded_credentials
        url = getattr(embedded_credentials, 'SUPABASE_URL', '')
        key = getattr(embedded_credentials, 'SUPABASE_KEY', '')
        if url and key:
            return url, key
    except:
        pass
    url = os.environ.get('SUPABASE_URL', '')
    key = os.environ.get('SUPABASE_ANON_KEY', '') or os.environ.get('SUPABASE_KEY', '')
    return url, key


class MatchbookClient:
    def __init__(self):
        self.client = httpx.Client(
            timeout=httpx.Timeout(30, connect=15),
            headers={"Accept": "application/json"},
            follow_redirects=True
        )
    
    def fetch_events(self) -> List[Dict]:
        all_events = []
        offset = 0
        for page in range(MAX_PAGES):
            url = (
                f"{MATCHBOOK_API}/events"
                f"?sport-ids={SPORT_ID_FOOTBALL}"
                f"&status=open"
                f"&per-page={PER_PAGE}"
                f"&offset={offset}"
                f"&include-markets=true"
                f"&include-runners=true"
                f"&include-prices=true"
            )
            try:
                resp = self.client.get(url)
                if resp.status_code != 200:
                    print(f"[MB] Page {page+1} HTTP {resp.status_code}")
                    break
                data = resp.json()
                events = data.get('events', [])
                if not events:
                    break
                all_events.extend(events)
                total = data.get('total', 0)
                offset += len(events)
                if offset >= total:
                    break
                time.sleep(0.3)
            except Exception as e:
                print(f"[MB] Page {page+1} error: {e}")
                break
        return all_events
    
    def close(self):
        try:
            self.client.close()
        except:
            pass


def extract_league(event: Dict) -> str:
    meta_tags = event.get('meta-tags', event.get('meta_tags', []))
    for tag in meta_tags:
        if isinstance(tag, dict) and tag.get('type') == 'COMPETITION':
            return tag.get('name', '')
    if isinstance(meta_tags, list) and len(meta_tags) > 0:
        for tag in meta_tags:
            if isinstance(tag, dict) and 'name' in tag:
                name = tag['name']
                if name not in ('Football', 'Soccer', 'Sports'):
                    return name
    return ''


def parse_event(event: Dict) -> Optional[Dict]:
    name = event.get('name', '')
    if ' vs ' not in name and ' v ' not in name:
        return None
    
    if ' vs ' in name:
        parts = name.split(' vs ', 1)
    else:
        parts = name.split(' v ', 1)
    
    if len(parts) != 2:
        return None
    
    home = parts[0].strip()
    away = parts[1].strip()
    
    if not home or not away:
        return None
    
    league = extract_league(event)
    
    start_str = event.get('start', '')
    kickoff = None
    if start_str:
        try:
            if start_str.endswith('Z'):
                kickoff = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
            else:
                kickoff = datetime.fromisoformat(start_str)
        except:
            pass
    
    markets = event.get('markets', [])
    market_data = {}
    
    for mkt in markets:
        mkt_name = mkt.get('name', '').lower()
        mkt_type = mkt.get('market-type', mkt.get('type', '')).lower()
        runners = mkt.get('runners', [])
        
        if 'match odds' in mkt_name or 'match-odds' in mkt_type or mkt_type == 'match_odds':
            market_data['1x2'] = _parse_1x2_runners(runners)
        elif 'over/under' in mkt_name or 'over-under' in mkt_type or 'total' in mkt_name:
            handicap = mkt.get('handicap', 0)
            if handicap == 2.5 or '2.5' in str(mkt_name):
                market_data['ou25'] = _parse_ou_runners(runners)
        elif 'both teams to score' in mkt_name or 'btts' in mkt_type:
            market_data['btts'] = _parse_btts_runners(runners)
    
    if not market_data:
        return None
    
    return {
        'event_id': event.get('id'),
        'home': home,
        'away': away,
        'league': league,
        'kickoff': kickoff,
        'markets': market_data,
        'volume_matched': event.get('volume', 0)
    }


def _get_best_back_price(runner: Dict) -> Tuple[Optional[float], float]:
    prices = runner.get('prices', [])
    best_odds = None
    total_available = 0.0
    
    for p in prices:
        side = p.get('side', '').lower()
        if side == 'back':
            odds = p.get('odds', p.get('decimal-odds'))
            avail = p.get('available-amount', 0)
            if odds is not None:
                if best_odds is None or odds > best_odds:
                    best_odds = odds
                total_available += avail
    
    return best_odds, total_available


def _parse_1x2_runners(runners: List[Dict]) -> Dict:
    result = {'odds1': None, 'oddsx': None, 'odds2': None, 'vol1': 0, 'volx': 0, 'vol2': 0}
    
    home_set = False
    away_set = False
    
    for r in runners:
        name = r.get('name', '').lower().strip()
        odds, vol = _get_best_back_price(r)
        matched = r.get('volume', 0) or 0
        
        if name == 'draw':
            result['oddsx'] = odds
            result['volx'] = matched or vol
        elif name == 'home' or (r.get('event-participant-id') and not home_set and name != 'away'):
            result['odds1'] = odds
            result['vol1'] = matched or vol
            home_set = True
        elif name == 'away' or (r.get('event-participant-id') and home_set and not away_set):
            result['odds2'] = odds
            result['vol2'] = matched or vol
            away_set = True
    
    if result['odds1'] is None and len(runners) >= 3:
        for i, r in enumerate(runners):
            odds, vol = _get_best_back_price(r)
            matched = r.get('volume', 0) or 0
            if i == 0:
                result['odds1'] = odds
                result['vol1'] = matched or vol
            elif i == 1:
                result['oddsx'] = odds
                result['volx'] = matched or vol
            elif i == 2:
                result['odds2'] = odds
                result['vol2'] = matched or vol
    
    return result


def _parse_ou_runners(runners: List[Dict]) -> Dict:
    result = {'over': None, 'under': None, 'vol_over': 0, 'vol_under': 0}
    
    for r in runners:
        name = r.get('name', '').lower()
        odds, vol = _get_best_back_price(r)
        matched = r.get('volume', 0) or 0
        
        if 'over' in name:
            result['over'] = odds
            result['vol_over'] = matched or vol
        elif 'under' in name:
            result['under'] = odds
            result['vol_under'] = matched or vol
    
    return result


def _parse_btts_runners(runners: List[Dict]) -> Dict:
    result = {'yes': None, 'no': None, 'vol_yes': 0, 'vol_no': 0}
    
    for r in runners:
        name = r.get('name', '').lower()
        odds, vol = _get_best_back_price(r)
        matched = r.get('volume', 0) or 0
        
        if 'yes' in name:
            result['yes'] = odds
            result['vol_yes'] = matched or vol
        elif 'no' in name:
            result['no'] = odds
            result['vol_no'] = matched or vol
    
    return result


def normalize_league_name(name: str) -> str:
    if not name:
        return ''
    n = name.lower().strip()
    n = re.sub(r'[^a-z0-9\s]', '', n)
    n = ' '.join(n.split())
    remove_words = ['football', 'soccer', 'league', 'division']
    words = n.split()
    words = [w for w in words if w not in remove_words]
    return ' '.join(words)


def league_similarity(mb_league: str, arb_league: str) -> float:
    mb_norm = normalize_league_name(mb_league)
    arb_norm = normalize_league_name(arb_league)
    
    if mb_norm == arb_norm:
        return 1.0
    
    mb_words = set(mb_norm.split())
    arb_words = set(arb_norm.split())
    
    if not mb_words or not arb_words:
        return 0.0
    
    common = mb_words & arb_words
    if not common:
        return 0.0
    
    return len(common) / max(len(mb_words), len(arb_words))


def team_similarity(mb_team: str, arb_team: str) -> float:
    mb_n = normalize_field(mb_team)
    arb_n = normalize_field(arb_team)
    
    if mb_n == arb_n:
        return 1.0
    
    if mb_n.startswith(arb_n) or arb_n.startswith(mb_n):
        shorter = min(len(mb_n), len(arb_n))
        longer = max(len(mb_n), len(arb_n))
        if shorter >= 4 and shorter / longer >= 0.5:
            return 0.85
    
    mb_words = set(mb_n.split())
    arb_words = set(arb_n.split())
    
    if not mb_words or not arb_words:
        return 0.0
    
    common = mb_words & arb_words
    if not common:
        return 0.0
    
    return len(common) / max(len(mb_words), len(arb_words))


class MatchMatcher:
    def __init__(self, supabase_url: str, supabase_key: str):
        self.url = supabase_url
        self.key = supabase_key
        self.headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json"
        }
        self.client = httpx.Client(timeout=15)
        self._arb_fixtures_cache = None
        self._league_map_cache = {}
    
    def _rest_url(self, table: str) -> str:
        return f"{self.url}/rest/v1/{table}"
    
    def load_arbworld_fixtures(self):
        try:
            from urllib.parse import quote
            now = datetime.now(timezone.utc)
            start = quote((now - timedelta(hours=6)).isoformat())
            end = quote((now + timedelta(days=3)).isoformat())
            
            url = (
                f"{self._rest_url('fixtures')}?select=home_team,away_team,league,kickoff_utc,match_id_hash"
                f"&kickoff_utc=gte.{start}&kickoff_utc=lte.{end}"
                f"&limit=1000"
            )
            resp = self.client.get(url, headers=self.headers)
            if resp.status_code == 200:
                self._arb_fixtures_cache = resp.json()
                print(f"[Match] Loaded {len(self._arb_fixtures_cache)} Arbworld fixtures")
            else:
                print(f"[Match] Failed to load fixtures: HTTP {resp.status_code}")
                self._arb_fixtures_cache = []
        except Exception as e:
            print(f"[Match] Error loading fixtures: {e}")
            self._arb_fixtures_cache = []
    
    def load_league_map(self):
        try:
            url = f"{self._rest_url('matchbook_league_map')}?select=matchbook_league,arbworld_league&limit=500"
            resp = self.client.get(url, headers=self.headers)
            if resp.status_code == 200:
                rows = resp.json()
                self._league_map_cache = {r['matchbook_league']: r['arbworld_league'] for r in rows if r.get('arbworld_league')}
                print(f"[Match] Loaded {len(self._league_map_cache)} league mappings")
        except Exception as e:
            print(f"[Match] Error loading league map: {e}")
    
    def save_league_mapping(self, mb_league: str, arb_league: str, auto: bool = True):
        try:
            data = {
                "matchbook_league": mb_league,
                "arbworld_league": arb_league,
                "auto_matched": auto
            }
            headers = {**self.headers, "Prefer": "resolution=merge-duplicates,return=representation"}
            resp = self.client.post(self._rest_url('matchbook_league_map'), json=data, headers=headers)
            if resp.status_code in [200, 201]:
                self._league_map_cache[mb_league] = arb_league
        except:
            pass
    
    def find_arbworld_match(self, mb_event: Dict) -> Optional[str]:
        if not self._arb_fixtures_cache:
            return None
        
        mb_league = mb_event.get('league', '')
        mb_home = mb_event.get('home', '')
        mb_away = mb_event.get('away', '')
        mb_kickoff = mb_event.get('kickoff')
        
        if mb_league in self._league_map_cache:
            mapped_league = self._league_map_cache[mb_league]
        else:
            mapped_league = None
        
        candidates = []
        
        for fix in self._arb_fixtures_cache:
            arb_league = fix.get('league', '')
            
            if mapped_league:
                if normalize_league_name(arb_league) != normalize_league_name(mapped_league):
                    continue
            else:
                sim = league_similarity(mb_league, arb_league)
                if sim < 0.4:
                    continue
                if sim >= 0.6 and not mapped_league:
                    self.save_league_mapping(mb_league, arb_league)
            
            if mb_kickoff:
                arb_kickoff_str = fix.get('kickoff_utc', '')
                if arb_kickoff_str:
                    try:
                        if arb_kickoff_str.endswith('Z'):
                            arb_kickoff = datetime.fromisoformat(arb_kickoff_str.replace('Z', '+00:00'))
                        elif '+' in arb_kickoff_str or arb_kickoff_str.endswith('Z'):
                            arb_kickoff = datetime.fromisoformat(arb_kickoff_str)
                        else:
                            arb_kickoff = datetime.fromisoformat(arb_kickoff_str + '+00:00')
                        
                        time_diff = abs((mb_kickoff - arb_kickoff).total_seconds())
                        if time_diff > 1800:
                            continue
                    except:
                        pass
            
            arb_home = fix.get('home_team', '')
            arb_away = fix.get('away_team', '')
            
            home_sim = team_similarity(mb_home, arb_home)
            away_sim = team_similarity(mb_away, arb_away)
            
            avg_sim = (home_sim + away_sim) / 2
            
            if avg_sim >= 0.5:
                candidates.append((avg_sim, fix))
        
        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            best_sim, best_fix = candidates[0]
            if best_sim >= 0.5:
                return best_fix.get('match_id_hash', '')
        
        return None
    
    def close(self):
        try:
            self.client.close()
        except:
            pass


class MatchbookWriter:
    def __init__(self, supabase_url: str, supabase_key: str):
        self.url = supabase_url
        self.key = supabase_key
        self.headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
        self.client = httpx.Client(timeout=15)
    
    def _rest_url(self, table: str) -> str:
        return f"{self.url}/rest/v1/{table}"
    
    def upsert_fixture(self, event: Dict, arbworld_hash: Optional[str] = None):
        try:
            mb_hash = make_match_id_hash(event['home'], event['away'], event.get('league', ''))
            
            data = {
                "event_id": event.get('event_id'),
                "home_team": event['home'],
                "away_team": event['away'],
                "league": event.get('league', ''),
                "match_id_hash": mb_hash,
                "last_scraped": datetime.now(timezone.utc).isoformat()
            }
            
            if event.get('kickoff'):
                data["kickoff_utc"] = event['kickoff'].isoformat()
            
            if arbworld_hash:
                data["arbworld_hash"] = arbworld_hash
            
            headers = {**self.headers, "Prefer": "resolution=merge-duplicates,return=representation"}
            resp = self.client.post(self._rest_url('matchbook_fixtures'), json=data, headers=headers)
            
            return mb_hash
        except Exception as e:
            print(f"[MB-W] Fixture upsert error: {e}")
            return make_match_id_hash(event['home'], event['away'], event.get('league', ''))
    
    def write_1x2(self, event: Dict, mb_hash: str, arb_hash: Optional[str]):
        mkt = event['markets'].get('1x2')
        if not mkt or mkt.get('odds1') is None:
            return
        
        cur_vol1 = mkt.get('vol1', 0) or 0
        cur_volx = mkt.get('volx', 0) or 0
        cur_vol2 = mkt.get('vol2', 0) or 0
        
        prev_key = f"{mb_hash}_1x2"
        prev = _prev_snapshots.get(prev_key, {})
        
        delta1 = max(0, cur_vol1 - (prev.get('raw_vol1', 0) or 0)) if prev else cur_vol1
        deltax = max(0, cur_volx - (prev.get('raw_volx', 0) or 0)) if prev else cur_volx
        delta2 = max(0, cur_vol2 - (prev.get('raw_vol2', 0) or 0)) if prev else cur_vol2
        delta_total = delta1 + deltax + delta2
        
        pct1 = pctx = pct2 = ''
        amt1 = amtx = amt2 = ''
        if delta_total > 0:
            pct1 = f"{delta1 / delta_total * 100:.1f}%"
            pctx = f"{deltax / delta_total * 100:.1f}%"
            pct2 = f"{delta2 / delta_total * 100:.1f}%"
            amt1 = f"£{int(delta1):,}"
            amtx = f"£{int(deltax):,}"
            amt2 = f"£{int(delta2):,}"
        
        trend1 = _calc_trend(mkt.get('odds1'), prev.get('odds1'))
        trendx = _calc_trend(mkt.get('oddsx'), prev.get('oddsx'))
        trend2 = _calc_trend(mkt.get('odds2'), prev.get('odds2'))
        
        kickoff_str = ''
        if event.get('kickoff'):
            kickoff_str = event['kickoff'].isoformat()
        
        total_vol = cur_vol1 + cur_volx + cur_vol2
        
        row = {
            "home": event['home'],
            "away": event['away'],
            "league": event.get('league', ''),
            "date": kickoff_str,
            "match_id_hash": mb_hash,
            "odds1": mkt.get('odds1'),
            "oddsx": mkt.get('oddsx'),
            "odds2": mkt.get('odds2'),
            "pct1": pct1, "pctx": pctx, "pct2": pct2,
            "amt1": amt1, "amtx": amtx, "amt2": amt2,
            "volume": f"£{int(total_vol):,}" if total_vol > 0 else '',
            "odds1_prev": str(prev.get('odds1', '')) if prev.get('odds1') else '',
            "oddsx_prev": str(prev.get('oddsx', '')) if prev.get('oddsx') else '',
            "odds2_prev": str(prev.get('odds2', '')) if prev.get('odds2') else '',
            "trend1": trend1, "trendx": trendx, "trend2": trend2,
            "scraped_at": datetime.now(timezone.utc).isoformat()
        }
        
        if arb_hash:
            row["arbworld_hash"] = arb_hash
        
        _prev_snapshots[prev_key] = {
            'odds1': mkt.get('odds1'),
            'oddsx': mkt.get('oddsx'),
            'odds2': mkt.get('odds2'),
            'raw_vol1': cur_vol1,
            'raw_volx': cur_volx,
            'raw_vol2': cur_vol2
        }
        
        self._insert('matchbook_1x2_history', row)
    
    def write_ou25(self, event: Dict, mb_hash: str, arb_hash: Optional[str]):
        mkt = event['markets'].get('ou25')
        if not mkt or (mkt.get('over') is None and mkt.get('under') is None):
            return
        
        cur_vol_over = mkt.get('vol_over', 0) or 0
        cur_vol_under = mkt.get('vol_under', 0) or 0
        
        prev_key = f"{mb_hash}_ou25"
        prev = _prev_snapshots.get(prev_key, {})
        
        delta_over = max(0, cur_vol_over - (prev.get('raw_vol_over', 0) or 0)) if prev else cur_vol_over
        delta_under = max(0, cur_vol_under - (prev.get('raw_vol_under', 0) or 0)) if prev else cur_vol_under
        delta_total = delta_over + delta_under
        
        pctover = pctunder = ''
        amtover = amtunder = ''
        if delta_total > 0:
            pctover = f"{delta_over / delta_total * 100:.1f}%"
            pctunder = f"{delta_under / delta_total * 100:.1f}%"
            amtover = f"£{int(delta_over):,}"
            amtunder = f"£{int(delta_under):,}"
        
        trendover = _calc_trend(mkt.get('over'), prev.get('over'))
        trendunder = _calc_trend(mkt.get('under'), prev.get('under'))
        
        kickoff_str = ''
        if event.get('kickoff'):
            kickoff_str = event['kickoff'].isoformat()
        
        total_vol = cur_vol_over + cur_vol_under
        
        row = {
            "home": event['home'],
            "away": event['away'],
            "league": event.get('league', ''),
            "date": kickoff_str,
            "match_id_hash": mb_hash,
            "over": mkt.get('over'),
            "under": mkt.get('under'),
            "line": "2.5",
            "pctover": pctover, "pctunder": pctunder,
            "amtover": amtover, "amtunder": amtunder,
            "volume": f"£{int(total_vol):,}" if total_vol > 0 else '',
            "over_prev": str(prev.get('over', '')) if prev.get('over') else '',
            "under_prev": str(prev.get('under', '')) if prev.get('under') else '',
            "trendover": trendover, "trendunder": trendunder,
            "scraped_at": datetime.now(timezone.utc).isoformat()
        }
        
        if arb_hash:
            row["arbworld_hash"] = arb_hash
        
        _prev_snapshots[prev_key] = {
            'over': mkt.get('over'),
            'under': mkt.get('under'),
            'raw_vol_over': cur_vol_over,
            'raw_vol_under': cur_vol_under
        }
        
        self._insert('matchbook_ou25_history', row)
    
    def write_btts(self, event: Dict, mb_hash: str, arb_hash: Optional[str]):
        mkt = event['markets'].get('btts')
        if not mkt or (mkt.get('yes') is None and mkt.get('no') is None):
            return
        
        cur_vol_yes = mkt.get('vol_yes', 0) or 0
        cur_vol_no = mkt.get('vol_no', 0) or 0
        
        prev_key = f"{mb_hash}_btts"
        prev = _prev_snapshots.get(prev_key, {})
        
        delta_yes = max(0, cur_vol_yes - (prev.get('raw_vol_yes', 0) or 0)) if prev else cur_vol_yes
        delta_no = max(0, cur_vol_no - (prev.get('raw_vol_no', 0) or 0)) if prev else cur_vol_no
        delta_total = delta_yes + delta_no
        
        pctyes = pctno = ''
        amtyes = amtno = ''
        if delta_total > 0:
            pctyes = f"{delta_yes / delta_total * 100:.1f}%"
            pctno = f"{delta_no / delta_total * 100:.1f}%"
            amtyes = f"£{int(delta_yes):,}"
            amtno = f"£{int(delta_no):,}"
        
        trendyes = _calc_trend(mkt.get('yes'), prev.get('yes'))
        trendno = _calc_trend(mkt.get('no'), prev.get('no'))
        
        kickoff_str = ''
        if event.get('kickoff'):
            kickoff_str = event['kickoff'].isoformat()
        
        total_vol = cur_vol_yes + cur_vol_no
        
        row = {
            "home": event['home'],
            "away": event['away'],
            "league": event.get('league', ''),
            "date": kickoff_str,
            "match_id_hash": mb_hash,
            "oddsyes": mkt.get('yes'),
            "oddsno": mkt.get('no'),
            "pctyes": pctyes, "pctno": pctno,
            "amtyes": amtyes, "amtno": amtno,
            "volume": f"£{int(total_vol):,}" if total_vol > 0 else '',
            "oddsyes_prev": str(prev.get('yes', '')) if prev.get('yes') else '',
            "oddsno_prev": str(prev.get('no', '')) if prev.get('no') else '',
            "trendyes": trendyes, "trendno": trendno,
            "scraped_at": datetime.now(timezone.utc).isoformat()
        }
        
        if arb_hash:
            row["arbworld_hash"] = arb_hash
        
        _prev_snapshots[prev_key] = {
            'yes': mkt.get('yes'),
            'no': mkt.get('no'),
            'raw_vol_yes': cur_vol_yes,
            'raw_vol_no': cur_vol_no
        }
        
        self._insert('matchbook_btts_history', row)
    
    def _insert(self, table: str, row: Dict):
        try:
            resp = self.client.post(self._rest_url(table), json=row, headers=self.headers)
            if resp.status_code not in [200, 201]:
                print(f"[MB-W] Insert {table} failed: HTTP {resp.status_code} - {resp.text[:100]}")
        except Exception as e:
            print(f"[MB-W] Insert {table} error: {e}")
    
    def close(self):
        try:
            self.client.close()
        except:
            pass


def _calc_trend(current, previous) -> str:
    if current is None or previous is None:
        return ''
    try:
        c = float(current)
        p = float(previous)
        if c > p:
            return '↑'
        elif c < p:
            return '↓'
        else:
            return '→'
    except:
        return ''


def run_scrape():
    supabase_url, supabase_key = get_supabase_creds()
    if not supabase_url or not supabase_key:
        print("[MB] FATAL: Supabase credentials missing!")
        return 0
    
    print(f"\n{'='*60}")
    print(f"[MB] Matchbook Scrape starting at {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}")
    print(f"{'='*60}")
    
    mb_client = MatchbookClient()
    matcher = MatchMatcher(supabase_url, supabase_key)
    writer = MatchbookWriter(supabase_url, supabase_key)
    
    try:
        matcher.load_arbworld_fixtures()
        matcher.load_league_map()
        
        events = mb_client.fetch_events()
        print(f"[MB] Fetched {len(events)} raw events")
        
        parsed_count = 0
        matched_count = 0
        written_1x2 = 0
        written_ou25 = 0
        written_btts = 0
        unmatched_leagues = set()
        
        now_utc = datetime.now(timezone.utc)
        skipped_live = 0
        
        for event in events:
            parsed = parse_event(event)
            if not parsed:
                continue
            
            if parsed.get('kickoff') and parsed['kickoff'] < now_utc:
                skipped_live += 1
                continue
            
            parsed_count += 1
            
            arb_hash = matcher.find_arbworld_match(parsed)
            if arb_hash:
                matched_count += 1
            else:
                if parsed.get('league'):
                    unmatched_leagues.add(parsed['league'])
            
            mb_hash = writer.upsert_fixture(parsed, arb_hash)
            
            if '1x2' in parsed['markets']:
                writer.write_1x2(parsed, mb_hash, arb_hash)
                written_1x2 += 1
            if 'ou25' in parsed['markets']:
                writer.write_ou25(parsed, mb_hash, arb_hash)
                written_ou25 += 1
            if 'btts' in parsed['markets']:
                writer.write_btts(parsed, mb_hash, arb_hash)
                written_btts += 1
        
        if skipped_live > 0:
            print(f"[MB] Skipped {skipped_live} live/in-play events (pre-match only)")
        print(f"[MB] Parsed: {parsed_count} events")
        print(f"[MB] Matched with Arbworld: {matched_count}/{parsed_count}")
        print(f"[MB] Written - 1X2: {written_1x2}, OU25: {written_ou25}, BTTS: {written_btts}")
        
        if unmatched_leagues:
            print(f"[MB] Unmatched leagues ({len(unmatched_leagues)}): {', '.join(list(unmatched_leagues)[:10])}")
        
        return parsed_count
    
    except Exception as e:
        print(f"[MB] Scrape error: {e}")
        traceback.print_exc()
        return 0
    
    finally:
        mb_client.close()
        matcher.close()
        writer.close()


def run_loop():
    print(f"[MB] Matchbook Scraper starting - {SCRAPE_INTERVAL//60} min interval")
    
    while True:
        try:
            count = run_scrape()
            print(f"[MB] Scrape complete: {count} events")
        except Exception as e:
            print(f"[MB] Loop error: {e}")
            traceback.print_exc()
        
        print(f"[MB] Next scrape in {SCRAPE_INTERVAL//60} minutes...")
        time.sleep(SCRAPE_INTERVAL)


if __name__ == '__main__':
    run_loop()
