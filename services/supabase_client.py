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
        self._load_credentials()
    
    def _load_credentials(self):
        # Method 1: Try services/embedded_credentials.py (created by build.yml)
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
        
        # Method 2: Try embedded_config.py (legacy)
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
        
        # Method 3: Environment variables (Replit)
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
        
        # Check for common URL errors
        if 'dashboard' in self.url.lower():
            print(f"[Supabase] ERROR: URL contains 'dashboard' - this is NOT an API URL!")
            print(f"[Supabase] ERROR: Use https://<project-ref>.supabase.co instead")
            self.url = None  # Invalidate
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
    
    def save_alert(self, match_id: int, alert_type: str, market: str, side: str, 
                   money_diff: float = 0, odds_from: float = None, odds_to: float = None,
                   details: Dict = None) -> bool:
        if not self.is_available:
            return False
        
        try:
            data = {
                "match_id": match_id,
                "alert_type": alert_type,
                "market": market,
                "side": side,
                "money_diff": money_diff,
                "odds_from": odds_from,
                "odds_to": odds_to,
                "details": json.dumps(details) if details else None,
                "is_active": True
            }
            resp = httpx.post(self._rest_url('alerts'), headers=self._headers(), json=data, timeout=10)
            return resp.status_code in [200, 201]
        except Exception as e:
            print(f"Error save_alert: {e}")
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
        """
        Get history for a specific match with pagination to handle 1000 row limit.
        """
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
    
    def get_bulk_history_for_alarms(self, market: str, match_pairs: List[tuple], lookback_hours: int = 48) -> Dict[tuple, List[Dict]]:
        """
        Fetch history for each match individually to ensure complete data.
        Uses batch queries with OR conditions and pagination to handle 1000 row limit.
        
        Args:
            market: Market type (moneyway_1x2, etc.)
            match_pairs: List of (home, away) tuples
            lookback_hours: How far back to look (default 48 = 2 days, performans için azaltıldı)
        
        Returns: {(home, away): [history_records]}
        """
        if not self.is_available or not match_pairs:
            return {}
        
        try:
            from datetime import datetime, timedelta
            import urllib.parse
            
            history_table = f"{market}_history"
            cutoff = (datetime.utcnow() - timedelta(hours=lookback_hours)).isoformat()
            
            result = {}
            total_rows = 0
            batch_size = 10
            page_size = 1000
            max_pages_per_batch = 5
            
            for i in range(0, len(match_pairs), batch_size):
                batch = match_pairs[i:i+batch_size]
                
                or_conditions = []
                for home, away in batch:
                    home_enc = urllib.parse.quote(home, safe='')
                    away_enc = urllib.parse.quote(away, safe='')
                    or_conditions.append(f"and(home.eq.{home_enc},away.eq.{away_enc})")
                
                or_query = ",".join(or_conditions)
                
                offset = 0
                for page in range(max_pages_per_batch):
                    url = f"{self._rest_url(history_table)}?or=({or_query})&scrapedat=gte.{cutoff}&order=scrapedat.asc&limit={page_size}&offset={offset}"
                    
                    headers = self._headers()
                    resp = httpx.get(url, headers=headers, timeout=60)
                    
                    if resp.status_code != 200:
                        break
                    
                    rows = resp.json()
                    if not rows:
                        break
                    
                    total_rows += len(rows)
                    
                    for row in rows:
                        key = (row.get('home', ''), row.get('away', ''))
                        if key not in result:
                            result[key] = []
                        result[key].append(self._history_row_to_legacy(row, market))
                    
                    if len(rows) < page_size:
                        break
                    
                    offset += page_size
            
            print(f"[Supabase] Bulk history ({market}): {total_rows} rows ({lookback_hours}h lookback), {len(result)} matches")
            return result
        except Exception as e:
            print(f"[Supabase] Error in get_bulk_history_for_alarms: {e}")
            import traceback
            traceback.print_exc()
            return {}
    
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
        """Get the most recent ScrapedAt timestamp from history tables"""
        if not self.is_available:
            return None
        
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
        
        return latest_time
    
    def get_active_alerts(self, limit: int = 50) -> List[Dict[str, Any]]:
        if not self.is_available:
            return []
        
        try:
            url = f"{self._rest_url('alerts')}?is_active=eq.true&select=*,matches(home_team,away_team,league)&order=created_at.desc&limit={limit}"
            resp = httpx.get(url, headers=self._headers(), timeout=10)
            if resp.status_code == 200:
                return resp.json()
            return []
        except Exception as e:
            print(f"Error get_active_alerts: {e}")
            return []
    
    def get_6h_odds_history(self, market: str) -> Dict[str, Dict[str, Any]]:
        """Get odds history for DROP markets (last 14 days).
        Returns dict: { "home|away": { "sel1": [values], "sel2": [values], ... } }
        """
        if not self.is_available:
            return {}
        
        if not market.startswith('dropping'):
            return {}
        
        history_table = f"{market}_history"
        
        try:
            from datetime import datetime, timedelta
            import pytz
            
            turkey_tz = pytz.timezone('Europe/Istanbul')
            now_turkey = datetime.now(turkey_tz)
            # 14 gün geriye git
            fourteen_days_ago = now_turkey - timedelta(days=14)
            cutoff_iso = fourteen_days_ago.strftime('%Y-%m-%d %H:%M:%S')
            
            all_rows = []
            offset = 0
            page_size = 1000
            max_pages = 50  # 14 gün için yeterli sayfa
            
            for page in range(max_pages):
                url = f"{self._rest_url(history_table)}?scrapedat=gte.{cutoff_iso}&order=scrapedat.asc&limit={page_size}&offset={offset}"
                resp = httpx.get(url, headers=self._headers(), timeout=30)
                
                if resp.status_code != 200:
                    print(f"[6h History] Error {resp.status_code} from {history_table}")
                    break
                
                rows = resp.json()
                if not rows:
                    break
                
                all_rows.extend(rows)
                
                if len(rows) < page_size:
                    break
                
                offset += page_size
            
            print(f"[6h History] Fetched {len(all_rows)} total rows from {history_table}")
            
            if not all_rows:
                return {}
            
            rows = all_rows
            
            result = {}
            
            for row in rows:
                home = row.get('home', '')
                away = row.get('away', '')
                key = f"{home}|{away}"
                
                if key not in result:
                    result[key] = {
                        'home': home,
                        'away': away,
                        'timestamps': [],
                        'values': {}
                    }
                
                ts = row.get('scrapedat', '')
                result[key]['timestamps'].append(ts)
                
                if market == 'dropping_1x2':
                    for sel in ['odds1', 'oddsx', 'odds2']:
                        if sel not in result[key]['values']:
                            result[key]['values'][sel] = []
                        val = self._parse_numeric(row.get(sel, ''))
                        result[key]['values'][sel].append(val)
                        
                elif market == 'dropping_ou25':
                    for sel in ['under', 'over']:
                        if sel not in result[key]['values']:
                            result[key]['values'][sel] = []
                        val = self._parse_numeric(row.get(sel, ''))
                        result[key]['values'][sel].append(val)
                        
                elif market == 'dropping_btts':
                    for sel in ['yes', 'no']:
                        if sel not in result[key]['values']:
                            result[key]['values'][sel] = []
                        val = self._parse_numeric(row.get(sel, row.get('odds' + sel, '')))
                        result[key]['values'][sel].append(val)
            
            for key in result:
                data = result[key]
                timestamps = data.get('timestamps', [])
                first_scraped = timestamps[0] if timestamps else None
                
                for sel, values in data['values'].items():
                    valid_values = [v for v in values if v is not None]
                    if len(valid_values) >= 2:
                        old_val = valid_values[0]
                        new_val = valid_values[-1]
                        if old_val > 0:
                            pct_change = ((new_val - old_val) / old_val) * 100
                            if new_val < old_val:
                                trend = 'down'
                            elif new_val > old_val:
                                trend = 'up'
                            else:
                                trend = 'stable'
                        else:
                            pct_change = 0
                            trend = 'stable'
                        
                        data['values'][sel] = {
                            'history': valid_values[-10:],
                            'old': old_val,
                            'new': new_val,
                            'pct_change': round(pct_change, 1),
                            'trend': trend,
                            'first_scraped': first_scraped
                        }
                    else:
                        data['values'][sel] = {
                            'history': valid_values,
                            'old': valid_values[0] if valid_values else None,
                            'new': valid_values[-1] if valid_values else None,
                            'pct_change': 0,
                            'trend': 'stable',
                            'first_scraped': first_scraped
                        }
            
            print(f"[6h History] Got {len(result)} matches from {history_table}")
            return result
            
        except Exception as e:
            print(f"[6h History] Error: {e}")
            import traceback
            traceback.print_exc()
            return {}
    
    def _parse_numeric(self, val: Any) -> Optional[float]:
        if val is None or val == '' or val == '-':
            return None
        try:
            return float(str(val).replace(',', '.').split('\n')[0])
        except:
            return None
    
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
    
    def save_smart_money_alarm(self, alarm: Dict[str, Any]) -> bool:
        """
        Save a smart money alarm to persistent storage.
        Uses odds-based deduplication to prevent duplicate alarms for same price movement.
        
        Deduplication strategy: match_id + alarm_type + side + odds_from + odds_to
        This ensures each unique price movement generates only one alarm.
        """
        if not self.is_available:
            return False
        
        try:
            match_id = alarm.get('match_id', '')
            alarm_type = alarm.get('type', '')
            side = alarm.get('side', '')
            odds_from = alarm.get('odds_from')
            odds_to = alarm.get('odds_to')
            
            check_url = f"{self._rest_url('smart_money_alarms')}?match_id=eq.{match_id}&alarm_type=eq.{alarm_type}&side=eq.{side}"
            if odds_from is not None:
                check_url += f"&odds_from=eq.{odds_from}"
            if odds_to is not None:
                check_url += f"&odds_to=eq.{odds_to}"
            
            check_resp = httpx.get(check_url, headers=self._headers(), timeout=5)
            if check_resp.status_code == 200:
                existing = check_resp.json()
                if existing:
                    return True
            
            window_start = alarm.get('window_start', '')
            if window_start and len(window_start) >= 16:
                try:
                    minute = int(window_start[14:16])
                    bucket_minute = (minute // 10) * 10
                    window_start_truncated = f"{window_start[:14]}{bucket_minute:02d}:00"
                except ValueError:
                    window_start_truncated = window_start[:16] + ':00'
            elif window_start and len(window_start) >= 13:
                window_start_truncated = window_start[:13] + ':00:00'
            else:
                window_start_truncated = window_start
            
            data = {
                'match_id': match_id,
                'home': alarm.get('home', ''),
                'away': alarm.get('away', ''),
                'league': alarm.get('league', ''),
                'match_date': alarm.get('match_date', ''),
                'market': alarm.get('market', ''),
                'alarm_type': alarm_type,
                'side': side,
                'money_diff': alarm.get('money_diff', 0),
                'odds_from': odds_from,
                'odds_to': odds_to,
                'detail': alarm.get('detail', ''),
                'window_start': window_start_truncated,
                'window_end': alarm.get('window_end', ''),
                'triggered_at': alarm.get('timestamp', '')
            }
            
            url = f"{self._rest_url('smart_money_alarms')}"
            headers = self._headers()
            headers['Prefer'] = 'resolution=ignore-duplicates'
            
            resp = httpx.post(url, headers=headers, json=data, timeout=10)
            
            if resp.status_code in [200, 201, 409]:
                return True
            else:
                print(f"[SaveAlarm] Error {resp.status_code}: {resp.text[:200]}")
                return False
                
        except Exception as e:
            print(f"[SaveAlarm] Exception: {e}")
            return False
    
    def cleanup_duplicate_alarms(self) -> int:
        """
        Remove duplicate alarms from database.
        Keeps only one alarm per match_id + alarm_type + side + odds_from + odds_to combination.
        Returns count of deleted duplicates.
        """
        if not self.is_available:
            return 0
        
        try:
            url = f"{self._rest_url('smart_money_alarms')}?select=*&order=triggered_at.desc"
            resp = httpx.get(url, headers=self._headers(), timeout=15)
            
            if resp.status_code != 200:
                return 0
            
            alarms = resp.json()
            seen = {}
            duplicates = []
            
            for alarm in alarms:
                key = (
                    alarm.get('match_id', ''),
                    alarm.get('alarm_type', ''),
                    alarm.get('side', ''),
                    str(alarm.get('odds_from', '')),
                    str(alarm.get('odds_to', ''))
                )
                
                if key in seen:
                    duplicates.append(alarm.get('id'))
                else:
                    seen[key] = alarm.get('id')
            
            deleted = 0
            for dup_id in duplicates:
                if dup_id:
                    del_url = f"{self._rest_url('smart_money_alarms')}?id=eq.{dup_id}"
                    del_resp = httpx.delete(del_url, headers=self._headers(), timeout=5)
                    if del_resp.status_code in [200, 204]:
                        deleted += 1
            
            if deleted > 0:
                print(f"[CleanupDuplicates] Removed {deleted} duplicate alarms")
            
            return deleted
            
        except Exception as e:
            print(f"[CleanupDuplicates] Exception: {e}")
            return 0
    
    def cleanup_low_drop_percent_alarms(self, threshold: float = 7.0) -> int:
        """
        Remove dropping alarms with drop_percent below threshold (default 7%).
        Only affects 'dropping' type alarms.
        Returns count of deleted alarms.
        """
        if not self.is_available:
            return 0
        
        try:
            url = f"{self._rest_url('smart_money_alarms')}?select=*&alarm_type=eq.dropping"
            resp = httpx.get(url, headers=self._headers(), timeout=15)
            
            if resp.status_code != 200:
                print(f"[CleanupLowDrop] Error fetching alarms: {resp.status_code}")
                return 0
            
            alarms = resp.json()
            print(f"[CleanupLowDrop] Found {len(alarms)} dropping alarms to check")
            
            to_delete = []
            for alarm in alarms:
                drop_percent = alarm.get('drop_percent')
                
                should_delete = False
                if drop_percent is None:
                    should_delete = True
                else:
                    try:
                        if float(drop_percent) < threshold:
                            should_delete = True
                    except:
                        should_delete = True
                
                if should_delete:
                    dp_val = drop_percent if drop_percent is not None else 0
                    to_delete.append({
                        'id': alarm.get('id'),
                        'home': alarm.get('home', ''),
                        'away': alarm.get('away', ''),
                        'side': alarm.get('side', ''),
                        'drop_percent': dp_val
                    })
            
            print(f"[CleanupLowDrop] {len(to_delete)} alarms below {threshold}% threshold will be deleted")
            
            deleted = 0
            for alarm in to_delete:
                alarm_id = alarm.get('id')
                if alarm_id:
                    del_url = f"{self._rest_url('smart_money_alarms')}?id=eq.{alarm_id}"
                    del_resp = httpx.delete(del_url, headers=self._headers(), timeout=5)
                    if del_resp.status_code in [200, 204]:
                        deleted += 1
                        print(f"  - Deleted: {alarm['home']} vs {alarm['away']} ({alarm['side']}) - {alarm['drop_percent']:.1f}%")
            
            print(f"[CleanupLowDrop] Successfully deleted {deleted} low drop% alarms")
            return deleted
            
        except Exception as e:
            print(f"[CleanupLowDrop] Exception: {e}")
            return 0
    
    def cleanup_legacy_alarms(self) -> int:
        """
        Remove legacy alarms that don't meet new criteria:
        - Old 'dropping' type alarms (new format: dropping_l1, dropping_l2, dropping_l3)
        - Sharp alarms with score < 20 (yeni eşik)
        - Reversal alarms with conditions_met < 3
        Returns count of deleted alarms.
        """
        if not self.is_available:
            return 0
        
        try:
            url = f"{self._rest_url('smart_money_alarms')}?select=*"
            resp = httpx.get(url, headers=self._headers(), timeout=15)
            
            if resp.status_code != 200:
                print(f"[CleanupLegacy] Error fetching alarms: {resp.status_code}")
                return 0
            
            alarms = resp.json()
            print(f"[CleanupLegacy] Found {len(alarms)} total alarms to check")
            
            to_delete = []
            for alarm in alarms:
                alarm_type = alarm.get('alarm_type', '')
                sharp_score = alarm.get('sharp_score') or 0
                
                try:
                    sharp_score = float(sharp_score)
                except:
                    sharp_score = 0
                
                should_delete = False
                reason = ""
                
                if alarm_type == 'dropping':
                    should_delete = True
                    reason = "old dropping format"
                elif alarm_type == 'sharp' and sharp_score < 20:
                    should_delete = True
                    reason = f"sharp score {sharp_score} < 20"
                elif alarm_type == 'reversal_move':
                    conditions_met = alarm.get('conditions_met')
                    try:
                        conditions_met = int(conditions_met) if conditions_met is not None else 0
                    except:
                        conditions_met = 0
                    if conditions_met < 3:
                        should_delete = True
                        reason = f"reversal conditions {conditions_met}/3 < 3"
                
                if should_delete:
                    to_delete.append({
                        'id': alarm.get('id'),
                        'home': alarm.get('home', ''),
                        'away': alarm.get('away', ''),
                        'type': alarm_type,
                        'reason': reason
                    })
            
            print(f"[CleanupLegacy] {len(to_delete)} legacy alarms will be deleted")
            
            deleted = 0
            for alarm in to_delete:
                alarm_id = alarm.get('id')
                if alarm_id:
                    del_url = f"{self._rest_url('smart_money_alarms')}?id=eq.{alarm_id}"
                    del_resp = httpx.delete(del_url, headers=self._headers(), timeout=5)
                    if del_resp.status_code in [200, 204]:
                        deleted += 1
                        print(f"  - Deleted: {alarm['home']} vs {alarm['away']} ({alarm['type']}) - {alarm['reason']}")
            
            print(f"[CleanupLegacy] Successfully deleted {deleted} legacy alarms")
            return deleted
            
        except Exception as e:
            print(f"[CleanupLegacy] Exception: {e}")
            return 0
    
    def get_persistent_alarms(self, match_date_filter: str = 'today_future') -> List[Dict[str, Any]]:
        """
        Get all persistent alarms for matches that are today or in the future.
        This is the source of truth for alarm visibility.
        
        Args:
            match_date_filter: 'today_future' (default), 'all', or specific date
        """
        if not self.is_available:
            return []
        
        try:
            url = f"{self._rest_url('smart_money_alarms')}?select=*&order=triggered_at.desc"
            resp = httpx.get(url, headers=self._headers(), timeout=15)
            
            if resp.status_code == 200:
                alarms = resp.json()
                print(f"[PersistentAlarms] Got {len(alarms)} alarms from database")
                return alarms
            elif resp.status_code == 404:
                print(f"[PersistentAlarms] Table not found - creating...")
                return []
            else:
                print(f"[PersistentAlarms] Error {resp.status_code}")
                return []
                
        except Exception as e:
            print(f"[PersistentAlarms] Exception: {e}")
            return []
    
    def save_alarms_batch(self, alarms: List[Dict[str, Any]]) -> int:
        """
        Save multiple alarms in batch. Returns count of successfully saved.
        """
        if not self.is_available or not alarms:
            return 0
        
        saved = 0
        for alarm in alarms:
            if self.save_smart_money_alarm(alarm):
                saved += 1
        
        if saved > 0:
            print(f"[SaveAlarmsBatch] Saved {saved}/{len(alarms)} alarms")
        
        return saved

    def delete_all_active_alarms(self, include_historical: bool = False) -> int:
        """
        Delete alarms based on scope using BATCH DELETE with pagination.
        
        Args:
            include_historical: If True, delete ALL alarms (including past matches).
                               If False, only delete today+future alarms.
        
        Used when admin recalculates alarms with new config.
        Returns count of deleted alarms.
        
        PERFORMANCE: Uses filter-based DELETE with pagination for >1000 rows.
        """
        if not self.is_available:
            return 0
        
        try:
            from datetime import datetime
            import pytz
            import time
            
            start_time = time.time()
            turkey_tz = pytz.timezone('Europe/Istanbul')
            today = datetime.now(turkey_tz).strftime('%Y-%m-%d')
            
            if include_historical:
                base_filter = ""
                scope_msg = "ALL alarms (including historical)"
            else:
                base_filter = f"match_date=gte.{today}"
                scope_msg = f"active alarms (today+future, >= {today})"
            
            print(f"[DeleteAlarms] Starting BATCH deletion of {scope_msg}...")
            
            count_headers = self._headers()
            count_headers['Prefer'] = 'count=exact'
            count_headers['Range-Unit'] = 'items'
            count_headers['Range'] = '0-0'
            
            count_url = f"{self._rest_url('smart_money_alarms')}?select=id"
            if base_filter:
                count_url += f"&{base_filter}"
            
            count_resp = httpx.get(count_url, headers=count_headers, timeout=30)
            
            total_to_delete = 0
            if 'Content-Range' in count_resp.headers:
                range_header = count_resp.headers['Content-Range']
                if '/' in range_header:
                    total_to_delete = int(range_header.split('/')[-1])
            else:
                count_resp2 = httpx.get(count_url.replace('&limit=', ''), headers=self._headers(), timeout=30)
                if count_resp2.status_code == 200:
                    total_to_delete = len(count_resp2.json())
            
            print(f"[DeleteAlarms] Found {total_to_delete} alarms to delete")
            
            if total_to_delete == 0:
                return 0
            
            total_deleted = 0
            batch_size = 1000
            
            while total_deleted < total_to_delete:
                delete_url = f"{self._rest_url('smart_money_alarms')}?select=id&limit={batch_size}"
                if base_filter:
                    delete_url += f"&{base_filter}"
                
                del_resp = httpx.delete(delete_url, headers=self._headers(), timeout=60)
                
                if del_resp.status_code in [200, 204]:
                    batch_deleted = batch_size
                    if del_resp.status_code == 200:
                        try:
                            deleted_items = del_resp.json()
                            batch_deleted = len(deleted_items) if isinstance(deleted_items, list) else batch_size
                        except:
                            pass
                    
                    total_deleted += batch_deleted
                    print(f"[DeleteAlarms] Batch deleted {batch_deleted}, Total: {total_deleted}")
                    
                    if batch_deleted < batch_size:
                        break
                else:
                    print(f"[DeleteAlarms] Batch delete failed: {del_resp.status_code}, falling back")
                    total_deleted += self._delete_alarms_one_by_one(include_historical)
                    break
            
            elapsed = time.time() - start_time
            print(f"[DeleteAlarms] BATCH deleted {total_deleted} {scope_msg} in {elapsed:.2f}s")
            return total_deleted
            
        except Exception as e:
            print(f"[DeleteAlarms] Exception: {e}")
            return 0

    def _delete_alarms_one_by_one(self, include_historical: bool = False) -> int:
        """Fallback: Delete alarms one by one if batch fails"""
        try:
            from datetime import datetime
            import pytz
            
            turkey_tz = pytz.timezone('Europe/Istanbul')
            today = datetime.now(turkey_tz).strftime('%Y-%m-%d')
            
            total_deleted = 0
            page_size = 1000
            
            while True:
                if include_historical:
                    url = f"{self._rest_url('smart_money_alarms')}?select=id&limit={page_size}"
                else:
                    url = f"{self._rest_url('smart_money_alarms')}?select=id&match_date=gte.{today}&limit={page_size}"
                
                resp = httpx.get(url, headers=self._headers(), timeout=30)
                if resp.status_code != 200:
                    break
                
                alarms = resp.json()
                if not alarms:
                    break
                
                for alarm in alarms:
                    alarm_id = alarm.get('id')
                    if alarm_id:
                        del_url = f"{self._rest_url('smart_money_alarms')}?id=eq.{alarm_id}"
                        del_resp = httpx.delete(del_url, headers=self._headers(), timeout=5)
                        if del_resp.status_code in [200, 204]:
                            total_deleted += 1
                
                if len(alarms) < page_size:
                    break
            
            print(f"[DeleteAlarms] Fallback deleted {total_deleted} alarms one-by-one")
            return total_deleted
            
        except Exception as e:
            print(f"[DeleteAlarms] Fallback exception: {e}")
            return 0

    def delete_alarms_by_type(self, alarm_type: str, include_historical: bool = True) -> int:
        """
        Delete alarms of a specific type only.
        
        Args:
            alarm_type: Base alarm type (e.g., 'sharp', 'momentum', 'dropping')
            include_historical: If True, delete all; if False, only today+future
        
        Returns count of deleted alarms.
        """
        if not self.is_available:
            return 0
        
        try:
            from datetime import datetime
            import pytz
            import time
            
            start_time = time.time()
            turkey_tz = pytz.timezone('Europe/Istanbul')
            today = datetime.now(turkey_tz).strftime('%Y-%m-%d')
            
            type_pattern = f"{alarm_type}%"
            
            count_headers = self._headers()
            count_headers['Prefer'] = 'count=exact'
            count_headers['Range-Unit'] = 'items'
            count_headers['Range'] = '0-0'
            
            if include_historical:
                count_url = f"{self._rest_url('smart_money_alarms')}?select=id&alarm_type=like.{type_pattern}"
            else:
                count_url = f"{self._rest_url('smart_money_alarms')}?select=id&alarm_type=like.{type_pattern}&match_date=gte.{today}"
            
            count_resp = httpx.get(count_url, headers=count_headers, timeout=30)
            
            total_to_delete = 0
            if 'Content-Range' in count_resp.headers:
                range_header = count_resp.headers['Content-Range']
                if '/' in range_header:
                    total_to_delete = int(range_header.split('/')[-1])
            else:
                count_resp2 = httpx.get(count_url, headers=self._headers(), timeout=30)
                if count_resp2.status_code == 200:
                    total_to_delete = len(count_resp2.json())
            
            print(f"[DeleteByType] Found {total_to_delete} '{alarm_type}*' alarms to delete")
            
            if total_to_delete == 0:
                return 0
            
            total_deleted = 0
            batch_size = 1000
            
            while total_deleted < total_to_delete:
                if include_historical:
                    delete_url = f"{self._rest_url('smart_money_alarms')}?alarm_type=like.{type_pattern}&limit={batch_size}"
                else:
                    delete_url = f"{self._rest_url('smart_money_alarms')}?alarm_type=like.{type_pattern}&match_date=gte.{today}&limit={batch_size}"
                
                del_resp = httpx.delete(delete_url, headers=self._headers(), timeout=60)
                
                if del_resp.status_code in [200, 204]:
                    batch_deleted = min(batch_size, total_to_delete - total_deleted)
                    total_deleted += batch_deleted
                    print(f"[DeleteByType] Batch deleted ~{batch_deleted} '{alarm_type}*', Total: {total_deleted}")
                    
                    if batch_deleted < batch_size:
                        break
                else:
                    print(f"[DeleteByType] Delete failed: {del_resp.status_code}")
                    break
            
            elapsed = time.time() - start_time
            print(f"[DeleteByType] Deleted {total_deleted} '{alarm_type}*' alarms in {elapsed:.2f}s")
            return total_deleted
            
        except Exception as e:
            print(f"[DeleteByType] Exception: {e}")
            return 0

    def get_alarm_type_counts(self) -> Dict[str, int]:
        """
        Get count of alarms grouped by type for debugging.
        Returns dict like {'public_surge': 10, 'sharp': 5, ...}
        """
        if not self.is_available:
            return {}
        
        try:
            url = f"{self._rest_url('smart_money_alarms')}?select=type"
            resp = httpx.get(url, headers=self._headers(), timeout=30)
            
            if resp.status_code != 200:
                print(f"[AlarmStats] Error: {resp.status_code}")
                return {}
            
            alarms = resp.json()
            counts = {}
            for alarm in alarms:
                alarm_type = alarm.get('type', 'unknown')
                counts[alarm_type] = counts.get(alarm_type, 0) + 1
            
            return counts
            
        except Exception as e:
            print(f"[AlarmStats] Exception: {e}")
            return {}


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
    
    def get_bulk_history_for_alarms(self, market: str, match_pairs: List[tuple]) -> Dict[tuple, List[Dict]]:
        """Batch fetch history for multiple matches"""
        if self.supabase.is_available:
            return self.supabase.get_bulk_history_for_alarms(market, match_pairs)
        return {}
    
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
    
    def save_alert(self, home: str, away: str, league: str, date: str,
                   alert_type: str, market: str, side: str, 
                   money_diff: float = 0, odds_from: float = None, odds_to: float = None) -> bool:
        if not self.supabase.is_available:
            return False
        
        match_id = self.supabase.get_or_create_match(home, away, league, date)
        if match_id:
            return self.supabase.save_alert(match_id, alert_type, market, side, money_diff, odds_from, odds_to)
        return False
    
    def get_active_alerts(self) -> List[Dict[str, Any]]:
        if self.supabase.is_available:
            return self.supabase.get_active_alerts()
        return []
    
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
