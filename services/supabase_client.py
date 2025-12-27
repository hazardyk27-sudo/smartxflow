"""
SmartXFlow Supabase Client
Handles database operations for matches and market snapshots
Uses REST API directly for better compatibility
"""

import os
import sqlite3
import httpx
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import json


class SupabaseClient:
    """REST API based Supabase client"""
    
    def __init__(self):
        self.url = None
        self.key = None
        self._last_data_update_cache = None
        self._last_data_update_cache_time = None
        self._cache_duration = 60
        self._load_credentials()
    
    def _load_credentials(self):
        try:
            from services import embedded_credentials
            self.url = getattr(embedded_credentials, 'SUPABASE_URL', '')
            self.key = getattr(embedded_credentials, 'SUPABASE_KEY', '')
            if self.url and self.key:
                print(f"[Supabase] Loaded from embedded_credentials")
                self._validate_and_log_url()
                return
        except (ImportError, AttributeError) as e:
            print(f"[Supabase] embedded_credentials not found: {e}")
        
        try:
            import embedded_config
            self.url = getattr(embedded_config, 'EMBEDDED_SUPABASE_URL', '')
            self.key = getattr(embedded_config, 'EMBEDDED_SUPABASE_KEY', '')
            if self.url and self.key:
                print(f"[Supabase] Loaded from embedded_config")
                self._validate_and_log_url()
                return
        except (ImportError, AttributeError) as e:
            print(f"[Supabase] embedded_config not found: {e}")
        
        self.url = os.getenv('SUPABASE_URL', '')
        self.key = os.getenv('SUPABASE_ANON_KEY', '') or os.getenv('SUPABASE_KEY', '')
        if self.url and self.key:
            print(f"[Supabase] Loaded from environment variables")
            self._validate_and_log_url()
        else:
            print(f"[Supabase] WARNING: No credentials found!")
    
    def _validate_and_log_url(self):
        """Validate URL format and log details"""
        print(f"[Supabase] URL: {self.url}")
        print(f"[Supabase] KEY: {self.key[:20]}...{self.key[-10:] if len(self.key) > 30 else ''}")
        
        if 'dashboard' in self.url.lower():
            print(f"[Supabase] ERROR: URL contains 'dashboard' - this is NOT an API URL!")
            print(f"[Supabase] ERROR: Use https://<project-ref>.supabase.co instead")
            self.url = None
        elif not self.url.endswith('.supabase.co'):
            print(f"[Supabase] WARNING: URL does not end with .supabase.co")
        else:
            print(f"[Supabase] URL format OK")
    
    @property
    def is_available(self) -> bool:
        return bool(self.url and self.key)
    
    def _headers(self) -> Dict[str, str]:
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
    
    def _rest_url(self, table: str) -> str:
        return f"{self.url}/rest/v1/{table}"
    
    def get_or_create_match(self, home_team: str, away_team: str, league: str, match_date: str) -> Optional[int]:
        if not self.is_available:
            return None
        
        try:
            url = f"{self._rest_url('matches')}?home_team=eq.{home_team}&away_team=eq.{away_team}&league=eq.{league}&match_date=eq.{match_date}&select=id"
            resp = httpx.get(url, headers=self._headers(), timeout=10)
            
            if resp.status_code == 200 and resp.json():
                return resp.json()[0]['id']
            
            data = {
                "home_team": home_team,
                "away_team": away_team,
                "league": league,
                "match_date": match_date
            }
            resp = httpx.post(self._rest_url('matches'), headers=self._headers(), json=data, timeout=10)
            
            if resp.status_code in [200, 201] and resp.json():
                return resp.json()[0]['id']
            
            return None
        except Exception as e:
            print(f"Error get_or_create_match: {e}")
            return None
    
    def save_snapshot(self, match_id: int, market: str, data: Dict[str, Any]) -> bool:
        if not self.is_available:
            return False
        
        try:
            snapshot = {
                "match_id": match_id,
                "market": market,
                "volume": data.get('Volume', data.get('volume', ''))
            }
            
            if market in ['moneyway_1x2', 'dropping_1x2']:
                snapshot.update({
                    "odds_1": self._parse_numeric(data.get('Odds1')),
                    "odds_x": self._parse_numeric(data.get('OddsX')),
                    "odds_2": self._parse_numeric(data.get('Odds2')),
                    "pct_1": data.get('Pct1', ''),
                    "amt_1": data.get('Amt1', ''),
                    "pct_x": data.get('PctX', ''),
                    "amt_x": data.get('AmtX', ''),
                    "pct_2": data.get('Pct2', ''),
                    "amt_2": data.get('Amt2', ''),
                    "trend_1": data.get('Trend1', ''),
                    "trend_x": data.get('TrendX', ''),
                    "trend_2": data.get('Trend2', '')
                })
            elif market in ['moneyway_ou25', 'dropping_ou25']:
                snapshot.update({
                    "under_odds": self._parse_numeric(data.get('Under')),
                    "over_odds": self._parse_numeric(data.get('Over')),
                    "line": data.get('Line', '2.5'),
                    "pct_under": data.get('PctUnder', ''),
                    "amt_under": data.get('AmtUnder', ''),
                    "pct_over": data.get('PctOver', ''),
                    "amt_over": data.get('AmtOver', ''),
                    "trend_under": data.get('TrendUnder', ''),
                    "trend_over": data.get('TrendOver', '')
                })
            elif market in ['moneyway_btts', 'dropping_btts']:
                snapshot.update({
                    "yes_odds": self._parse_numeric(data.get('OddsYes', data.get('Yes'))),
                    "no_odds": self._parse_numeric(data.get('OddsNo', data.get('No'))),
                    "pct_yes": data.get('PctYes', ''),
                    "amt_yes": data.get('AmtYes', ''),
                    "pct_no": data.get('PctNo', ''),
                    "amt_no": data.get('AmtNo', ''),
                    "trend_yes": data.get('TrendYes', ''),
                    "trend_no": data.get('TrendNo', '')
                })
            
            resp = httpx.post(self._rest_url('odds_snapshots'), headers=self._headers(), json=snapshot, timeout=10)
            return resp.status_code in [200, 201]
        except Exception as e:
            print(f"Error save_snapshot: {e}")
            return False
    
    def get_all_matches(self, limit: int = 100) -> List[Dict[str, Any]]:
        if not self.is_available:
            return []
        
        try:
            url = f"{self._rest_url('matches')}?select=*&order=created_at.desc&limit={limit}"
            resp = httpx.get(url, headers=self._headers(), timeout=10)
            if resp.status_code == 200:
                rows = resp.json()
                return [self._match_to_legacy(r) for r in rows]
            return []
        except Exception as e:
            print(f"Error get_all_matches: {e}")
            return []
    
    def _match_to_legacy(self, row: Dict) -> Dict[str, Any]:
        return {
            'home_team': row.get('home_team', ''),
            'away_team': row.get('away_team', ''),
            'league': row.get('league', ''),
            'date': row.get('match_date', ''),
            'display': f"{row.get('home_team', '')} vs {row.get('away_team', '')}"
        }
    
    def get_match_history(self, home_team: str, away_team: str, market: str, league: str = '') -> List[Dict[str, Any]]:
        """Get history for a specific match with pagination to handle 1000 row limit."""
        if not self.is_available:
            return []
        
        try:
            import urllib.parse
            history_table = f"{market}_history"
            home_enc = urllib.parse.quote(home_team, safe='')
            away_enc = urllib.parse.quote(away_team, safe='')
            
            all_rows = []
            offset = 0
            page_size = 1000
            max_pages = 10
            
            for page in range(max_pages):
                base_url = f"{self._rest_url(history_table)}?home=eq.{home_enc}&away=eq.{away_enc}"
                if league:
                    league_enc = urllib.parse.quote(league, safe='')
                    base_url += f"&league=eq.{league_enc}"
                url = f"{base_url}&order=scraped_at.asc&limit={page_size}&offset={offset}"
                resp = httpx.get(url, headers=self._headers(), timeout=15)
                
                if resp.status_code != 200:
                    break
                
                rows = resp.json()
                if not rows:
                    break
                
                all_rows.extend(rows)
                
                if len(rows) < page_size:
                    break
                
                offset += page_size
            
            return [self._history_row_to_legacy(r, market) for r in all_rows]
        except Exception as e:
            print(f"Error get_match_history from {market}_history: {e}")
            return []
    
    def _history_row_to_legacy(self, row: Dict, market: str) -> Dict[str, Any]:
        result = {
            'ScrapedAt': row.get('scraped_at', ''),
            'Volume': row.get('volume', ''),
            'Home': row.get('home', ''),
            'Away': row.get('away', ''),
            'League': row.get('league', ''),
            'Date': row.get('date', '')
        }
        
        if market in ['moneyway_1x2', 'dropping_1x2']:
            result.update({
                'Odds1': row.get('odds1', ''),
                'OddsX': row.get('oddsx', ''),
                'Odds2': row.get('odds2', ''),
                'Pct1': row.get('pct1', ''),
                'Amt1': row.get('amt1', ''),
                'PctX': row.get('pctx', ''),
                'AmtX': row.get('amtx', ''),
                'Pct2': row.get('pct2', ''),
                'Amt2': row.get('amt2', ''),
                'Odds1_prev': row.get('odds1_prev', ''),
                'OddsX_prev': row.get('oddsx_prev', ''),
                'Odds2_prev': row.get('odds2_prev', ''),
                'Trend1': row.get('trend1', ''),
                'TrendX': row.get('trendx', ''),
                'Trend2': row.get('trend2', '')
            })
        elif market in ['moneyway_ou25', 'dropping_ou25']:
            result.update({
                'Under': row.get('under', ''),
                'Over': row.get('over', ''),
                'Line': row.get('line', '2.5'),
                'PctUnder': row.get('pctunder', ''),
                'AmtUnder': row.get('amtunder', ''),
                'PctOver': row.get('pctover', ''),
                'AmtOver': row.get('amtover', ''),
                'Under_prev': row.get('under_prev', ''),
                'Over_prev': row.get('over_prev', ''),
                'TrendUnder': row.get('trendunder', ''),
                'TrendOver': row.get('trendover', '')
            })
        elif market in ['moneyway_btts', 'dropping_btts']:
            result.update({
                'Yes': row.get('yes', ''),
                'No': row.get('no', ''),
                'OddsYes': row.get('oddsyes', row.get('yes', '')),
                'OddsNo': row.get('oddsno', row.get('no', '')),
                'PctYes': row.get('pctyes', ''),
                'AmtYes': row.get('amtyes', ''),
                'PctNo': row.get('pctno', ''),
                'AmtNo': row.get('amtno', ''),
                'OddsYes_prev': row.get('oddsyes_prev', ''),
                'OddsNo_prev': row.get('oddsno_prev', ''),
                'TrendYes': row.get('trendyes', ''),
                'TrendNo': row.get('trendno', '')
            })
        
        return result
    
    def get_all_matches_with_latest(self, market: str, date_filter: str = None) -> List[Dict[str, Any]]:
        """Get all matches with LATEST data from history table (not stale base table)
        
        Args:
            market: Market name (e.g., 'moneyway_1x2')
            date_filter: Optional date filter - 'yesterday' to get yesterday's matches
        """
        if not self.is_available:
            print(f"[Supabase] ERROR: Not available - URL or KEY missing")
            return []
        
        try:
            from datetime import datetime, timedelta
            import pytz
            
            history_table = f"{market}_history"
            
            tr_tz = pytz.timezone('Europe/Istanbul')
            now_tr = datetime.now(tr_tz)
            
            if date_filter == 'yesterday':
                yesterday = now_tr - timedelta(days=1)
                yesterday_pattern = yesterday.strftime('%d.%b')
                print(f"[Supabase] Fetching yesterday's matches ({yesterday_pattern}) from: {history_table}")
                
                seen = {}
                page = 0
                page_size = 1000
                max_unique_matches = 200
                max_pages = 4
                
                while page < max_pages and len(seen) < max_unique_matches:
                    offset = page * page_size
                    url = f"{self._rest_url(history_table)}?select=*&date=like.*{yesterday_pattern}*&order=scraped_at.desc&limit={page_size}&offset={offset}"
                    
                    resp = None
                    for attempt in range(3):
                        try:
                            resp = httpx.get(url, headers=self._headers(), timeout=30)
                            if resp.status_code == 200:
                                break
                            elif resp.status_code >= 500:
                                print(f"[Supabase] Retry {attempt+1}/3 for page {page+1} (status {resp.status_code})")
                                import time
                                time.sleep(1)
                        except Exception as e:
                            print(f"[Supabase] Retry {attempt+1}/3 for page {page+1} (error: {e})")
                            import time
                            time.sleep(1)
                    
                    if resp and resp.status_code == 200:
                        rows = resp.json()
                        if not rows:
                            break
                        
                        for row in rows:
                            home = row.get('home', '')
                            away = row.get('away', '')
                            league = row.get('league', '')
                            key = f"{home}|{away}|{league}"
                            if key not in seen:
                                seen[key] = row
                            else:
                                existing_time = seen[key].get('scraped_at', '')
                                new_time = row.get('scraped_at', '')
                                if new_time > existing_time:
                                    seen[key] = row
                        
                        print(f"[Supabase] Page {page+1}: {len(rows)} rows, {len(seen)} unique matches")
                        
                        if len(rows) < page_size or len(seen) >= max_unique_matches:
                            break
                        page += 1
                    else:
                        print(f"[Supabase] ERROR {resp.status_code if resp else 'timeout'} on page {page+1} after 3 retries")
                        break
                
                matches = []
                for key, row in seen.items():
                    latest = self._normalize_history_row(row, market)
                    matches.append({
                        'home_team': row.get('home', ''),
                        'away_team': row.get('away', ''),
                        'league': row.get('league', ''),
                        'date': row.get('date', ''),
                        'latest': latest
                    })
                print(f"[Supabase] Got {len(matches)} unique YESTERDAY matches from {history_table} (optimized)")
                return matches
            elif date_filter == 'today':
                # FIXTURES-FIRST APPROACH: Get all today's fixtures first, then batch fetch odds
                today_date = now_tr.date()
                today_str = today_date.strftime('%Y-%m-%d')
                history_table = f"{market}_history"
                print(f"[Supabase] TODAY: Fixtures-first approach for {today_str}")
                
                # Step 1: Get ALL today's fixtures
                fix_url = f"{self._rest_url('fixtures')}?select=*&fixture_date=eq.{today_str}&order=kickoff_utc.desc&limit=500"
                fix_resp = httpx.get(fix_url, headers=self._headers(), timeout=15)
                
                if fix_resp.status_code != 200:
                    print(f"[Supabase] TODAY fixtures fetch error: {fix_resp.status_code}")
                    return []
                
                fixtures = fix_resp.json()
                print(f"[Supabase] TODAY: Got {len(fixtures)} fixtures from table")
                
                if not fixtures:
                    return []
                
                # Step 2: Batch fetch odds from history for ALL fixtures
                from urllib.parse import quote
                odds_cache = {}
                batch_size = 10
                pairs = [(fix.get('home_team', ''), fix.get('away_team', '')) for fix in fixtures]
                
                for i in range(0, len(pairs), batch_size):
                    batch_pairs = pairs[i:i+batch_size]
                    or_filters = ','.join(
                        f'and(home.eq.{quote(h, safe="")},away.eq.{quote(a, safe="")})'
                        for h, a in batch_pairs if h and a
                    )
                    
                    if not or_filters:
                        continue
                    
                    try:
                        batch_url = f"{self._rest_url(history_table)}?or=({or_filters})&order=scraped_at.desc&limit=1000"
                        batch_resp = httpx.get(batch_url, headers=self._headers(), timeout=30)
                        
                        if batch_resp.status_code == 200:
                            rows = batch_resp.json()
                            for row in rows:
                                cache_key = f"{row.get('home', '')}|{row.get('away', '')}"
                                if cache_key not in odds_cache:
                                    odds_cache[cache_key] = row
                    except Exception as e:
                        print(f"[Supabase] TODAY batch {i//batch_size + 1} error: {e}")
                
                print(f"[Supabase] TODAY: Batch fetched odds for {len(odds_cache)}/{len(fixtures)} matches")
                
                # Step 3: Build match list with odds
                matches = []
                tr_tz = pytz.timezone('Europe/Istanbul')
                
                for fix in fixtures:
                    home = fix.get('home_team', '')
                    away = fix.get('away_team', '')
                    league = fix.get('league', '')
                    
                    kickoff_utc = fix.get('kickoff_utc', '')
                    date_display = fix.get('fixture_date', '')
                    if kickoff_utc:
                        try:
                            if isinstance(kickoff_utc, str):
                                kickoff_dt = datetime.fromisoformat(kickoff_utc.replace('Z', '+00:00'))
                            else:
                                kickoff_dt = kickoff_utc
                            kickoff_tr = kickoff_dt.astimezone(tr_tz)
                            date_display = kickoff_tr.strftime('%d.%b %H:%M')
                        except:
                            pass
                    
                    cache_key = f"{home}|{away}"
                    latest_odds = {
                        'ScrapedAt': '',
                        'Volume': '',
                        'Odds1': '-',
                        'OddsX': '-',
                        'Odds2': '-'
                    }
                    
                    if cache_key in odds_cache:
                        row = odds_cache[cache_key]
                        latest_odds = self._normalize_history_row(row, market)
                    
                    matches.append({
                        'home_team': home,
                        'away_team': away,
                        'league': league,
                        'date': date_display,
                        'match_id_hash': fix.get('match_id_hash', ''),
                        'kickoff_utc': kickoff_utc,
                        'latest': latest_odds
                    })
                
                print(f"[Supabase] TODAY: Got {len(matches)} matches (fixtures-first)")
                return matches
            else:
                # ALL mode: Optimized - early exit when enough unique matches found
                today_date = now_tr.date()
                yesterday_date = today_date - timedelta(days=1)
                
                month_map = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                            'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12}
                
                seen = {}
                page = 0
                page_size = 1000
                max_unique_matches = 400
                max_pages = 10
                
                print(f"[Supabase] Fetching ALL matches (optimized, max {max_unique_matches} unique)...")
                
                while page < max_pages and len(seen) < max_unique_matches:
                    offset = page * page_size
                    url = f"{self._rest_url(history_table)}?select=*&order=scraped_at.desc&limit={page_size}&offset={offset}"
                    
                    resp = None
                    for attempt in range(3):
                        try:
                            resp = httpx.get(url, headers=self._headers(), timeout=30)
                            if resp.status_code == 200:
                                break
                            elif resp.status_code >= 500:
                                print(f"[Supabase] Retry {attempt+1}/3 for ALL page {page+1} (status {resp.status_code})")
                                import time
                                time.sleep(1)
                        except Exception as e:
                            print(f"[Supabase] Retry {attempt+1}/3 for ALL page {page+1} (error: {e})")
                            import time
                            time.sleep(1)
                    
                    if resp and resp.status_code == 200:
                        rows = resp.json()
                        if not rows:
                            break
                        
                        for row in rows:
                            date_str = row.get('date', '')
                            if not date_str:
                                continue
                            
                            include_match = False
                            try:
                                date_part = date_str.split()[0]
                                if '.' in date_part:
                                    parts = date_part.split('.')
                                    if len(parts) >= 2:
                                        day = int(parts[0])
                                        month_abbr = parts[1][:3]
                                        month = month_map.get(month_abbr, today_date.month)
                                        year = today_date.year
                                        if month < today_date.month and today_date.month >= 11 and month <= 2:
                                            year += 1
                                        match_date = datetime(year, month, day).date()
                                        if match_date >= yesterday_date:
                                            include_match = True
                                    else:
                                        include_match = True
                                else:
                                    include_match = True
                            except:
                                include_match = True
                            
                            if include_match:
                                home = row.get('home', '')
                                away = row.get('away', '')
                                league = row.get('league', '')
                                key = f"{home}|{away}|{league}"
                                if key not in seen:
                                    seen[key] = row
                                else:
                                    existing_time = seen[key].get('scraped_at', '')
                                    new_time = row.get('scraped_at', '')
                                    if new_time > existing_time:
                                        seen[key] = row
                        
                        print(f"[Supabase] Page {page+1}: {len(rows)} rows, {len(seen)} unique matches")
                        
                        if len(rows) < page_size or len(seen) >= max_unique_matches:
                            break
                        page += 1
                    else:
                        print(f"[Supabase] ERROR on ALL page {page+1} after 3 retries")
                        break
                
                matches = []
                for key, row in seen.items():
                    latest = self._normalize_history_row(row, market)
                    matches.append({
                        'home_team': row.get('home', ''),
                        'away_team': row.get('away', ''),
                        'league': row.get('league', ''),
                        'date': row.get('date', ''),
                        'latest': latest
                    })
                
                # CRITICAL: Also fetch from fixtures table to catch matches not in history
                fixtures_matches = self._get_matches_from_fixtures(seen, today_date, yesterday_date, market)
                if fixtures_matches:
                    matches.extend(fixtures_matches)
                    print(f"[Supabase] Added {len(fixtures_matches)} matches from fixtures table")
                
                print(f"[Supabase] Got {len(matches)} total unique matches (optimized)")
                return matches
        except Exception as e:
            print(f"[Supabase] EXCEPTION in get_all_matches_with_latest: {e}")
            return []
    
    def get_matches_paginated(self, market: str, limit: int = 20, offset: int = 0) -> Dict[str, Any]:
        """FAST paginated match fetch - fixtures first, then only needed odds
        
        Returns: {matches: [...], total: N, has_more: bool}
        
        Strategy:
        1. Get N fixtures from fixtures table (with limit/offset) - ~20 rows
        2. Batch fetch odds only for those N matches - ~100 rows max
        Result: 10,000 rows -> 120 rows = 80x faster
        """
        if not self.is_available:
            return {'matches': [], 'total': 0, 'has_more': False}
        
        try:
            import time
            start_time = time.time()
            from datetime import datetime, timedelta
            from urllib.parse import quote
            import pytz
            
            tr_tz = pytz.timezone('Europe/Istanbul')
            now_tr = datetime.now(tr_tz)
            today_date = now_tr.date()
            yesterday_date = today_date - timedelta(days=1)
            
            today_str = today_date.strftime('%Y-%m-%d')
            yesterday_str = yesterday_date.strftime('%Y-%m-%d')
            
            # Step 1: Get total count first (with Prefer: count=exact)
            count_headers = self._headers()
            count_headers['Prefer'] = 'count=exact'
            count_url = f"{self._rest_url('fixtures')}?select=match_id_hash&fixture_date=gte.{yesterday_str}&limit=1"
            count_resp = httpx.get(count_url, headers=count_headers, timeout=10)
            
            total = 0
            if count_resp.status_code == 200:
                content_range = count_resp.headers.get('content-range', '')
                if '/' in content_range:
                    try:
                        total = int(content_range.split('/')[-1])
                    except:
                        total = 0
                # Don't do fallback count - it's expensive and unnecessary
                # has_more is calculated based on returned row count
            
            # Step 2: Get fixtures with limit/offset (FAST - just N rows)
            # IMPORTANT: Use nullslast to prevent NULL kickoff_utc rows from being front-loaded
            fix_url = f"{self._rest_url('fixtures')}?select=*&fixture_date=gte.{yesterday_str}&order=kickoff_utc.desc.nullslast,fixture_date.desc&limit={limit}&offset={offset}"
            fix_resp = httpx.get(fix_url, headers=self._headers(), timeout=10)
            
            if fix_resp.status_code != 200:
                print(f"[Paginated] Fixtures fetch error: {fix_resp.status_code}")
                return {'matches': [], 'total': 0, 'has_more': False}
            
            fixtures = fix_resp.json()
            print(f"[Paginated] Got {len(fixtures)} fixtures (offset={offset}, limit={limit})")
            
            if not fixtures:
                return {'matches': [], 'total': total, 'has_more': False}
            
            # Step 3: Batch fetch odds ONLY for these fixtures
            history_table = f"{market}_history"
            odds_cache = {}
            
            # Build home|away pairs for batch query
            pairs = [(fix.get('home_team', ''), fix.get('away_team', '')) for fix in fixtures]
            
            # Single batch query for all fixtures (max 20 pairs = ~200 rows)
            or_filters = ','.join(
                f'and(home.eq.{quote(h, safe="")},away.eq.{quote(a, safe="")})'
                for h, a in pairs if h and a
            )
            
            if or_filters:
                batch_url = f"{self._rest_url(history_table)}?or=({or_filters})&order=scraped_at.desc&limit=500"
                batch_resp = httpx.get(batch_url, headers=self._headers(), timeout=15)
                
                if batch_resp.status_code == 200:
                    rows = batch_resp.json()
                    for row in rows:
                        cache_key = f"{row.get('home', '')}|{row.get('away', '')}"
                        if cache_key not in odds_cache:
                            odds_cache[cache_key] = row
                    print(f"[Paginated] Batch fetched {len(odds_cache)} odds from {history_table}")
            
            # Step 4: Build match list
            matches = []
            for fix in fixtures:
                home = fix.get('home_team', '')
                away = fix.get('away_team', '')
                league = fix.get('league', '')
                
                kickoff_utc = fix.get('kickoff_utc', '')
                date_display = fix.get('fixture_date', '')
                if kickoff_utc:
                    try:
                        if isinstance(kickoff_utc, str):
                            kickoff_dt = datetime.fromisoformat(kickoff_utc.replace('Z', '+00:00'))
                        else:
                            kickoff_dt = kickoff_utc
                        kickoff_tr = kickoff_dt.astimezone(tr_tz)
                        date_display = kickoff_tr.strftime('%d.%b %H:%M')
                    except:
                        pass
                
                cache_key = f"{home}|{away}"
                latest_odds = self._get_empty_odds(market)
                
                if cache_key in odds_cache:
                    row = odds_cache[cache_key]
                    latest_odds = self._normalize_history_row(row, market)
                
                matches.append({
                    'home_team': home,
                    'away_team': away,
                    'league': league,
                    'date': date_display,
                    'match_id_hash': fix.get('match_id_hash', ''),
                    'kickoff_utc': kickoff_utc,
                    'latest': latest_odds
                })
            
            elapsed = time.time() - start_time
            # If total is unknown (0), assume more data exists if we got a full page
            if total == 0:
                has_more = len(fixtures) == limit
            else:
                has_more = offset + len(fixtures) < total
            print(f"[Paginated] Completed in {elapsed:.2f}s - {len(matches)} matches, total={total}, has_more={has_more}")
            
            return {
                'matches': matches,
                'total': total,
                'has_more': has_more
            }
        except Exception as e:
            print(f"[Paginated] EXCEPTION: {e}")
            import traceback
            traceback.print_exc()
            return {'matches': [], 'total': 0, 'has_more': False}
    
    def _get_empty_odds(self, market: str) -> Dict[str, Any]:
        """Return empty odds structure for a market"""
        if market in ['moneyway_1x2', 'dropping_1x2']:
            return {
                'ScrapedAt': '',
                'Volume': '',
                'Odds1': '-',
                'OddsX': '-',
                'Odds2': '-',
                'Pct1': '',
                'Amt1': '',
                'PctX': '',
                'AmtX': '',
                'Pct2': '',
                'Amt2': ''
            }
        elif market in ['moneyway_ou25', 'dropping_ou25']:
            return {
                'ScrapedAt': '',
                'Volume': '',
                'Under': '-',
                'Over': '-',
                'PctUnder': '',
                'AmtUnder': '',
                'PctOver': '',
                'AmtOver': ''
            }
        elif market in ['moneyway_btts', 'dropping_btts']:
            return {
                'ScrapedAt': '',
                'Volume': '',
                'OddsYes': '-',
                'OddsNo': '-',
                'PctYes': '',
                'AmtYes': '',
                'PctNo': '',
                'AmtNo': ''
            }
        return {'ScrapedAt': '', 'Volume': ''}
    
    def _get_matches_from_fixtures(self, seen: Dict, today_date, yesterday_date, market: str = 'moneyway_1x2') -> List[Dict[str, Any]]:
        """Fetch matches from fixtures table that are not already in seen dict
        
        This ensures matches are shown even if they don't have history table data yet.
        Uses batch query to fetch odds for all fixtures at once (optimized).
        """
        if not self.is_available:
            return []
        
        try:
            from datetime import datetime
            from urllib.parse import quote
            import pytz
            
            # Fetch fixtures for today and yesterday
            today_str = today_date.strftime('%Y-%m-%d')
            yesterday_str = yesterday_date.strftime('%Y-%m-%d')
            
            url = f"{self._rest_url('fixtures')}?select=*&fixture_date=gte.{yesterday_str}&fixture_date=lte.{today_str}&order=kickoff_utc.desc&limit=500"
            resp = httpx.get(url, headers=self._headers(), timeout=15)
            
            if resp.status_code != 200:
                print(f"[Supabase] Fixtures fetch error: {resp.status_code}")
                return []
            
            fixtures = resp.json()
            history_table = f"{market}_history"
            
            # Collect fixtures not in seen
            fixtures_to_enrich = []
            for fix in fixtures:
                home = fix.get('home_team', '')
                away = fix.get('away_team', '')
                league = fix.get('league', '')
                key = f"{home}|{away}|{league}"
                
                # Skip if already in seen from history table
                if key in seen:
                    continue
                
                fixtures_to_enrich.append(fix)
                seen[key] = True
            
            if not fixtures_to_enrich:
                return []
            
            print(f"[Supabase] Found {len(fixtures_to_enrich)} fixtures not in history, batch fetching odds...")
            
            # BATCH FETCH using home+away pairs for precision
            odds_cache = {}
            batch_size = 10  # Smaller batch to ensure all matches get data within 1000 row limit
            
            # Build list of home|away pairs
            pairs = [(fix.get('home_team', ''), fix.get('away_team', '')) for fix in fixtures_to_enrich]
            
            for i in range(0, len(pairs), batch_size):
                batch_pairs = pairs[i:i+batch_size]
                or_filters = ','.join(
                    f'and(home.eq.{quote(h, safe="")},away.eq.{quote(a, safe="")})'
                    for h, a in batch_pairs if h and a
                )
                
                if not or_filters:
                    continue
                
                try:
                    batch_url = f"{self._rest_url(history_table)}?or=({or_filters})&order=scraped_at.desc&limit=1000"
                    batch_resp = httpx.get(batch_url, headers=self._headers(), timeout=30)
                    
                    if batch_resp.status_code == 200:
                        rows = batch_resp.json()
                        for row in rows:
                            cache_key = f"{row.get('home', '')}|{row.get('away', '')}"
                            if cache_key not in odds_cache:
                                odds_cache[cache_key] = row
                except Exception as e:
                    print(f"[Supabase] Batch odds fetch error: {e}")
            
            print(f"[Supabase] Batch fetched {len(odds_cache)} odds records")
            
            # Now build matches with cached odds
            new_matches = []
            tr_tz = pytz.timezone('Europe/Istanbul')
            
            for fix in fixtures_to_enrich:
                home = fix.get('home_team', '')
                away = fix.get('away_team', '')
                league = fix.get('league', '')
                
                # Format date for UI (e.g., "20.Dec 15:30")
                kickoff_utc = fix.get('kickoff_utc', '')
                date_display = fix.get('fixture_date', '')
                if kickoff_utc:
                    try:
                        if isinstance(kickoff_utc, str):
                            kickoff_dt = datetime.fromisoformat(kickoff_utc.replace('Z', '+00:00'))
                        else:
                            kickoff_dt = kickoff_utc
                        kickoff_tr = kickoff_dt.astimezone(tr_tz)
                        date_display = kickoff_tr.strftime('%d.%b %H:%M')
                    except:
                        pass
                
                # Get odds from cache
                cache_key = f"{home}|{away}"
                latest_odds = {
                    'ScrapedAt': '',
                    'Volume': '',
                    'Odds1': '-',
                    'OddsX': '-',
                    'Odds2': '-'
                }
                
                if cache_key in odds_cache:
                    row = odds_cache[cache_key]
                    latest_odds = self._normalize_history_row(row, market)
                
                new_matches.append({
                    'home_team': home,
                    'away_team': away,
                    'league': league,
                    'date': date_display,
                    'match_id_hash': fix.get('match_id_hash', ''),
                    'kickoff_utc': kickoff_utc,
                    'latest': latest_odds
                })
            
            return new_matches
            
        except Exception as e:
            print(f"[Supabase] Error fetching fixtures: {e}")
            return []
    
    def _get_matches_from_fixtures_today(self, seen: Dict, today_date, market: str = 'moneyway_1x2') -> List[Dict[str, Any]]:
        """Fetch TODAY's fixtures that are not already in seen dict (for TODAY filter)"""
        if not self.is_available:
            return []
        
        try:
            from datetime import datetime
            from urllib.parse import quote
            import pytz
            
            today_str = today_date.strftime('%Y-%m-%d')
            
            url = f"{self._rest_url('fixtures')}?select=*&fixture_date=eq.{today_str}&order=kickoff_utc.desc&limit=300"
            resp = httpx.get(url, headers=self._headers(), timeout=15)
            
            if resp.status_code != 200:
                print(f"[Supabase] TODAY Fixtures fetch error: {resp.status_code}")
                return []
            
            fixtures = resp.json()
            history_table = f"{market}_history"
            
            # Collect fixtures not in seen
            fixtures_to_enrich = []
            for fix in fixtures:
                home = fix.get('home_team', '')
                away = fix.get('away_team', '')
                league = fix.get('league', '')
                key = f"{home}|{away}|{league}"
                
                if key in seen:
                    continue
                
                fixtures_to_enrich.append(fix)
                seen[key] = True
            
            if not fixtures_to_enrich:
                return []
            
            print(f"[Supabase] Found {len(fixtures_to_enrich)} TODAY fixtures not in history, batch fetching...")
            
            # BATCH FETCH odds using home+away pairs for precision
            odds_cache = {}
            batch_size = 10  # Smaller batch to ensure all matches get data within 1000 row limit
            
            # Build list of home|away pairs
            pairs = [(fix.get('home_team', ''), fix.get('away_team', '')) for fix in fixtures_to_enrich]
            
            for i in range(0, len(pairs), batch_size):
                batch_pairs = pairs[i:i+batch_size]
                or_filters = ','.join(
                    f'and(home.eq.{quote(h, safe="")},away.eq.{quote(a, safe="")})'
                    for h, a in batch_pairs if h and a
                )
                
                if not or_filters:
                    continue
                
                try:
                    batch_url = f"{self._rest_url(history_table)}?or=({or_filters})&order=scraped_at.desc&limit=1000"
                    batch_resp = httpx.get(batch_url, headers=self._headers(), timeout=30)
                    
                    if batch_resp.status_code == 200:
                        rows = batch_resp.json()
                        for row in rows:
                            cache_key = f"{row.get('home', '')}|{row.get('away', '')}"
                            if cache_key not in odds_cache:
                                odds_cache[cache_key] = row
                except Exception as e:
                    print(f"[Supabase] TODAY batch odds fetch error: {e}")
            
            print(f"[Supabase] TODAY: Batch fetched odds for {len(odds_cache)} matches")
            
            # Build matches
            new_matches = []
            tr_tz = pytz.timezone('Europe/Istanbul')
            
            for fix in fixtures_to_enrich:
                home = fix.get('home_team', '')
                away = fix.get('away_team', '')
                league = fix.get('league', '')
                
                kickoff_utc = fix.get('kickoff_utc', '')
                date_display = fix.get('fixture_date', '')
                if kickoff_utc:
                    try:
                        if isinstance(kickoff_utc, str):
                            kickoff_dt = datetime.fromisoformat(kickoff_utc.replace('Z', '+00:00'))
                        else:
                            kickoff_dt = kickoff_utc
                        kickoff_tr = kickoff_dt.astimezone(tr_tz)
                        date_display = kickoff_tr.strftime('%d.%b %H:%M')
                    except:
                        pass
                
                cache_key = f"{home}|{away}"
                latest_odds = {
                    'ScrapedAt': '',
                    'Volume': '',
                    'Odds1': '-',
                    'OddsX': '-',
                    'Odds2': '-'
                }
                
                if cache_key in odds_cache:
                    row = odds_cache[cache_key]
                    latest_odds = self._normalize_history_row(row, market)
                
                new_matches.append({
                    'home_team': home,
                    'away_team': away,
                    'league': league,
                    'date': date_display,
                    'match_id_hash': fix.get('match_id_hash', ''),
                    'kickoff_utc': kickoff_utc,
                    'latest': latest_odds
                })
            
            return new_matches
            
        except Exception as e:
            print(f"[Supabase] Error fetching TODAY fixtures: {e}")
            return []
    
    def _get_matches_from_base_table(self, market: str) -> List[Dict[str, Any]]:
        """Fallback: Get matches from base table (may be stale)"""
        try:
            url = f"{self._rest_url(market)}?select=*&order=id.desc"
            print(f"[Supabase] Fetching from base: {url}")
            resp = httpx.get(url, headers=self._headers(), timeout=15)
            
            if resp.status_code == 200:
                rows = resp.json()
                matches = []
                for row in rows:
                    latest = self._normalize_row(row, market)
                    matches.append({
                        'home_team': row.get('home', ''),
                        'away_team': row.get('away', ''),
                        'league': row.get('league', ''),
                        'date': row.get('date', ''),
                        'latest': latest
                    })
                print(f"[Supabase] Got {len(matches)} matches from {market} (base)")
                return matches
        except Exception as e:
            print(f"[Supabase] Base table fallback error: {e}")
        return []
    
    def _normalize_history_row(self, row: Dict, market: str) -> Dict[str, Any]:
        """Normalize history table row to expected format"""
        result = {
            'ScrapedAt': row.get('scraped_at', ''),
            'Volume': row.get('volume', '')
        }
        
        if '1x2' in market:
            result.update({
                'Odds1': row.get('odds1', '-'),
                'OddsX': row.get('oddsx', '-'),
                'Odds2': row.get('odds2', '-'),
                'Pct1': row.get('pct1', ''),
                'Amt1': row.get('amt1', ''),
                'PctX': row.get('pctx', ''),
                'AmtX': row.get('amtx', ''),
                'Pct2': row.get('pct2', ''),
                'Amt2': row.get('amt2', ''),
                'Trend1': row.get('trend1', ''),
                'TrendX': row.get('trendx', ''),
                'Trend2': row.get('trend2', '')
            })
        elif 'ou25' in market:
            result.update({
                'Under': row.get('under', '-'),
                'Over': row.get('over', '-'),
                'Line': row.get('line', '2.5'),
                'PctUnder': row.get('pctunder', ''),
                'AmtUnder': row.get('amtunder', ''),
                'PctOver': row.get('pctover', ''),
                'AmtOver': row.get('amtover', ''),
                'TrendUnder': row.get('trendunder', ''),
                'TrendOver': row.get('trendover', '')
            })
        elif 'btts' in market:
            yes_val = row.get('oddsyes', row.get('yes', '-'))
            no_val = row.get('oddsno', row.get('no', '-'))
            result.update({
                'Yes': yes_val,
                'No': no_val,
                'OddsYes': yes_val,
                'OddsNo': no_val,
                'PctYes': row.get('pctyes', ''),
                'AmtYes': row.get('amtyes', ''),
                'PctNo': row.get('pctno', ''),
                'AmtNo': row.get('amtno', ''),
                'TrendYes': row.get('trendyes', ''),
                'TrendNo': row.get('trendno', '')
            })
        
        return result
    
    def _normalize_row(self, row: Dict, market: str) -> Dict[str, Any]:
        """Convert lowercase Supabase columns to expected format"""
        if market in ['moneyway_1x2', 'dropping_1x2']:
            return {
                'Odds1': row.get('odds1', '-'),
                'OddsX': row.get('oddsx', '-'),
                'Odds2': row.get('odds2', '-'),
                'Pct1': row.get('pct1', ''),
                'Amt1': row.get('amt1', ''),
                'PctX': row.get('pctx', ''),
                'AmtX': row.get('amtx', ''),
                'Pct2': row.get('pct2', ''),
                'Amt2': row.get('amt2', ''),
                'Volume': row.get('volume', ''),
                'Odds1_prev': row.get('odds1_prev', ''),
                'OddsX_prev': row.get('oddsx_prev', ''),
                'Odds2_prev': row.get('odds2_prev', ''),
                'Trend1': row.get('trend1', ''),
                'TrendX': row.get('trendx', ''),
                'Trend2': row.get('trend2', '')
            }
        elif market in ['moneyway_ou25', 'dropping_ou25']:
            return {
                'Under': row.get('under', '-'),
                'Over': row.get('over', '-'),
                'Line': row.get('line', '2.5'),
                'PctUnder': row.get('pctunder', ''),
                'AmtUnder': row.get('amtunder', ''),
                'PctOver': row.get('pctover', ''),
                'AmtOver': row.get('amtover', ''),
                'Volume': row.get('volume', ''),
                'Under_prev': row.get('under_prev', ''),
                'Over_prev': row.get('over_prev', ''),
                'TrendUnder': row.get('trendunder', ''),
                'TrendOver': row.get('trendover', '')
            }
        elif market in ['moneyway_btts', 'dropping_btts']:
            yes_val = row.get('oddsyes', row.get('yes', '-'))
            no_val = row.get('oddsno', row.get('no', '-'))
            return {
                'Yes': yes_val,
                'No': no_val,
                'OddsYes': yes_val,
                'OddsNo': no_val,
                'PctYes': row.get('pctyes', ''),
                'AmtYes': row.get('amtyes', ''),
                'PctNo': row.get('pctno', ''),
                'AmtNo': row.get('amtno', ''),
                'Volume': row.get('volume', ''),
                'OddsYes_prev': row.get('oddsyes_prev', ''),
                'OddsNo_prev': row.get('oddsno_prev', ''),
                'TrendYes': row.get('trendyes', ''),
                'TrendNo': row.get('trendno', '')
            }
        return row
    
    def get_last_data_update(self) -> Optional[str]:
        """Get the most recent ScrapedAt timestamp from history tables (cached for 60s)"""
        if not self.is_available:
            return None
        
        now = datetime.now()
        if (self._last_data_update_cache is not None and 
            self._last_data_update_cache_time is not None and
            (now - self._last_data_update_cache_time).total_seconds() < self._cache_duration):
            return self._last_data_update_cache
        
        latest_time = None
        history_tables = [
            'moneyway_1x2_history', 'moneyway_ou25_history', 'moneyway_btts_history',
            'dropping_1x2_history', 'dropping_ou25_history', 'dropping_btts_history'
        ]
        
        for table in history_tables:
            try:
                url = f"{self._rest_url(table)}?select=scraped_at&order=scraped_at.desc&limit=1"
                resp = httpx.get(url, headers=self._headers(), timeout=5)
                if resp.status_code == 200:
                    rows = resp.json()
                    if rows and rows[0].get('scraped_at'):
                        ts = rows[0]['scraped_at']
                        if latest_time is None or ts > latest_time:
                            latest_time = ts
            except Exception as e:
                continue
        
        self._last_data_update_cache = latest_time
        self._last_data_update_cache_time = now
        
        return latest_time
    
    def get_alarm_settings(self) -> List[Dict]:
        """Get all alarm settings from database"""
        if not self.is_available:
            return []
        try:
            url = f"{self._rest_url('alarm_settings')}?select=*"
            resp = httpx.get(url, headers=self._headers(), timeout=10)
            if resp.status_code == 200:
                return resp.json()
            return []
        except Exception as e:
            print(f"Error get_alarm_settings: {e}")
            return []
    
    def get_alarm_setting(self, alarm_type: str) -> Optional[Dict]:
        """Get specific alarm setting"""
        if not self.is_available:
            return None
        try:
            url = f"{self._rest_url('alarm_settings')}?alarm_type=eq.{alarm_type}&select=*"
            resp = httpx.get(url, headers=self._headers(), timeout=10)
            if resp.status_code == 200:
                rows = resp.json()
                return rows[0] if rows else None
            return None
        except Exception as e:
            print(f"Error get_alarm_setting: {e}")
            return None
    
    def update_alarm_setting(self, alarm_type: str, enabled: bool, config: Dict) -> bool:
        """Update or create an alarm setting (upsert) - Admin Panel → Supabase yazma
        
        Bu fonksiyon Admin panelden değiştirilen ayarları Supabase'e yazar.
        AlarmCalculator sonraki hesaplamada bu ayarları okur.
        """
        if not self.is_available:
            print(f"[CONFIG SAVE] Supabase not available!")
            return False
        try:
            data = [{
                'alarm_type': alarm_type,
                'enabled': enabled,
                'config': config,
                'updated_at': datetime.now().isoformat()
            }]
            headers = self._headers()
            headers['Prefer'] = 'resolution=merge-duplicates,return=representation'
            
            url = f"{self._rest_url('alarm_settings')}?on_conflict=alarm_type"
            resp = httpx.post(url, headers=headers, json=data, timeout=10)
            
            if resp.status_code in [200, 201]:
                print(f"[CONFIG SAVE] {alarm_type}: Supabase'e kaydedildi (enabled={enabled})")
                return True
            else:
                print(f"[CONFIG SAVE ERROR] {alarm_type}: HTTP {resp.status_code} - {resp.text[:200]}")
                return False
        except Exception as e:
            print(f"[CONFIG SAVE ERROR] {alarm_type}: {e}")
            return False
    
    def delete_alarm_setting(self, alarm_type: str) -> bool:
        """Delete an alarm setting from database"""
        if not self.is_available:
            return False
        try:
            url = f"{self._rest_url('alarm_settings')}?alarm_type=eq.{alarm_type}"
            resp = httpx.delete(url, headers=self._headers(), timeout=10)
            return resp.status_code in [200, 204]
        except Exception as e:
            print(f"Error delete_alarm_setting: {e}")
            return False
    
    def get_6h_odds_history(self, market: str) -> Dict[str, Dict[str, Any]]:
        """Drop markets: İlk snapshot vs Son snapshot = Açılıştan bu yana değişim.
        OPTIMIZED: Sadece unique maçları çek, her maç için 1 first + 1 last."""
        if not self.is_available or not market.startswith('dropping'):
            return {}
        
        history_table = f"{market}_history"
        
        try:
            import time
            from concurrent.futures import ThreadPoolExecutor
            start_time = time.time()
            
            if market == 'dropping_1x2':
                sels = ['odds1', 'oddsx', 'odds2']
                select_cols = 'home,away,odds1,oddsx,odds2,scraped_at'
            elif market == 'dropping_ou25':
                sels = ['under', 'over']
                select_cols = 'home,away,under,over,scraped_at'
            elif market == 'dropping_btts':
                sels = ['oddsyes', 'oddsno']
                select_cols = 'home,away,oddsyes,oddsno,scraped_at'
            else:
                return {}
            
            def fetch_unique_matches(order_dir):
                """Fetch unique matches with first/last record only"""
                seen = set()
                rows = []
                offset = 0
                max_unique = 600
                
                while len(rows) < max_unique:
                    url = f"{self._rest_url(history_table)}?select={select_cols}&order=scraped_at.{order_dir}&offset={offset}&limit=1000"
                    resp = httpx.get(url, headers=self._headers(), timeout=15)
                    if resp.status_code != 200:
                        break
                    batch = resp.json()
                    if not batch:
                        break
                    
                    for row in batch:
                        key = f"{row.get('home', '')}|{row.get('away', '')}"
                        if key not in seen:
                            seen.add(key)
                            rows.append(row)
                            if len(rows) >= max_unique:
                                break
                    
                    if len(batch) < 1000 or len(rows) >= max_unique:
                        break
                    offset += 1000
                    if offset > 10000:
                        break
                
                return rows
            
            with ThreadPoolExecutor(max_workers=2) as executor:
                future_first = executor.submit(fetch_unique_matches, 'asc')
                future_last = executor.submit(fetch_unique_matches, 'desc')
                first_rows = future_first.result()
                last_rows = future_last.result()
            
            match_first = {f"{r.get('home', '')}|{r.get('away', '')}": r for r in first_rows}
            match_last = {f"{r.get('home', '')}|{r.get('away', '')}": r for r in last_rows}
            
            if not match_first and not match_last:
                return {}
            
            result = {}
            for key in match_last.keys():
                first_row = match_first.get(key, {})
                last_row = match_last.get(key, {})
                
                home, away = key.split('|', 1) if '|' in key else (key, '')
                
                match_data = {'home': home, 'away': away, 'values': {}}
                for sel in sels:
                    old_val = self._parse_numeric(first_row.get(sel, ''))
                    new_val = self._parse_numeric(last_row.get(sel, ''))
                    if old_val is None: old_val = new_val
                    if new_val is None: new_val = old_val
                    pct_change = 0
                    trend = 'stable'
                    if old_val and new_val and old_val > 0:
                        pct_change = ((new_val - old_val) / old_val) * 100
                        trend = 'down' if new_val < old_val else ('up' if new_val > old_val else 'stable')
                    match_data['values'][sel] = {'old': old_val, 'new': new_val, 'pct_change': round(pct_change, 1), 'trend': trend, 'history': [old_val, new_val]}
                result[key] = match_data
            
            elapsed = time.time() - start_time
            print(f"[Drop] Got {len(result)} matches for {market} in {elapsed:.1f}s (optimized)")
            return result
            
        except Exception as e:
            print(f"[Drop] Error: {e}")
            return {}
    
    def _parse_numeric(self, val: Any) -> Optional[float]:
        if val is None or val == '' or val == '-':
            return None
        try:
            return float(str(val).replace(',', '.').split('\n')[0])
        except:
            return None
    
    def get_match_history_for_sharp(self, home: str, away: str, history_table: str) -> List[Dict]:
        """Get match history for Sharp calculation (all snapshots)"""
        if not self.is_available:
            return []
        
        try:
            from urllib.parse import quote
            home_enc = quote(home, safe='')
            away_enc = quote(away, safe='')
            url = f"{self._rest_url(history_table)}?home=eq.{home_enc}&away=eq.{away_enc}&order=scraped_at.asc&limit=500"
            resp = httpx.get(url, headers=self._headers(), timeout=15)
            if resp.status_code == 200:
                return resp.json()
            else:
                print(f"[Sharp] History fetch failed: {resp.status_code} for {home} vs {away}")
            return []
        except Exception as e:
            print(f"[Sharp] History error for {home} vs {away}: {e}")
            return []
    
    def save_sharp_config(self, config: Dict) -> bool:
        """Save Sharp config to Supabase"""
        return True
    
    def delete_all_sharp_alarms(self) -> bool:
        """Delete all Sharp alarms"""
        return True
    
    def cleanup_old_matches(self, cutoff_date: str) -> Dict[str, int]:
        """
        Delete D-2+ matches from all tables.
        cutoff_date format: YYYY-MM-DD (matches older than this date will be deleted)
        Returns count of deleted records per table.
        """
        if not self.is_available:
            return {}
        
        deleted = {}
        
        # History tabloları
        history_tables = ['moneyway_1x2_history', 'moneyway_ou25_history', 'moneyway_btts_history', 
                          'dropping_1x2_history', 'dropping_ou25_history', 'dropping_btts_history']
        
        # History tablolarını sil (scraped_at < cutoff_date)
        for table in history_tables:
            try:
                # Prefer header ile silinen kayıtları döndür
                headers = self._headers()
                headers['Prefer'] = 'return=representation'
                
                # scraped_at sütunu ile filtrele
                url = f"{self._rest_url(table)}?scraped_at=lt.{cutoff_date}T00:00:00"
                resp = httpx.delete(url, headers=headers, timeout=60)
                
                if resp.status_code == 200:
                    # Silinen kayıtları say
                    try:
                        deleted_rows = resp.json()
                        count = len(deleted_rows) if isinstance(deleted_rows, list) else 0
                        if count > 0:
                            deleted[table] = count
                            print(f"[Cleanup] Deleted {count} old records from {table}")
                    except:
                        pass
                elif resp.status_code == 204:
                    # No content - silme başarılı ama kayıt yok
                    pass
                elif resp.status_code == 404:
                    pass  # Tablo yok, sorun değil
                else:
                    print(f"[Cleanup] Error deleting from {table}: {resp.status_code} - {resp.text[:100]}")
            except Exception as e:
                print(f"[Cleanup] Exception for {table}: {e}")
        
        return deleted
    
    def _snapshot_to_legacy(self, snap: Dict, market: str) -> Dict[str, Any]:
        result = {
            'ScrapedAt': snap.get('scraped_at', ''),
            'Volume': snap.get('volume', '')
        }
        
        if market in ['moneyway_1x2', 'dropping_1x2']:
            result.update({
                'Odds1': snap.get('odds_1'),
                'OddsX': snap.get('odds_x'),
                'Odds2': snap.get('odds_2'),
                'Pct1': snap.get('pct_1', ''),
                'Amt1': snap.get('amt_1', ''),
                'PctX': snap.get('pct_x', ''),
                'AmtX': snap.get('amt_x', ''),
                'Pct2': snap.get('pct_2', ''),
                'Amt2': snap.get('amt_2', ''),
                'Trend1': snap.get('trend_1', ''),
                'TrendX': snap.get('trend_x', ''),
                'Trend2': snap.get('trend_2', '')
            })
        elif market in ['moneyway_ou25', 'dropping_ou25']:
            result.update({
                'Under': snap.get('under_odds'),
                'Over': snap.get('over_odds'),
                'Line': snap.get('line', '2.5'),
                'PctUnder': snap.get('pct_under', ''),
                'AmtUnder': snap.get('amt_under', ''),
                'PctOver': snap.get('pct_over', ''),
                'AmtOver': snap.get('amt_over', ''),
                'TrendUnder': snap.get('trend_under', ''),
                'TrendOver': snap.get('trend_over', '')
            })
        elif market in ['moneyway_btts', 'dropping_btts']:
            result.update({
                'OddsYes': snap.get('yes_odds'),
                'OddsNo': snap.get('no_odds'),
                'PctYes': snap.get('pct_yes', ''),
                'AmtYes': snap.get('amt_yes', ''),
                'PctNo': snap.get('pct_no', ''),
                'AmtNo': snap.get('amt_no', ''),
                'TrendYes': snap.get('trend_yes', ''),
                'TrendNo': snap.get('trend_no', '')
            })
        
        return result


class LocalDatabase:
    """Fallback local SQLite database when Supabase is not available"""
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
            os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, "moneyway.db")
        self.db_path = db_path
    
    def get_all_matches(self) -> List[Dict[str, Any]]:
        matches = []
        seen = set()
        
        if not os.path.exists(self.db_path):
            return matches
        
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%_hist'")
            tables = [row[0] for row in cur.fetchall()]
            
            for table in tables:
                try:
                    cur.execute(f'SELECT DISTINCT League, Home, Away, Date FROM "{table}"')
                    for row in cur.fetchall():
                        key = (row[1], row[2])
                        if key not in seen:
                            seen.add(key)
                            matches.append({
                                'league': row[0],
                                'home_team': row[1],
                                'away_team': row[2],
                                'date': row[3],
                                'display': f"{row[1]} vs {row[2]}"
                            })
                except Exception:
                    continue
            
            conn.close()
        except Exception as e:
            print(f"Error reading local DB: {e}")
        
        return matches
    
    def get_match_history(
        self,
        home: str,
        away: str,
        market_key: str = "moneyway_1x2"
    ) -> List[Dict[str, Any]]:
        history = []
        
        if not os.path.exists(self.db_path):
            return history
        
        table_name = f"{market_key}_hist"
        
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            
            cur.execute(
                f'SELECT * FROM "{table_name}" WHERE Home=? AND Away=? ORDER BY ScrapedAt',
                (home, away)
            )
            
            for row in cur.fetchall():
                history.append(dict(row))
            
            conn.close()
        except Exception as e:
            print(f"Error reading match history: {e}")
        
        return history
    
    def get_all_matches_with_latest(self, market_key: str = "moneyway_1x2") -> List[Dict[str, Any]]:
        """Get all matches with their latest snapshot - single query optimization"""
        matches = []
        
        if not os.path.exists(self.db_path):
            return matches
        
        table_name = f"{market_key}_hist"
        
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            
            cur.execute(f"""
                SELECT * FROM "{table_name}" t1
                WHERE t1.ScrapedAt = (
                    SELECT MAX(t2.ScrapedAt) 
                    FROM "{table_name}" t2 
                    WHERE t2.Home = t1.Home AND t2.Away = t1.Away
                )
                ORDER BY t1.Date DESC
            """)
            
            for row in cur.fetchall():
                d = dict(row)
                matches.append({
                    'home_team': d.get('Home', ''),
                    'away_team': d.get('Away', ''),
                    'league': d.get('League', ''),
                    'date': d.get('Date', ''),
                    'latest': d
                })
            
            conn.close()
        except Exception as e:
            print(f"Error reading matches with latest: {e}")
        
        return matches
    
    def get_available_markets(self) -> List[str]:
        markets = []
        
        if not os.path.exists(self.db_path):
            return markets
        
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%_hist'")
            markets = [row[0].replace('_hist', '') for row in cur.fetchall()]
            
            conn.close()
        except Exception:
            pass
        
        return markets


class HybridDatabase:
    """Hybrid database that uses Supabase when available, falls back to SQLite"""
    
    def __init__(self):
        self.supabase = SupabaseClient()
        self.local = LocalDatabase()
    
    @property
    def is_supabase_available(self) -> bool:
        return self.supabase.is_available
    
    def get_all_matches(self) -> List[Dict[str, Any]]:
        if self.supabase.is_available:
            matches = self.supabase.get_all_matches()
            if matches:
                return matches
        return self.local.get_all_matches()
    
    def get_match_history(self, home: str, away: str, market: str, league: str = '') -> List[Dict[str, Any]]:
        if self.supabase.is_available:
            history = self.supabase.get_match_history(home, away, market, league)
            if history:
                return history
        return self.local.get_match_history(home, away, market)
    
    def get_all_matches_with_latest(self, market: str, date_filter: str = None) -> List[Dict[str, Any]]:
        """Get all matches with latest snapshot from Supabase or local"""
        if self.supabase.is_available:
            matches = self.supabase.get_all_matches_with_latest(market, date_filter=date_filter)
            if matches:
                return matches
        return self.local.get_all_matches_with_latest(market)
    
    def get_matches_paginated(self, market: str, limit: int = 20, offset: int = 0) -> Dict[str, Any]:
        """FAST paginated match fetch - delegates to Supabase"""
        if self.supabase.is_available:
            return self.supabase.get_matches_paginated(market, limit=limit, offset=offset)
        # Fallback to local (no pagination - just return all)
        matches = self.local.get_all_matches_with_latest(market)
        return {
            'matches': matches[offset:offset + limit],
            'total': len(matches),
            'has_more': offset + limit < len(matches)
        }
    
    def save_scraped_data(self, market: str, rows: List[Dict[str, Any]]) -> int:
        if not self.supabase.is_available:
            return 0
        
        saved = 0
        for row in rows:
            home = row.get('Home', '')
            away = row.get('Away', '')
            league = row.get('League', '')
            date = row.get('Date', '')
            
            if not home or not away:
                continue
            
            match_id = self.supabase.get_or_create_match(home, away, league, date)
            if match_id:
                if self.supabase.save_snapshot(match_id, market, row):
                    saved += 1
        
        return saved
    
    def get_last_data_update(self) -> Optional[str]:
        """Get the most recent data update timestamp from Supabase"""
        if self.supabase.is_available:
            return self.supabase.get_last_data_update()
        return None


_database = None


def get_database() -> HybridDatabase:
    global _database
    if _database is None:
        _database = HybridDatabase()
    return _database


def get_supabase_client():
    return get_database().supabase if get_database().is_supabase_available else None


def fetch_alarms_from_supabase(table_name: str, order_by: str = 'created_at', limit: int = 500) -> Optional[List[Dict[str, Any]]]:
    """Fetch alarms from a Supabase alarm table
    Returns:
        - List (empty or with data) on success
        - None on error (Supabase unavailable, network error, etc.)
    """
    client = get_supabase_client()
    if not client or not client.is_available:
        return None  # Supabase unavailable, fallback to JSON
    
    try:
        url = f"{client._rest_url(table_name)}?select=*&order={order_by}.desc&limit={limit}"
        resp = httpx.get(url, headers=client._headers(), timeout=15)
        if resp.status_code == 200:
            return resp.json()  # Success - may be empty list []
        else:
            print(f"[Supabase] Error fetching {table_name}: {resp.status_code}")
            return None  # Error, fallback to JSON
    except Exception as e:
        print(f"[Supabase] Error fetching {table_name}: {e}")
        return None  # Error, fallback to JSON


def get_sharp_alarms_from_supabase() -> List[Dict[str, Any]]:
    """Get Sharp alarms from Supabase"""
    return fetch_alarms_from_supabase('sharp_alarms')


def get_insider_alarms_from_supabase() -> List[Dict[str, Any]]:
    """Get Insider alarms from Supabase"""
    return fetch_alarms_from_supabase('insider_alarms')


def get_bigmoney_alarms_from_supabase() -> List[Dict[str, Any]]:
    """Get BigMoney alarms from Supabase"""
    return fetch_alarms_from_supabase('bigmoney_alarms')


def get_volumeshock_alarms_from_supabase() -> List[Dict[str, Any]]:
    """Get VolumeShock alarms from Supabase"""
    return fetch_alarms_from_supabase('volumeshock_alarms')


def get_dropping_alarms_from_supabase() -> List[Dict[str, Any]]:
    """Get Dropping alarms from Supabase"""
    return fetch_alarms_from_supabase('dropping_alarms')


def get_volumeleader_alarms_from_supabase() -> List[Dict[str, Any]]:
    """Get VolumeLeader alarms from Supabase"""
    return fetch_alarms_from_supabase('volume_leader_alarms')


def get_mim_alarms_from_supabase() -> List[Dict[str, Any]]:
    """Get MIM (Market Impact Money) alarms from Supabase"""
    return fetch_alarms_from_supabase('mim_alarms')


def delete_alarms_from_supabase(table_name: str) -> bool:
    """Delete all alarms from a Supabase alarm table"""
    client = get_supabase_client()
    if not client or not client.is_available:
        return False
    
    try:
        url = f"{client._rest_url(table_name)}?id=gt.0"
        resp = httpx.delete(url, headers=client._headers(), timeout=15)
        return resp.status_code in [200, 204]
    except Exception as e:
        print(f"[Supabase] Error deleting from {table_name}: {e}")
        return False


def write_alarms_to_supabase(table_name: str, alarms: List[Dict[str, Any]], clear_first: bool = False, on_conflict: str = None) -> bool:
    """Write alarms to a Supabase alarm table using UPSERT
    
    Args:
        table_name: Name of the alarm table (e.g., 'insider_alarms')
        alarms: List of alarm dictionaries to write
        clear_first: If True, delete existing alarms before inserting new ones
        on_conflict: Comma-separated column names for upsert (e.g., 'home,away,market,selection')
    
    Returns:
        True if successful, False otherwise
    """
    client = get_supabase_client()
    if not client or not client.is_available:
        print(f"[Supabase] Cannot write to {table_name}: client not available")
        return False
    
    try:
        # Try to clear existing alarms if requested (ignore errors due to RLS)
        if clear_first:
            delete_alarms_from_supabase(table_name)
        
        if not alarms:
            print(f"[Supabase] No alarms to write to {table_name}")
            return True
        
        # Prepare alarms for insert (remove 'id' field if exists, Supabase auto-generates)
        clean_alarms = []
        for alarm in alarms:
            clean_alarm = {k: v for k, v in alarm.items() if k != 'id'}
            clean_alarms.append(clean_alarm)
        
        # Deduplicate alarms by on_conflict keys (keep last occurrence)
        if on_conflict:
            conflict_keys = [k.strip() for k in on_conflict.split(',')]
            seen = {}
            for alarm in clean_alarms:
                key = tuple(alarm.get(k, '') for k in conflict_keys)
                seen[key] = alarm  # Last one wins
            clean_alarms = list(seen.values())
            print(f"[Supabase] Deduplicated to {len(clean_alarms)} unique alarms for {table_name}")
        
        # UPSERT in batches of 100 (on conflict = update)
        batch_size = 100
        for i in range(0, len(clean_alarms), batch_size):
            batch = clean_alarms[i:i + batch_size]
            
            # Build URL with on_conflict parameter for upsert
            base_url = client._rest_url(table_name)
            if on_conflict:
                url = f"{base_url}?on_conflict={on_conflict}"
            else:
                url = base_url
            
            headers = client._headers()
            headers['Prefer'] = 'resolution=merge-duplicates,return=minimal'
            
            resp = httpx.post(url, headers=headers, json=batch, timeout=30)
            if resp.status_code not in [200, 201]:
                print(f"[Supabase] Error writing batch to {table_name}: {resp.status_code} - {resp.text[:200]}")
                return False
        
        print(f"[Supabase] Wrote {len(clean_alarms)} alarms to {table_name}")
        return True
        
    except Exception as e:
        print(f"[Supabase] Error writing to {table_name}: {e}")
        return False


def write_insider_alarms_to_supabase(alarms: List[Dict[str, Any]]) -> bool:
    """Write Insider alarms to Supabase - ADMIN.EXE ALANLARI"""
    import json as json_module
    mapped_alarms = []
    for alarm in alarms:
        snapshot_data = alarm.get('surrounding_snapshots') or []
        if isinstance(snapshot_data, str):
            try:
                snapshot_data = json_module.loads(snapshot_data)
            except:
                snapshot_data = []
        
        mapped = {
            'match_id': alarm.get('match_id', ''),
            'match_id_hash': alarm.get('match_id_hash', ''),
            'home': alarm.get('home', ''),
            'away': alarm.get('away', ''),
            'league': alarm.get('league', ''),
            'market': alarm.get('market', ''),
            'selection': alarm.get('selection', ''),
            'odds_drop_pct': alarm.get('odds_drop_pct', 0),
            'max_odds_drop': alarm.get('max_odds_drop', 0),
            'incoming_money': alarm.get('incoming_money', 0),
            'volume_shock': alarm.get('volume_shock', 0),
            'opening_odds': alarm.get('opening_odds'),
            'current_odds': alarm.get('current_odds'),
            'drop_moment_index': alarm.get('drop_moment_index'),
            'drop_moment': alarm.get('drop_moment', ''),
            'surrounding_snapshots': snapshot_data,
            'snapshot_count': alarm.get('snapshot_count', 0),
            'match_date': alarm.get('match_date', ''),
            'trigger_at': alarm.get('trigger_at', ''),
            'created_at': alarm.get('created_at', ''),
            'alarm_type': alarm.get('alarm_type', 'insider')
        }
        mapped_alarms.append(mapped)
    return write_alarms_to_supabase('insider_alarms', mapped_alarms, on_conflict='home,away,market,selection')


def write_sharp_alarms_to_supabase(alarms: List[Dict[str, Any]]) -> bool:
    """Write Sharp alarms to Supabase - ADMIN.EXE ALANLARI"""
    import json as json_module
    mapped_alarms = []
    for alarm in alarms:
        weights_data = alarm.get('weights')
        if isinstance(weights_data, dict):
            weights_data = json_module.dumps(weights_data)
        
        mapped = {
            'match_id': alarm.get('match_id', ''),
            'match_id_hash': alarm.get('match_id_hash', ''),
            'home': alarm.get('home', ''),
            'away': alarm.get('away', ''),
            'league': alarm.get('league', ''),
            'market': alarm.get('market', ''),
            'selection': alarm.get('selection', ''),
            'sharp_score': alarm.get('sharp_score', 0),
            'odds_drop_pct': alarm.get('odds_drop_pct', 0),
            'volume_shock_multiplier': alarm.get('volume_shock_multiplier', 0),
            'share_change': alarm.get('share_change', 0),
            'weights': weights_data,
            'volume_contrib': alarm.get('volume_contrib', 0),
            'odds_contrib': alarm.get('odds_contrib', 0),
            'share_contrib': alarm.get('share_contrib', 0),
            'incoming_money': alarm.get('incoming_money', 0),
            'opening_odds': alarm.get('opening_odds'),
            'previous_odds': alarm.get('previous_odds'),
            'current_odds': alarm.get('current_odds'),
            'previous_share': alarm.get('previous_share'),
            'current_share': alarm.get('current_share'),
            'match_date': alarm.get('match_date', ''),
            'trigger_at': alarm.get('trigger_at', ''),
            'created_at': alarm.get('created_at', ''),
            'alarm_type': alarm.get('alarm_type', 'sharp')
        }
        mapped_alarms.append(mapped)
    return write_alarms_to_supabase('sharp_alarms', mapped_alarms, on_conflict='home,away,market,selection')


def write_volumeleader_alarms_to_supabase(alarms: List[Dict[str, Any]]) -> bool:
    """Write VolumeLeader alarms to Supabase - ADMIN.EXE ALANLARI"""
    mapped_alarms = []
    for alarm in alarms:
        mapped = {
            'match_id': alarm.get('match_id', ''),
            'match_id_hash': alarm.get('match_id_hash', ''),
            'home': alarm.get('home', ''),
            'away': alarm.get('away', ''),
            'league': alarm.get('league', ''),
            'market': alarm.get('market', ''),
            'old_leader': alarm.get('old_leader', ''),
            'old_leader_share': alarm.get('old_leader_share', 0),
            'new_leader': alarm.get('new_leader', ''),
            'new_leader_share': alarm.get('new_leader_share', 0),
            'total_volume': alarm.get('total_volume', 0),
            'match_date': alarm.get('match_date', ''),
            'trigger_at': alarm.get('trigger_at', ''),
            'created_at': alarm.get('created_at', ''),
            'alarm_type': alarm.get('alarm_type', 'volumeleader')
        }
        mapped_alarms.append(mapped)
    return write_alarms_to_supabase('volume_leader_alarms', mapped_alarms, on_conflict='home,away,market,old_leader,new_leader')


def write_bigmoney_alarms_to_supabase(alarms: List[Dict[str, Any]]) -> bool:
    """Write BigMoney alarms to Supabase - ADMIN.EXE ALANLARI"""
    mapped_alarms = []
    for alarm in alarms:
        mapped = {
            'match_id': alarm.get('match_id', ''),
            'match_id_hash': alarm.get('match_id_hash', ''),
            'home': alarm.get('home', ''),
            'away': alarm.get('away', ''),
            'league': alarm.get('league', ''),
            'market': alarm.get('market', ''),
            'selection': alarm.get('selection', ''),
            'incoming_money': alarm.get('incoming_money', 0),
            'selection_total': alarm.get('selection_total', 0),
            'is_huge': alarm.get('is_huge', False),
            'huge_total': alarm.get('huge_total', 0),
            'alarm_type': alarm.get('alarm_type', 'BIG MONEY'),
            'match_date': alarm.get('match_date', ''),
            'trigger_at': alarm.get('trigger_at', ''),
            'created_at': alarm.get('created_at', '')
        }
        mapped_alarms.append(mapped)
    return write_alarms_to_supabase('bigmoney_alarms', mapped_alarms, on_conflict='home,away,market,selection,trigger_at')


def write_dropping_alarms_to_supabase(alarms: List[Dict[str, Any]]) -> bool:
    """Write Dropping alarms to Supabase - ADMIN.EXE ALANLARI"""
    mapped_alarms = []
    for alarm in alarms:
        mapped = {
            'match_id': alarm.get('match_id', ''),
            'match_id_hash': alarm.get('match_id_hash', ''),
            'home': alarm.get('home', ''),
            'away': alarm.get('away', ''),
            'league': alarm.get('league', ''),
            'market': alarm.get('market', ''),
            'selection': alarm.get('selection', ''),
            'opening_odds': alarm.get('opening_odds'),
            'current_odds': alarm.get('current_odds'),
            'odds_drop_pct': alarm.get('odds_drop_pct', 0),
            'level': alarm.get('level', ''),
            'match_date': alarm.get('match_date', ''),
            'trigger_at': alarm.get('trigger_at', ''),
            'created_at': alarm.get('created_at', ''),
            'alarm_type': alarm.get('alarm_type', 'dropping')
        }
        mapped_alarms.append(mapped)
    return write_alarms_to_supabase('dropping_alarms', mapped_alarms, on_conflict='home,away,market,selection')


def write_volumeshock_alarms_to_supabase(alarms: List[Dict[str, Any]]) -> bool:
    """Write VolumeShock alarms to Supabase - ADMIN.EXE ALANLARI"""
    mapped_alarms = []
    for alarm in alarms:
        mapped = {
            'match_id': alarm.get('match_id', ''),
            'match_id_hash': alarm.get('match_id_hash', ''),
            'home': alarm.get('home', ''),
            'away': alarm.get('away', ''),
            'league': alarm.get('league', ''),
            'market': alarm.get('market', ''),
            'selection': alarm.get('selection', ''),
            'volume_shock': alarm.get('volume_shock', 0),
            'volume_shock_multiplier': alarm.get('volume_shock_multiplier', 0),
            'incoming_money': alarm.get('incoming_money', 0),
            'avg_previous': alarm.get('avg_previous', 0),
            'match_date': alarm.get('match_date', ''),
            'trigger_at': alarm.get('trigger_at', ''),
            'created_at': alarm.get('created_at', ''),
            'alarm_type': alarm.get('alarm_type', 'volumeshock')
        }
        mapped_alarms.append(mapped)
    return write_alarms_to_supabase('volumeshock_alarms', mapped_alarms, on_conflict='home,away,market,selection')
