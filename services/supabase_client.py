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
        try:
            import embedded_config
            self.url = getattr(embedded_config, 'EMBEDDED_SUPABASE_URL', '')
            self.key = getattr(embedded_config, 'EMBEDDED_SUPABASE_KEY', '')
        except (ImportError, AttributeError):
            pass
        
        if not self.url:
            self.url = os.getenv('SUPABASE_URL', '')
        if not self.key:
            self.key = os.getenv('SUPABASE_ANON_KEY', '') or os.getenv('SUPABASE_KEY', '')
    
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
        if not self.is_available:
            return []
        
        try:
            match_url = f"{self._rest_url('matches')}?home_team=eq.{home_team}&away_team=eq.{away_team}&select=id"
            resp = httpx.get(match_url, headers=self._headers(), timeout=10)
            
            if resp.status_code != 200 or not resp.json():
                return []
            
            match_id = resp.json()[0]['id']
            
            snap_url = f"{self._rest_url('odds_snapshots')}?match_id=eq.{match_id}&market=eq.{market}&select=*&order=scraped_at.asc"
            resp = httpx.get(snap_url, headers=self._headers(), timeout=10)
            
            if resp.status_code == 200:
                snapshots = resp.json()
                return [self._snapshot_to_legacy(s, market) for s in snapshots]
            return []
        except Exception as e:
            print(f"Error get_match_history: {e}")
            return []
    
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


_database = None


def get_database() -> HybridDatabase:
    global _database
    if _database is None:
        _database = HybridDatabase()
    return _database


def get_supabase_client():
    return get_database().supabase if get_database().is_supabase_available else None
