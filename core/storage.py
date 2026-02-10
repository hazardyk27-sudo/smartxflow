import os
import sys
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass
import sqlite3
from datetime import datetime, timezone

_SUPABASE_AVAILABLE = False
_supabase_client = None

try:
    from supabase import create_client, Client
    _SUPABASE_AVAILABLE = True
except ImportError:
    pass

def _get_supabase_credentials():
    """Load Supabase credentials from embedded config, settings, or environment variables."""
    url = None
    key = None
    
    try:
        import embedded_config
        url = embedded_config.EMBEDDED_SUPABASE_URL
        key = embedded_config.EMBEDDED_SUPABASE_KEY
    except (ImportError, AttributeError):
        pass
    
    if not url or not key:
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_ANON_KEY') or os.getenv('SUPABASE_KEY')
    
    if not url or not key:
        raise ValueError(
            "SUPABASE_URL and SUPABASE_KEY not found. "
            "They should be embedded in the build or set as environment variables."
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
    def _to_lower_keys(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [{k.lower(): v for k, v in r.items()} for r in records]
    def replace_table(self, table_name: str, headers: List[str], records: List[Dict[str, Any]]) -> None:
        if not records:
            return
        filtered = [{h: r.get(h, None) for h in headers} for r in records]
        is_hist = '_hist' in table_name
        if not is_hist:
            filtered = self._to_lower_keys(filtered)
        try:
            self.client.table(table_name).delete().neq('id', 0).execute()
        except Exception:
            pass
        BATCH = 500
        for i in range(0, len(filtered), BATCH):
            batch = filtered[i:i+BATCH]
            self.client.table(table_name).insert(batch).execute()
    def _get_table_columns(self, table_name: str) -> List[str]:
        try:
            res = self.client.table(table_name).select('*').limit(1).execute()
            if res.data:
                return list(res.data[0].keys())
        except Exception:
            pass
        return []
    _HISTORY_SCHEMA = {
        'moneyway_1x2_history': ['match_id_hash', 'home', 'away', 'league', 'date', 'odds1', 'oddsx', 'odds2', 'amt1', 'amtx', 'amt2', 'pct1', 'pctx', 'pct2', 'scraped_at'],
        'moneyway_ou25_history': ['match_id_hash', 'home', 'away', 'league', 'date', 'odds_over', 'odds_under', 'amt_over', 'amt_under', 'pct_over', 'pct_under', 'scraped_at'],
        'moneyway_btts_history': ['match_id_hash', 'home', 'away', 'league', 'date', 'odds_yes', 'odds_no', 'amt_yes', 'amt_no', 'pct_yes', 'pct_no', 'scraped_at'],
        'dropping_1x2_history': ['match_id_hash', 'home', 'away', 'league', 'date', 'opening1', 'openingx', 'opening2', 'odds1', 'oddsx', 'odds2', 'drop1', 'dropx', 'drop2', 'amt1', 'amtx', 'amt2', 'scraped_at'],
        'dropping_ou25_history': ['match_id_hash', 'home', 'away', 'league', 'date', 'opening_over', 'opening_under', 'odds_over', 'odds_under', 'drop_over', 'drop_under', 'amt_over', 'amt_under', 'scraped_at'],
        'dropping_btts_history': ['match_id_hash', 'home', 'away', 'league', 'date', 'opening_yes', 'opening_no', 'odds_yes', 'odds_no', 'drop_yes', 'drop_no', 'amt_yes', 'amt_no', 'scraped_at'],
    }
    def _write_to_history_table(self, hist_table: str, headers: List[str], records: List[Dict[str, Any]], scraped_at: str) -> None:
        history_table = hist_table.replace('_hist', '_history')
        if history_table == hist_table:
            return
        try:
            from core.hash_utils import make_match_id_hash
        except ImportError:
            return
        try:
            table_cols = self._get_table_columns(history_table)
            if not table_cols:
                table_cols = self._HISTORY_SCHEMA.get(history_table, [])
            if not table_cols:
                return
            try:
                from datetime import timedelta
                tr_tz = timezone(timedelta(hours=3))
                if scraped_at and '+' not in scraped_at and 'Z' not in scraped_at:
                    utc_dt = datetime.fromisoformat(scraped_at).replace(tzinfo=timezone.utc)
                else:
                    utc_dt = datetime.now(timezone.utc)
                tr_dt = utc_dt.astimezone(tr_tz)
                scraped_ts = tr_dt.strftime('%Y-%m-%dT%H:%M:%S+03:00')
            except Exception:
                scraped_ts = scraped_at
                if scraped_ts and '+' not in scraped_ts and 'Z' not in scraped_ts:
                    scraped_ts = scraped_ts + '+03:00'
            rows = []
            for r in records:
                low = {k.lower(): v for k, v in r.items()}
                home = low.get('home', '')
                away = low.get('away', '')
                league = low.get('league', '')
                if not home or not away:
                    continue
                match_hash = make_match_id_hash(home, away, league)
                row = {}
                for col in table_cols:
                    if col == 'id':
                        continue
                    elif col == 'match_id_hash':
                        row[col] = match_hash
                    elif col == 'scraped_at':
                        row[col] = scraped_ts
                    else:
                        row[col] = low.get(col, '')
                rows.append(row)
            if rows:
                seen = set()
                unique_rows = []
                for row in rows:
                    key = (row.get('match_id_hash', ''), row.get('scraped_at', ''))
                    if key not in seen:
                        seen.add(key)
                        unique_rows.append(row)
                rows = unique_rows
                BATCH = 500
                total_written = 0
                failed_count = 0
                for i in range(0, len(rows), BATCH):
                    batch = rows[i:i+BATCH]
                    try:
                        self.client.table(history_table).insert(batch).execute()
                        total_written += len(batch)
                    except Exception as batch_err:
                        print(f"[Storage] {history_table} batch insert error: {batch_err}")
                        for single_row in batch:
                            try:
                                self.client.table(history_table).insert(single_row).execute()
                                total_written += 1
                            except Exception as row_err:
                                failed_count += 1
                                if failed_count <= 3:
                                    print(f"[Storage] {history_table} row insert failed: {row_err} | hash={single_row.get('match_id_hash','')}")
                if failed_count > 3:
                    print(f"[Storage] {history_table}: ...and {failed_count - 3} more row failures")
                print(f"[Storage] {history_table}: {total_written}/{len(rows)} rows written" + (f" ({failed_count} failed)" if failed_count else ""))
        except Exception as e:
            print(f"[Storage] {history_table} write error: {e}")
    def append_history(self, hist_table: str, headers: List[str], records: List[Dict[str, Any]], scraped_at: str) -> None:
        if not records:
            return
        table_cols = self._get_table_columns(hist_table)
        rows = []
        for r in records:
            d = {}
            for h in headers:
                if table_cols and h not in table_cols:
                    continue
                d[h] = r.get(h, "")
            d['ScrapedAt'] = scraped_at
            rows.append(d)
        try:
            self.client.table(hist_table).upsert(rows, on_conflict='Home,Away,ScrapedAt').execute()
        except Exception as e:
            print(f"[Storage] {hist_table} upsert error: {e}")
        self._write_to_history_table(hist_table, headers, records, scraped_at)
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
    except (ValueError, TypeError, Exception) as e:
        print(f"Warning: {e}")
        print("Falling back to SQLite storage")
        return SQLiteStorage(db_path)
