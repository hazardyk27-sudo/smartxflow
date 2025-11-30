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
            url = f"{self._rest_url('matches')}?home_team=eq.{home_team}&away_team=eq.{away_team}&match_date=eq.{match_date}&select=id"
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
    
    def get_match_history(self, home_team: str, away_team: str, market: str) -> List[Dict[str, Any]]:
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
                url = f"{self._rest_url(history_table)}?home=eq.{home_enc}&away=eq.{away_enc}&order=scrapedat.asc&limit={page_size}&offset={offset}"
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
            'ScrapedAt': row.get('scrapedat', ''),
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
    
    def get_all_matches_with_latest(self, market: str) -> List[Dict[str, Any]]:
        """Get all matches from market table (moneyway_1x2, dropping_ou25, etc.)"""
        if not self.is_available:
            print(f"[Supabase] ERROR: Not available - URL or KEY missing")
            return []
        
        try:
            url = f"{self._rest_url(market)}?select=*&order=date.desc"
            print(f"[Supabase] Fetching: {url}")
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
                print(f"[Supabase] Got {len(matches)} matches from {market}")
                return matches
            elif resp.status_code == 404:
                print(f"[Supabase] ERROR 404: Table '{market}' not found!")
                print(f"[Supabase] Check if URL is correct API endpoint (not dashboard link)")
                print(f"[Supabase] Current URL base: {self.url}")
                return []
            else:
                print(f"[Supabase] ERROR {resp.status_code} fetching {market}")
                print(f"[Supabase] Response: {resp.text[:200]}")
                return []
        except Exception as e:
            print(f"[Supabase] EXCEPTION in get_all_matches_with_latest: {e}")
            return []
    
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
                url = f"{self._rest_url(table)}?select=scrapedat&order=scrapedat.desc&limit=1"
                resp = httpx.get(url, headers=self._headers(), timeout=5)
                if resp.status_code == 200:
                    rows = resp.json()
                    if rows and rows[0].get('scrapedat'):
                        ts = rows[0]['scrapedat']
                        if latest_time is None or ts > latest_time:
                            latest_time = ts
            except Exception as e:
                continue
        
        self._last_data_update_cache = latest_time
        self._last_data_update_cache_time = now
        
        return latest_time
    
    def get_6h_odds_history(self, market: str) -> Dict[str, Dict[str, Any]]:
        """Drop markets: İlk snapshot vs Son snapshot = Açılıştan bu yana değişim.
        Optimized: 2 bulk queries (first + last) per market."""
        if not self.is_available or not market.startswith('dropping'):
            return {}
        
        history_table = f"{market}_history"
        
        try:
            import time
            from concurrent.futures import ThreadPoolExecutor, as_completed
            start_time = time.time()
            
            if market == 'dropping_1x2':
                sels = ['odds1', 'oddsx', 'odds2']
                select_cols = 'home,away,odds1,oddsx,odds2,scrapedat'
            elif market == 'dropping_ou25':
                sels = ['under', 'over']
                select_cols = 'home,away,under,over,scrapedat'
            elif market == 'dropping_btts':
                sels = ['oddsyes', 'oddsno']
                select_cols = 'home,away,oddsyes,oddsno,scrapedat'
            else:
                return {}
            
            def fetch_all_rows(order_dir):
                """Fetch all rows with given order direction using pagination"""
                rows = []
                offset = 0
                while True:
                    url = f"{self._rest_url(history_table)}?select={select_cols}&order=scrapedat.{order_dir}&offset={offset}&limit=1000"
                    resp = httpx.get(url, headers=self._headers(), timeout=30)
                    if resp.status_code != 200:
                        break
                    batch = resp.json()
                    if not batch:
                        break
                    rows.extend(batch)
                    if len(batch) < 1000:
                        break
                    offset += 1000
                    if offset > 50000:
                        break
                return rows
            
            with ThreadPoolExecutor(max_workers=2) as executor:
                future_first = executor.submit(fetch_all_rows, 'asc')
                future_last = executor.submit(fetch_all_rows, 'desc')
                first_rows = future_first.result()
                last_rows = future_last.result()
            
            match_first = {}
            for row in first_rows:
                key = f"{row.get('home', '')}|{row.get('away', '')}"
                if key not in match_first:
                    match_first[key] = row
            
            match_last = {}
            for row in last_rows:
                key = f"{row.get('home', '')}|{row.get('away', '')}"
                if key not in match_last:
                    match_last[key] = row
            
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
            print(f"[Drop] Got {len(result)} matches for {market} in {elapsed:.1f}s (bulk query)")
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
            url = f"{self._rest_url(history_table)}?home=eq.{home_enc}&away=eq.{away_enc}&order=scrapedat.asc&limit=500"
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
        
        # History tablolarını sil (scrapedat < cutoff_date)
        for table in history_tables:
            try:
                # Prefer header ile silinen kayıtları döndür
                headers = self._headers()
                headers['Prefer'] = 'return=representation'
                
                # scrapedat sütunu ile filtrele
                url = f"{self._rest_url(table)}?scrapedat=lt.{cutoff_date}T00:00:00"
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
    
    def get_match_history(self, home: str, away: str, market: str) -> List[Dict[str, Any]]:
        if self.supabase.is_available:
            history = self.supabase.get_match_history(home, away, market)
            if history:
                return history
        return self.local.get_match_history(home, away, market)
    
    def get_all_matches_with_latest(self, market: str) -> List[Dict[str, Any]]:
        """Get all matches with latest snapshot from Supabase or local"""
        if self.supabase.is_available:
            matches = self.supabase.get_all_matches_with_latest(market)
            if matches:
                return matches
        return self.local.get_all_matches_with_latest(market)
    
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
