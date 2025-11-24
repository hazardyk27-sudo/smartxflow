"""
SmartXFlow Supabase Client
Handles database operations for matches and market snapshots
"""

import os
import sqlite3
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

_SUPABASE_AVAILABLE = False
_supabase_client = None

try:
    from supabase import create_client
    _SUPABASE_AVAILABLE = True
except ImportError:
    pass


def get_supabase_credentials():
    """Get Supabase credentials from embedded config or environment"""
    url = None
    key = None
    
    try:
        import embedded_config
        url = getattr(embedded_config, 'EMBEDDED_SUPABASE_URL', '')
        key = getattr(embedded_config, 'EMBEDDED_SUPABASE_KEY', '')
    except (ImportError, AttributeError):
        pass
    
    if not url:
        url = os.getenv('SUPABASE_URL', '')
    if not key:
        key = os.getenv('SUPABASE_ANON_KEY', '') or os.getenv('SUPABASE_KEY', '')
    
    return url, key


def get_supabase_client():
    """Get or create Supabase client singleton"""
    global _supabase_client
    
    if not _SUPABASE_AVAILABLE:
        return None
    
    if _supabase_client is None:
        url, key = get_supabase_credentials()
        if url and key:
            try:
                _supabase_client = create_client(url, key)
            except Exception as e:
                print(f"Supabase connection error: {e}")
                return None
    
    return _supabase_client


def save_match_if_not_exists(match_data: Dict[str, Any]) -> Optional[int]:
    """
    Save match to Supabase if it doesn't exist.
    Returns match ID.
    """
    client = get_supabase_client()
    if not client:
        return None
    
    try:
        existing = client.table('matches').select('id').eq(
            'external_match_id', match_data.get('external_match_id', '')
        ).execute()
        
        if existing.data:
            return existing.data[0]['id']
        
        result = client.table('matches').insert({
            'external_match_id': match_data.get('external_match_id', ''),
            'league': match_data.get('league', ''),
            'home_team': match_data.get('home_team', ''),
            'away_team': match_data.get('away_team', ''),
            'start_time': match_data.get('start_time')
        }).execute()
        
        if result.data:
            return result.data[0]['id']
        return None
        
    except Exception as e:
        print(f"Error saving match: {e}")
        return None


def save_snapshots(snapshots: List[Dict[str, Any]]) -> bool:
    """
    Bulk insert market snapshots to Supabase.
    """
    client = get_supabase_client()
    if not client or not snapshots:
        return False
    
    try:
        client.table('market_snapshots').insert(snapshots).execute()
        return True
    except Exception as e:
        print(f"Error saving snapshots: {e}")
        return False


def get_matches(limit: int = 100, days_back: int = 7) -> List[Dict[str, Any]]:
    """Get recent matches from Supabase"""
    client = get_supabase_client()
    if not client:
        return []
    
    try:
        cutoff = (datetime.now() - timedelta(days=days_back)).isoformat()
        result = client.table('matches').select('*').gte(
            'created_at', cutoff
        ).order('created_at', desc=True).limit(limit).execute()
        return result.data or []
    except Exception as e:
        print(f"Error fetching matches: {e}")
        return []


def get_snapshots_for_match(
    match_id: int,
    source: str = None,
    market: str = None
) -> List[Dict[str, Any]]:
    """Get market snapshots for a specific match"""
    client = get_supabase_client()
    if not client:
        return []
    
    try:
        query = client.table('market_snapshots').select('*').eq('match_id', match_id)
        
        if source:
            query = query.eq('source', source)
        if market:
            query = query.eq('market', market)
        
        result = query.order('created_at').execute()
        return result.data or []
    except Exception as e:
        print(f"Error fetching snapshots: {e}")
        return []


class LocalDatabase:
    """Fallback local SQLite database when Supabase is not available"""
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
            os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, "moneyway.db")
        self.db_path = db_path
    
    def get_all_matches(self) -> List[Dict[str, Any]]:
        """Get unique matches from all history tables"""
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
        """Get historical data for a specific match and market"""
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
        """Get list of available market tables"""
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


def get_database():
    """Get appropriate database (Supabase or local SQLite)"""
    client = get_supabase_client()
    if client:
        return client
    return LocalDatabase()
