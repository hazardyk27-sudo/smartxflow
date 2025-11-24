import os
import sys
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass
import sqlite3

_SUPABASE_AVAILABLE = False
try:
    from supabase import create_client
    _SUPABASE_AVAILABLE = True
except Exception:
    _SUPABASE_AVAILABLE = False

def _get_supabase_credentials():
    """Load Supabase credentials from environment variables."""
    url = os.getenv('SUPABASE_URL')
    key = os.getenv('SUPABASE_KEY')
    
    if not url or not key:
        raise ValueError(
            "SUPABASE_URL and SUPABASE_KEY environment variables required for cloud storage. "
            "Set them in Replit Secrets or your .env file."
        )
    
    return url, key


@dataclass
class TableResult:
    headers: List[str]
    rows: List[Tuple[Any, ...]]


class StorageBackend:
    def fetch_table_values(self, table_name: str) -> TableResult:
        raise NotImplementedError
    def replace_table(self, table_name: str, headers: List[str], records: List[Dict[str, Any]]) -> None:
        raise NotImplementedError
    def append_history(self, hist_table: str, headers: List[str], records: List[Dict[str, Any]], scraped_at: str) -> None:
        raise NotImplementedError
    def query_row(self, table_name: str, home: str, away: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError
    def query_history(self, hist_table: str, home: str, away: str) -> List[Dict[str, Any]]:
        raise NotImplementedError
    def lookup_hist_row_by_label(self, hist_table: str, home: str, away: str, date_label: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError


class SQLiteStorage(StorageBackend):
    def __init__(self, db_path: str):
        self.db_path = db_path
    def fetch_table_values(self, table_name: str) -> TableResult:
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.cursor()
            cur.execute(f"SELECT * FROM \"{table_name}\"")
            headers = [d[0] for d in cur.description]
            rows = cur.fetchall()
            return TableResult(headers=headers, rows=rows)
        finally:
            conn.close()
    def replace_table(self, table_name: str, headers: List[str], records: List[Dict[str, Any]]) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.cursor()
            cur.execute(f"DROP TABLE IF EXISTS \"{table_name}\"")
            cols_def = ", ".join([f'"{h}" TEXT' for h in headers])
            cur.execute(f"CREATE TABLE IF NOT EXISTS \"{table_name}\" ({cols_def})")
            cols = ", ".join([f'"{h}"' for h in headers])
            placeholders = ", ".join(["?"] * len(headers))
            insert_sql = f"INSERT INTO \"{table_name}\" ({cols}) VALUES ({placeholders})"
            rows = [[r.get(h, "") for h in headers] for r in records]
            cur.executemany(insert_sql, rows)
            conn.commit()
        finally:
            conn.close()
    def append_history(self, hist_table: str, headers: List[str], records: List[Dict[str, Any]], scraped_at: str) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.cursor()
            hist_headers = list(headers) + ["ScrapedAt"]
            cur.execute(f"DROP TABLE IF EXISTS \"{hist_table}\"")
            cols_def = ", ".join([f'"{h}" TEXT' for h in hist_headers])
            cur.execute(f"CREATE TABLE IF NOT EXISTS \"{hist_table}\" ({cols_def})")
            cols = ", ".join([f'"{h}"' for h in hist_headers])
            placeholders = ", ".join(["?"] * len(hist_headers))
            insert_sql = f"INSERT INTO \"{hist_table}\" ({cols}) VALUES ({placeholders})"
            rows = [[r.get(h, "") for h in headers] + [scraped_at] for r in records]
            cur.executemany(insert_sql, rows)
            conn.commit()
        finally:
            conn.close()
    def query_row(self, table_name: str, home: str, away: str) -> Optional[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.cursor()
            cur.execute(f"SELECT * FROM \"{table_name}\" WHERE Home=? AND Away=? LIMIT 1", (home, away))
            row = cur.fetchone()
            if not row:
                return None
            headers = [d[0] for d in cur.description]
            return {h: row[i] for i, h in enumerate(headers)}
        finally:
            conn.close()
    def query_history(self, hist_table: str, home: str, away: str) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.cursor()
            cur.execute(f"SELECT * FROM \"{hist_table}\" WHERE Home=? AND Away=? ORDER BY ScrapedAt", (home, away))
            rows = cur.fetchall()
            headers = [d[0] for d in cur.description] if cur.description else []
            return [{h: row[i] for i, h in enumerate(headers)} for row in rows]
        finally:
            conn.close()
    def lookup_hist_row_by_label(self, hist_table: str, home: str, away: str, date_label: str) -> Optional[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                f"SELECT * FROM \"{hist_table}\" WHERE Home=? AND Away=? AND Date=? ORDER BY ScrapedAt DESC LIMIT 1",
                (home, away, date_label),
            )
            row = cur.fetchone()
            headers = [d[0] for d in cur.description] if cur.description else []
            if row and headers:
                return {h: row[i] for i, h in enumerate(headers)}
            return None
        finally:
            conn.close()


class SupabaseStorage(StorageBackend):
    def __init__(self, url: str, key: str):
        self.client = create_client(url, key)
    def fetch_table_values(self, table_name: str) -> TableResult:
        res = self.client.table(table_name).select('*').execute()
        data = res.data or []
        if not data:
            return TableResult(headers=[], rows=[])
        headers = list(data[0].keys())
        rows = [tuple(r.get(h, None) for h in headers) for r in data]
        return TableResult(headers=headers, rows=rows)
    def replace_table(self, table_name: str, headers: List[str], records: List[Dict[str, Any]]) -> None:
        if not records:
            return
        filtered = [{h: r.get(h, None) for h in headers} for r in records]
        on_conflict = None
        if 'ID' in headers:
            on_conflict = 'ID'
        elif 'Date' in headers and 'Home' in headers and 'Away' in headers:
            on_conflict = 'Home,Away,Date'
        elif 'Home' in headers and 'Away' in headers:
            on_conflict = 'Home,Away'
        if on_conflict:
            self.client.table(table_name).upsert(filtered, on_conflict=on_conflict).execute()
        else:
            self.client.table(table_name).upsert(filtered).execute()
    def append_history(self, hist_table: str, headers: List[str], records: List[Dict[str, Any]], scraped_at: str) -> None:
        if not records:
            return
        rows = []
        for r in records:
            d = {h: r.get(h, "") for h in headers}
            d['ScrapedAt'] = scraped_at
            rows.append(d)
        self.client.table(hist_table).upsert(rows, on_conflict='Home,Away,ScrapedAt').execute()
    def query_row(self, table_name: str, home: str, away: str) -> Optional[Dict[str, Any]]:
        res = self.client.table(table_name).select('*').eq('Home', home).eq('Away', away).limit(1).execute()
        data = res.data or []
        return data[0] if data else None
    def query_history(self, hist_table: str, home: str, away: str) -> List[Dict[str, Any]]:
        res = self.client.table(hist_table).select('*').eq('Home', home).eq('Away', away).order('ScrapedAt', desc=False).execute()
        return res.data or []
    def lookup_hist_row_by_label(self, hist_table: str, home: str, away: str, date_label: str) -> Optional[Dict[str, Any]]:
        res = self.client.table(hist_table).select('*').eq('Home', home).eq('Away', away).eq('Date', date_label).order('ScrapedAt', desc=True).limit(1).execute()
        data = res.data or []
        if data:
            return data[0]
        from datetime import datetime
        try_dt = None
        for fmt in ('%d/%m/%Y %H:%M', '%d/%m/%Y', '%d/%m'):
            try:
                try_dt = datetime.strptime(date_label, fmt)
                break
            except Exception:
                continue
        if try_dt:
            prefix = try_dt.strftime('%Y-%m-%d %H:%M')
            res2 = self.client.table(hist_table).select('*').eq('Home', home).eq('Away', away).like('ScrapedAt', f'{prefix}%').order('ScrapedAt', desc=True).limit(1).execute()
            data2 = res2.data or []
            if data2:
                return data2[0]
        return None


def get_storage(db_path: str):
    """
    Get storage backend (Supabase if available, otherwise SQLite).
    
    Args:
        db_path: Path to SQLite database file
        
    Returns:
        StorageBackend instance
    """
    if not _SUPABASE_AVAILABLE:
        print("Warning: Supabase library not available, using SQLite backend")
        return SQLiteStorage(db_path)
    
    try:
        url, key = _get_supabase_credentials()
        return SupabaseStorage(url, key)
    except ValueError as e:
        print(f"Warning: {e}")
        print("Falling back to SQLite storage")
        return SQLiteStorage(db_path)