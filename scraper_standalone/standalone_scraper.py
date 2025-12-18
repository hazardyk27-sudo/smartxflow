"""
SmartXFlow Monitor V1.20 - Standalone Scraper
PC'de çalışan bağımsız scraper - Supabase'e direkt yazar
"""

import os
import sys
import json
import re
import time
import requests
import certifi
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from bs4 import BeautifulSoup

# Hash utils import - fixtures ve snapshots için match_id_hash üretimi
# Canonical implementation from core/hash_utils.py
try:
    import sys
    import os
    # Add parent directory to path for core module import
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    from core.hash_utils import make_match_id_hash
except ImportError:
    # Fallback: inline implementation if core module not available
    import hashlib
    
    def normalize_field_for_hash(value: str) -> str:
        """String normalizasyonu for match_id_hash"""
        if not value:
            return ""
        value = value.strip()
        # Türkçe karakter normalizasyonu
        tr_map = {'ş': 's', 'Ş': 'S', 'ğ': 'g', 'Ğ': 'G', 'ü': 'u', 'Ü': 'U',
                  'ı': 'i', 'İ': 'I', 'ö': 'o', 'Ö': 'O', 'ç': 'c', 'Ç': 'C'}
        for tr_char, en_char in tr_map.items():
            value = value.replace(tr_char, en_char)
        value = value.lower()
        value = ' '.join(value.split())
        return value

    def normalize_kickoff_for_hash(kickoff: str) -> str:
        """Kickoff normalizasyonu: YYYY-MM-DDTHH:MM"""
        if not kickoff:
            return ""
        kickoff = str(kickoff).strip()
        kickoff = re.sub(r'[+-]\d{2}:\d{2}$', '', kickoff)
        kickoff = kickoff.replace('Z', '')
        if 'T' in kickoff and len(kickoff) >= 16:
            return kickoff[:16]
        if len(kickoff) >= 10 and kickoff[4] == '-':
            return kickoff[:16] if len(kickoff) >= 16 else kickoff[:10] + "T00:00"
        return kickoff

    def make_match_id_hash(home: str, away: str, league: str, kickoff_utc: str) -> str:
        """12 karakterlik MD5 hash üret - Format: league|kickoff|home|away"""
        home_norm = normalize_field_for_hash(home)
        away_norm = normalize_field_for_hash(away)
        league_norm = normalize_field_for_hash(league)
        kickoff_norm = normalize_kickoff_for_hash(kickoff_utc)
        canonical = f"{league_norm}|{kickoff_norm}|{home_norm}|{away_norm}"
        return hashlib.md5(canonical.encode('utf-8')).hexdigest()[:12]


def get_ssl_cert_path():
    """Get SSL certificate path with fallback for PyInstaller temp folder issues"""
    # Try certifi first
    try:
        cert_path = certifi.where()
        if os.path.exists(cert_path):
            return cert_path
    except Exception:
        pass
    
    # Fallback: Check bundled certifi in PyInstaller temp
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
        bundled_cert = os.path.join(base_path, 'certifi', 'cacert.pem')
        if os.path.exists(bundled_cert):
            return bundled_cert
    
    # Fallback: Use requests bundled certs
    try:
        import requests.certs
        req_cert = requests.certs.where()
        if os.path.exists(req_cert):
            return req_cert
    except Exception:
        pass
    
    # Last resort: Disable SSL verification (not recommended but keeps scraper running)
    return False

SSL_VERIFY = get_ssl_cert_path()

try:
    import pytz
    TURKEY_TZ = pytz.timezone('Europe/Istanbul')
except ImportError:
    TURKEY_TZ = None

VERSION = "1.20"
SCRAPE_INTERVAL_MINUTES = 10

DATASETS = {
    "moneyway-1x2": "https://arbworld.net/en/moneyway/football-1-x-2",
    "moneyway-ou25": "https://arbworld.net/en/moneyway/football-over-under-2-5",
    "moneyway-btts": "https://arbworld.net/en/moneyway/football-both-teams-to-score",
    "dropping-1x2": "https://arbworld.net/en/dropping-odds/football-1-x-2",
    "dropping-ou25": "https://arbworld.net/en/dropping-odds/football-over-under-2-5",
    "dropping-btts": "https://arbworld.net/en/dropping-odds/football-both-teams-to-score",
}

MARKET_TABLE_MAP = {
    "moneyway-1x2": "moneyway_1x2",
    "moneyway-ou25": "moneyway_ou25",
    "moneyway-btts": "moneyway_btts",
    "dropping-1x2": "dropping_1x2",
    "dropping-ou25": "dropping_ou25",
    "dropping-btts": "dropping_btts",
}

HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}


def get_turkey_now() -> str:
    """Return ISO timestamp WITH +03:00 offset for Europe/Istanbul"""
    if TURKEY_TZ:
        return datetime.now(TURKEY_TZ).strftime('%Y-%m-%dT%H:%M:%S+03:00')
    return datetime.now().strftime('%Y-%m-%dT%H:%M:%S+03:00')


def get_turkey_time_display() -> str:
    if TURKEY_TZ:
        return datetime.now(TURKEY_TZ).strftime('%H:%M')
    return datetime.now().strftime('%H:%M')


def log(msg: str):
    timestamp = get_turkey_time_display()
    print(f"[{timestamp}] {msg}")


def load_config() -> Dict[str, str]:
    possible_paths = []
    
    if getattr(sys, 'frozen', False):
        possible_paths.append(os.path.join(os.path.dirname(sys.executable), 'config.json'))
        if hasattr(sys, '_MEIPASS'):
            possible_paths.append(os.path.join(sys._MEIPASS, 'config.json'))
    else:
        possible_paths.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json'))
    
    possible_paths.append('config.json')
    possible_paths.append(os.path.join(os.getcwd(), 'config.json'))
    
    config_path = None
    for path in possible_paths:
        log(f"Config araniyor: {path}")
        if os.path.exists(path):
            config_path = path
            break
    
    if not config_path:
        log(f"ERROR: config.json bulunamadi!")
        log(f"Aranan konumlar:")
        for p in possible_paths:
            log(f"  - {p}")
        log(f"Lutfen config.json dosyasini .exe ile ayni klasore koyun.")
        input("Devam etmek icin Enter'a basin...")
        sys.exit(1)
    
    try:
        with open(config_path, 'r', encoding='utf-8-sig') as f:
            content = f.read().strip()
        
        if content.startswith('\ufeff'):
            content = content[1:]
        
        config = json.loads(content)
        
        if not config.get('SUPABASE_URL'):
            log("ERROR: config.json'da SUPABASE_URL eksik!")
            input("Devam etmek icin Enter'a basin...")
            sys.exit(1)
        
        # SERVICE_ROLE_KEY tercih et (RLS bypass), yoksa ANON_KEY kullan
        if not config.get('SUPABASE_SERVICE_ROLE_KEY') and not config.get('SUPABASE_ANON_KEY'):
            log("ERROR: config.json'da SUPABASE_SERVICE_ROLE_KEY veya SUPABASE_ANON_KEY eksik!")
            input("Devam etmek icin Enter'a basin...")
            sys.exit(1)
        
        log(f"Config yuklendi basariyla!")
        return config
    except json.JSONDecodeError as e:
        log(f"ERROR: config.json okunamadi - {e}")
        log(f"Dosya icerigi: {repr(content[:100])}")
        input("Devam etmek icin Enter'a basin...")
        sys.exit(1)
    except Exception as e:
        log(f"ERROR: Beklenmeyen hata - {e}")
        input("Devam etmek icin Enter'a basin...")
        sys.exit(1)


class SupabaseWriter:
    def __init__(self, url: str, key: str):
        self.url = url.rstrip('/')
        self.key = key
    
    def _headers(self) -> Dict[str, str]:
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json"
        }
    
    def _rest_url(self, table: str) -> str:
        return f"{self.url}/rest/v1/{table}"
    
    def upsert_rows(self, table: str, rows: List[Dict[str, Any]], on_conflict: str = "home,away,date") -> bool:
        """UPSERT rows using Supabase REST API with proper on_conflict"""
        if not rows:
            return True
        
        try:
            headers = self._headers()
            headers["Prefer"] = "resolution=merge-duplicates"
            url = f"{self._rest_url(table)}?on_conflict={on_conflict}"
            
            resp = requests.post(
                url,
                headers=headers,
                json=rows,
                timeout=30,
                verify=SSL_VERIFY
            )
            
            if resp.status_code in [200, 201, 204]:
                return True
            else:
                # DETAYLI HATA LOGLAMA
                log(f"  [UPSERT ERR] {table}: HTTP {resp.status_code}")
                log(f"  [UPSERT ERR] URL: {url}")
                try:
                    error_body = resp.text if resp.text else "empty"
                    log(f"  [UPSERT ERR] Response: {error_body[:500]}")
                except:
                    log(f"  [UPSERT ERR] Response read failed")
                log(f"  [UPSERT ERR] Sample keys: {list(rows[0].keys()) if rows else 'no rows'}")
                return False
        except Exception as e:
            log(f"  Supabase baglanti hatasi: {e}")
            return False
    
    def insert_rows(self, table: str, rows: List[Dict[str, Any]]) -> bool:
        """Insert rows without upsert"""
        if not rows:
            return True
        
        try:
            headers = self._headers()
            url = self._rest_url(table)
            
            resp = requests.post(
                url,
                headers=headers,
                json=rows,
                timeout=30,
                verify=SSL_VERIFY
            )
            
            if resp.status_code in [200, 201, 204]:
                return True
            else:
                log(f"  [INSERT ERR] {table}: {resp.status_code}")
                log(f"  [INSERT ERR] Response: {resp.text}")
                log(f"  [INSERT ERR] Sample row: {json.dumps(rows[0], default=str)}")
                return False
        except Exception as e:
            log(f"  Supabase baglanti hatasi: {e}")
            return False
    
    def delete_all_rows(self, table: str) -> bool:
        """DELETE all rows - id > 0 filtresi ile"""
        try:
            headers = self._headers()
            url = f"{self._rest_url(table)}?id=gt.0"
            
            resp = requests.delete(
                url,
                headers=headers,
                timeout=30,
                verify=SSL_VERIFY
            )
            if resp.status_code not in [200, 204]:
                log(f"  [DELETE ERR] {table}: {resp.status_code} - {resp.text}")
            return resp.status_code in [200, 204]
        except Exception as e:
            log(f"  Tablo temizleme hatasi: {e}")
            return False
    
    def replace_table(self, table: str, rows: List[Dict[str, Any]]) -> bool:
        """Replace table: UPSERT kullan (v1.08 gibi)"""
        clean_rows = []
        for row in rows:
            new_row = row.copy()
            if 'id' in new_row:
                del new_row['id']
            clean_rows.append(new_row)
        
        # UPSERT - UNIQUE(league, home, away, date) constraint'i kullan
        return self.upsert_rows(table, clean_rows, on_conflict="league,home,away,date")
    
    def append_history(self, table: str, rows: List[Dict[str, Any]], scraped_at: str) -> bool:
        """History tablosuna yeni kayit ekle - match_id_hash dahil
        
        KRITIK: Her satira match_id_hash eklenir (date alanini kickoff olarak kullanir)
        Bu sayede history <-> fixtures <-> alarms zinciri ayni ID ile baglanir
        """
        history_rows = []
        skipped = 0
        
        for row in rows:
            home = row.get('home', '').strip()
            away = row.get('away', '').strip()
            league = row.get('league', '').strip()
            date_str = row.get('date', '').strip()
            
            if not home or not away or not date_str:
                skipped += 1
                continue
            
            match_id_hash = make_match_id_hash(home, away, league, date_str)
            
            new_row = row.copy()
            if 'id' in new_row:
                del new_row['id']
            new_row['scraped_at'] = scraped_at
            new_row['match_id_hash'] = match_id_hash
            history_rows.append(new_row)
        
        if skipped > 0:
            log(f"  [HISTORY WARN] {table}: {skipped} satir skip (eksik field)")
        
        return self.insert_rows(table, history_rows)
    
    def upsert_fixtures(self, fixtures: List[Dict[str, Any]]) -> bool:
        """Fixtures tablosuna UPSERT - match_id_hash unique key"""
        if not fixtures:
            return True
        try:
            headers = self._headers()
            headers["Prefer"] = "resolution=merge-duplicates"
            url = f"{self._rest_url('fixtures')}?on_conflict=match_id_hash"
            
            resp = requests.post(url, headers=headers, json=fixtures, timeout=30, verify=SSL_VERIFY)
            if resp.status_code in [200, 201, 204]:
                return True
            else:
                log(f"  [FIXTURES UPSERT ERR] {resp.status_code}: {resp.text[:200]}")
                return False
        except Exception as e:
            log(f"  [FIXTURES UPSERT ERR] {e}")
            return False
    
    def insert_snapshots(self, table: str, snapshots: List[Dict[str, Any]]) -> bool:
        """Snapshot tablosuna INSERT - match_id_hash dahil"""
        if not snapshots:
            return True
        try:
            headers = self._headers()
            resp = requests.post(self._rest_url(table), headers=headers, json=snapshots, timeout=30, verify=SSL_VERIFY)
            if resp.status_code in [200, 201, 204]:
                return True
            else:
                log(f"  [SNAPSHOT INSERT ERR] {table}: {resp.status_code}: {resp.text[:200]}")
                return False
        except Exception as e:
            log(f"  [SNAPSHOT INSERT ERR] {table}: {e}")
            return False


def _text(node) -> str:
    return node.get_text(strip=True) if node else ""


def _hidden_date(tr) -> Optional[str]:
    for td in tr.find_all("td"):
        style = td.get("style", "")
        if "display:none" in style.replace(" ", ""):
            return " ".join(list(td.stripped_strings))
    return None


def _parse_pct_amt_cell(td) -> tuple:
    joined = " ".join(list(td.stripped_strings))
    m_pct = re.search(r"(\d+(?:\.\d+)?)\s*%", joined)
    pct = f"{m_pct.group(1)}%" if m_pct else ""
    m_amt = re.search(r"£\s*([\d\s\.]+\s*[MKmk]?)", joined)
    amt = f"£ {m_amt.group(1).strip()}" if m_amt else ""
    return pct, amt


def fetch_table(url: str, session: requests.Session) -> BeautifulSoup:
    resp = session.get(url, headers=HEADERS, timeout=30, verify=SSL_VERIFY)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.select_one("table#matches.table_matches")
    if not table:
        table = soup.find("table", id="matches") or soup.find("table", class_="table_matches")
    if not table:
        raise RuntimeError("Hedef tablo bulunamadi")
    return table


def extract_moneyway_1x2(table: BeautifulSoup) -> List[Dict[str, str]]:
    rows = []
    for tr in table.select("tbody tr"):
        league = _text(tr.select_one("td.tleague"))
        if not league:
            continue
        row_id = tr.get("id", "")
        date = _hidden_date(tr) or _text(tr.select_one("td.tdate"))
        home = _text(tr.select_one("td.thome"))
        away = _text(tr.select_one("td.taway"))
        volume = _text(tr.select_one("td.tvol"))
        odds_small = [td.get_text(strip=True) for td in tr.select("td.odds_col_small")][:3]
        while len(odds_small) < 3:
            odds_small.append("")
        pct_cells = tr.select("td.odds_col")[:3]
        pct_amt_values = [_parse_pct_amt_cell(td) for td in pct_cells]
        while len(pct_amt_values) < 3:
            pct_amt_values.append(("", ""))
        rows.append({
            "id": row_id,
            "league": league,
            "date": date,
            "home": home,
            "odds1": odds_small[0],
            "oddsx": odds_small[1],
            "odds2": odds_small[2],
            "pct1": pct_amt_values[0][0],
            "amt1": pct_amt_values[0][1],
            "pctx": pct_amt_values[1][0],
            "amtx": pct_amt_values[1][1],
            "pct2": pct_amt_values[2][0],
            "amt2": pct_amt_values[2][1],
            "away": away,
            "volume": volume,
        })
    return rows


def extract_moneyway_ou25(table: BeautifulSoup) -> List[Dict[str, str]]:
    rows = []
    for tr in table.select("tbody tr"):
        league = _text(tr.select_one("td.tleague"))
        if not league:
            continue
        row_id = tr.get("id", "")
        date = _hidden_date(tr) or _text(tr.select_one("td.tdate"))
        home = _text(tr.select_one("td.thome"))
        away = _text(tr.select_one("td.taway"))
        volume = _text(tr.select_one("td.tvol"))
        small = [td.get_text(strip=True) for td in tr.select("td.odds_col_small")]
        under = small[0] if len(small) > 0 else ""
        line = small[1] if len(small) > 1 else ""
        over = small[2] if len(small) > 2 else ""
        pct_cells = tr.select("td.odds_col")
        pct_under, amt_under = _parse_pct_amt_cell(pct_cells[0]) if len(pct_cells) > 0 else ("", "")
        pct_over, amt_over = _parse_pct_amt_cell(pct_cells[1]) if len(pct_cells) > 1 else ("", "")
        rows.append({
            "id": row_id,
            "league": league,
            "date": date,
            "home": home,
            "under": under,
            "line": line,
            "over": over,
            "pctunder": pct_under,
            "amtunder": amt_under,
            "pctover": pct_over,
            "amtover": amt_over,
            "away": away,
            "volume": volume,
        })
    return rows


def extract_moneyway_btts(table: BeautifulSoup) -> List[Dict[str, str]]:
    rows = []
    for tr in table.select("tbody tr"):
        league = _text(tr.select_one("td.tleague"))
        if not league:
            continue
        row_id = tr.get("id", "")
        date = _hidden_date(tr) or _text(tr.select_one("td.tdate"))
        home = _text(tr.select_one("td.thome"))
        away = _text(tr.select_one("td.taway"))
        volume = _text(tr.select_one("td.tvol"))
        small = [td.get_text(strip=True) for td in tr.select("td.odds_col_small")]
        yes = small[0] if len(small) > 0 else ""
        no = small[1] if len(small) > 1 else ""
        pct_cells = tr.select("td.odds_col")
        pct_yes, amt_yes = _parse_pct_amt_cell(pct_cells[0]) if len(pct_cells) > 0 else ("", "")
        pct_no, amt_no = _parse_pct_amt_cell(pct_cells[1]) if len(pct_cells) > 1 else ("", "")
        rows.append({
            "id": row_id,
            "league": league,
            "date": date,
            "home": home,
            "yes": yes,
            "no": no,
            "pctyes": pct_yes,
            "amtyes": amt_yes,
            "pctno": pct_no,
            "amtno": amt_no,
            "away": away,
            "volume": volume,
        })
    return rows


def extract_dropping_1x2(table: BeautifulSoup) -> List[Dict[str, str]]:
    rows = []
    for tr in table.select("tbody tr"):
        league = _text(tr.select_one("td.tleague"))
        if not league:
            continue
        row_id = tr.get("id", "")
        date = _hidden_date(tr) or _text(tr.select_one("td.tdate"))
        home = _text(tr.select_one("td.thome"))
        away = _text(tr.select_one("td.taway"))
        volume = _text(tr.select_one("td.tvol"))
        small = [td.get_text(strip=True) for td in tr.select("td.odds_col_small")]
        
        def g(i):
            return small[i] if len(small) > i else ""
        
        s1_f, c1_f, sx_f, cx_f, s2_f, c2_f = g(0), g(1), g(2), g(3), g(4), g(5)
        ocells = tr.select("td.odds_col")
        
        def two_line_text(td, start_fb, cur_fb):
            if td:
                raw = td.get_text(separator="\n", strip=True)
                nums_all = re.findall(r"\d+(?:\.\d+)?", raw)
                if len(nums_all) >= 2:
                    start, cur = nums_all[0], nums_all[-1]
                elif len(nums_all) == 1:
                    n = nums_all[0]
                    start, cur = (start_fb or n), n
                else:
                    start, cur = start_fb, cur_fb
            else:
                start, cur = start_fb, cur_fb
            return start, cur
        
        s1, c1 = two_line_text(ocells[0] if len(ocells) > 0 else None, s1_f, c1_f)
        sx, cx = two_line_text(ocells[1] if len(ocells) > 1 else None, sx_f, cx_f)
        s2, c2 = two_line_text(ocells[2] if len(ocells) > 2 else None, s2_f, c2_f)
        
        def calc_trend(cur, prev):
            try:
                c = float(cur) if cur else 0
                p = float(prev) if prev else 0
                if abs(c - p) < 0.001:
                    return ""
                return "up" if c > p else "down"
            except:
                return ""
        
        rows.append({
            "id": row_id,
            "league": league,
            "date": date,
            "home": home,
            "odds1": c1,
            "odds1_prev": s1,
            "oddsx": cx,
            "oddsx_prev": sx,
            "odds2": c2,
            "odds2_prev": s2,
            "trend1": calc_trend(c1, s1),
            "trendx": calc_trend(cx, sx),
            "trend2": calc_trend(c2, s2),
            "away": away,
            "volume": volume,
        })
    return rows


def extract_dropping_ou25(table: BeautifulSoup) -> List[Dict[str, str]]:
    rows = []
    for tr in table.select("tbody tr"):
        league = _text(tr.select_one("td.tleague"))
        if not league:
            continue
        row_id = tr.get("id", "")
        date = _hidden_date(tr) or _text(tr.select_one("td.tdate"))
        home = _text(tr.select_one("td.thome"))
        away = _text(tr.select_one("td.taway"))
        volume = _text(tr.select_one("td.tvol"))
        small = [td.get_text(strip=True) for td in tr.select("td.odds_col_small")]
        
        def g(i):
            return small[i] if len(small) > i else ""
        
        under_start_fb, under_cur_fb, over_start_fb, over_cur_fb = g(0), g(1), g(3), g(4)
        astar_fb = g(2)
        ocells = tr.select("td.odds_col")
        
        def two_line_text(td, start_fb, cur_fb):
            if td:
                raw = td.get_text(separator="\n", strip=True)
                nums_all = re.findall(r"\d+(?:\.\d+)?", raw)
                if len(nums_all) >= 2:
                    start, cur = nums_all[0], nums_all[-1]
                elif len(nums_all) == 1:
                    n = nums_all[0]
                    start, cur = (start_fb or n), n
                else:
                    start, cur = start_fb, cur_fb
            else:
                start, cur = start_fb, cur_fb
            return start, cur
        
        under_start, under_cur = two_line_text(ocells[0] if len(ocells) > 0 else None, under_start_fb, under_cur_fb)
        over_start, over_cur = two_line_text(ocells[2] if len(ocells) > 2 else None, over_start_fb, over_cur_fb)
        
        astar = ""
        if len(ocells) > 1:
            astar = " ".join(list(ocells[1].stripped_strings)).strip()
        if not astar:
            astar = astar_fb
        
        pct_cells = tr.select("td.tpercent")
        pct_under, amt_under, pct_over, amt_over = "", "", "", ""
        if len(pct_cells) >= 2:
            pct_under, amt_under = _parse_pct_amt_cell(pct_cells[0])
            pct_over, amt_over = _parse_pct_amt_cell(pct_cells[1])
        
        def calc_trend(cur, prev):
            try:
                c = float(cur) if cur else 0
                p = float(prev) if prev else 0
                if abs(c - p) < 0.001:
                    return ""
                return "up" if c > p else "down"
            except:
                return ""
        
        rows.append({
            "id": row_id,
            "league": league,
            "date": date,
            "home": home,
            "under": under_cur,
            "under_prev": under_start,
            "line": astar,
            "over": over_cur,
            "over_prev": over_start,
            "trendunder": calc_trend(under_cur, under_start),
            "trendover": calc_trend(over_cur, over_start),
            "pctunder": pct_under,
            "amtunder": amt_under,
            "pctover": pct_over,
            "amtover": amt_over,
            "away": away,
            "volume": volume,
        })
    return rows


def extract_dropping_btts(table: BeautifulSoup) -> List[Dict[str, str]]:
    rows = []
    for tr in table.select("tbody tr"):
        league = _text(tr.select_one("td.tleague"))
        if not league:
            continue
        row_id = tr.get("id", "")
        date = _hidden_date(tr) or _text(tr.select_one("td.tdate"))
        home = _text(tr.select_one("td.thome"))
        away = _text(tr.select_one("td.taway"))
        volume = _text(tr.select_one("td.tvol"))
        small = [td.get_text(strip=True) for td in tr.select("td.odds_col_small")]
        
        def g(i):
            return small[i] if len(small) > i else ""
        
        yes_start_fb, yes_cur_fb, no_start_fb, no_cur_fb = g(0), g(1), g(2), g(3)
        ocells = tr.select("td.odds_col")
        
        def two_line_text(td, start_fb, cur_fb):
            if td:
                raw = td.get_text(separator="\n", strip=True)
                nums_all = re.findall(r"\d+(?:\.\d+)?", raw)
                if len(nums_all) >= 2:
                    start, cur = nums_all[0], nums_all[-1]
                elif len(nums_all) == 1:
                    n = nums_all[0]
                    start, cur = (start_fb or n), n
                else:
                    start, cur = start_fb, cur_fb
            else:
                start, cur = start_fb, cur_fb
            return start, cur
        
        yes_start, yes_cur = two_line_text(ocells[0] if len(ocells) > 0 else None, yes_start_fb, yes_cur_fb)
        no_start, no_cur = two_line_text(ocells[1] if len(ocells) > 1 else None, no_start_fb, no_cur_fb)
        
        pct_cells = tr.select("td.tpercent")
        pct_yes, amt_yes, pct_no, amt_no = "", "", "", ""
        if len(pct_cells) >= 2:
            pct_yes, amt_yes = _parse_pct_amt_cell(pct_cells[0])
            pct_no, amt_no = _parse_pct_amt_cell(pct_cells[1])
        
        def calc_trend(cur, prev):
            try:
                c = float(cur) if cur else 0
                p = float(prev) if prev else 0
                if abs(c - p) < 0.001:
                    return ""
                return "up" if c > p else "down"
            except:
                return ""
        
        rows.append({
            "id": row_id,
            "league": league,
            "date": date,
            "home": home,
            "oddsyes": yes_cur,
            "oddsyes_prev": yes_start,
            "oddsno": no_cur,
            "oddsno_prev": no_start,
            "trendyes": calc_trend(yes_cur, yes_start),
            "trendno": calc_trend(no_cur, no_start),
            "pctyes": pct_yes,
            "amtyes": amt_yes,
            "pctno": pct_no,
            "amtno": amt_no,
            "away": away,
            "volume": volume,
        })
    return rows


EXTRACTORS = {
    "moneyway-1x2": extract_moneyway_1x2,
    "moneyway-ou25": extract_moneyway_ou25,
    "moneyway-btts": extract_moneyway_btts,
    "dropping-1x2": extract_dropping_1x2,
    "dropping-ou25": extract_dropping_ou25,
    "dropping-btts": extract_dropping_btts,
}


def cleanup_old_matches(writer: SupabaseWriter, logger_callback=None):
    """
    D-2+ maçlarını sil (bugün ve dün hariç tüm eski maçlar)
    - D (bugün): Korunur
    - D-1 (dün): Korunur
    - D-2+ (öncesi): Silinir
    
    Temizlenen tablolar:
    - history tablolari (scraped_at bazli)
    - moneyway/dropping tablolari (date bazli)
    - fixtures (fixture_date bazli)
    - alarm tablolari
    """
    _log = logger_callback if logger_callback else log
    
    if TURKEY_TZ:
        now = datetime.now(TURKEY_TZ)
    else:
        now = datetime.now()
    
    today = now.date()
    yesterday = today - timedelta(days=1)
    d_minus_2 = today - timedelta(days=2)
    
    _log(f"[Cleanup] D-2+ silme: {d_minus_2} ve oncesi silinecek (bugun={today}, dun={yesterday})")
    
    total_deleted = 0
    
    # 1. History tablolari (scraped_at bazli)
    history_tables = [
        "moneyway_1x2_history",
        "moneyway_ou25_history",
        "moneyway_btts_history",
        "dropping_1x2_history",
        "dropping_ou25_history",
        "dropping_btts_history",
    ]
    
    for table in history_tables:
        try:
            cutoff_iso = d_minus_2.strftime('%Y-%m-%dT23:59:59')
            url = f"{writer._rest_url(table)}?scraped_at=lt.{cutoff_iso}"
            resp = requests.delete(url, headers=writer._headers(), timeout=30)
            if resp.status_code in [200, 204]:
                _log(f"  [Cleanup] {table}: D-2+ kayitlar silindi")
                total_deleted += 1
        except Exception as e:
            _log(f"  [Cleanup] {table}: Hata - {e}")
    
    # 2. Moneyway/Dropping canli tablolari (date bazli - DD.Mon formatinda)
    live_tables = [
        "moneyway_1x2",
        "moneyway_ou25", 
        "moneyway_btts",
        "dropping_1x2",
        "dropping_ou25",
        "dropping_btts",
    ]
    
    months_map = {1:'jan',2:'feb',3:'mar',4:'apr',5:'may',6:'jun',7:'jul',8:'aug',9:'sep',10:'oct',11:'nov',12:'dec'}
    valid_dates = []
    for offset in range(0, 7):
        d = today - timedelta(days=offset)
        if offset <= 1:
            month_str = months_map[d.month].capitalize()
            valid_dates.append(f"{d.day:02d}.{month_str}")
            valid_dates.append(f"{d.day}.{month_str}")
    
    _log(f"  [Cleanup] Gecerli tarihler: {valid_dates[:4]}...")
    
    for table in live_tables:
        try:
            r = requests.get(f"{writer._rest_url(table)}?select=id,date", headers=writer._headers(), timeout=60)
            if r.status_code == 200:
                rows = r.json()
                old_ids = []
                for row in rows:
                    date_str = row.get('date', '')
                    is_valid = any(date_str.startswith(vd) for vd in valid_dates)
                    if not is_valid and row.get('id'):
                        old_ids.append(str(row['id']))
                
                if old_ids:
                    # Batch delete - 500'er grupla
                    for i in range(0, len(old_ids), 500):
                        batch = old_ids[i:i+500]
                        ids_filter = ','.join(batch)
                        requests.delete(f"{writer._rest_url(table)}?id=in.({ids_filter})", headers=writer._headers(), timeout=30)
                    _log(f"  [Cleanup] {table}: {len(old_ids)} eski mac silindi")
                    total_deleted += len(old_ids)
        except Exception as e:
            _log(f"  [Cleanup] {table}: Hata - {e}")
    
    # 3. Fixtures (fixture_date bazli)
    try:
        cutoff_date = d_minus_2.strftime('%Y-%m-%d')
        url = f"{writer._rest_url('fixtures')}?fixture_date=lt.{cutoff_date}"
        resp = requests.delete(url, headers=writer._headers(), timeout=30)
        if resp.status_code in [200, 204]:
            _log(f"  [Cleanup] fixtures: D-2+ kayitlar silindi")
            total_deleted += 1
    except Exception as e:
        _log(f"  [Cleanup] fixtures: Hata - {e}")
    
    if total_deleted > 0:
        _log(f"[Cleanup] Tamamlandi - {total_deleted} islem")
    
    # 4. Alarm tablolarini temizle
    try:
        from alarm_calculator import AlarmCalculator
        alarm_calc = AlarmCalculator(
            supabase_url=writer.supabase_url,
            supabase_key=writer.supabase_key
        )
        alarm_deleted = alarm_calc.cleanup_old_alarms(days_to_keep=2)
        total_deleted += alarm_deleted
    except Exception as e:
        _log(f"[Cleanup] Alarm cleanup hatası: {e}")
    
    return total_deleted


def parse_date_to_kickoff(date_str: str) -> str:
    """Parse date string to kickoff_utc format (YYYY-MM-DDTHH:MM:SS+00:00)
    
    Desteklenen formatlar:
    - "21.Dec 13:30:00" (history format)
    - "21.Dec 13:30" (history short)
    - "18 Dec 15:00" (space format)
    - "18 Dec" (date only)
    """
    if not date_str:
        return datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S+00:00')
    
    date_str = date_str.strip()
    now = datetime.utcnow()
    months = {'jan':1,'feb':2,'mar':3,'apr':4,'may':5,'jun':6,'jul':7,'aug':8,'sep':9,'oct':10,'nov':11,'dec':12}
    
    # Pattern 1: "21.Dec 13:30:00" veya "21.Dec 13:30" (history format - noktalı)
    m = re.match(r'^(\d{1,2})\.([A-Za-z]{3})\s+(\d{1,2}):(\d{2})(?::\d{2})?', date_str)
    if m:
        day, month_str, hour, minute = m.groups()
        month = months.get(month_str.lower()[:3], now.month)
        year = now.year
        try:
            dt = datetime(year, month, int(day), int(hour), int(minute))
            return dt.strftime('%Y-%m-%dT%H:%M:%S+00:00')
        except:
            pass
    
    # Pattern 2: "18 Dec 15:00" or "18 Dec" (space format)
    m = re.match(r'^(\d{1,2})\s+(\w{3})\s*(\d{1,2}:\d{2})?', date_str)
    if m:
        day, month_str, time_part = m.groups()
        month = months.get(month_str.lower()[:3], now.month)
        year = now.year
        if time_part:
            hour, minute = map(int, time_part.split(':'))
        else:
            hour, minute = 12, 0
        try:
            dt = datetime(year, month, int(day), hour, minute)
            return dt.strftime('%Y-%m-%dT%H:%M:%S+00:00')
        except:
            pass
    
    return now.strftime('%Y-%m-%dT%H:%M:%S+00:00')


def run_scrape(writer: SupabaseWriter, logger_callback=None):
    _log = logger_callback if logger_callback else log
    _log("SCRAPE BASLIYOR...")
    session = requests.Session()
    scraped_at = get_turkey_now()
    scraped_at_utc = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S+00:00')
    total_rows = 0
    write_errors = 0
    market_stats = []
    
    # Tüm maçları topla (fixtures için)
    all_fixtures = {}  # match_id_hash -> fixture data
    all_moneyway_snapshots = []
    all_dropping_snapshots = []
    
    for dataset_key, url in DATASETS.items():
        table_name = MARKET_TABLE_MAP[dataset_key]
        history_table = f"{table_name}_history"
        extractor = EXTRACTORS[dataset_key]
        is_moneyway = dataset_key.startswith('moneyway')
        is_dropping = dataset_key.startswith('dropping')
        
        # Market type: 1X2, OU25, BTTS
        market = dataset_key.split('-')[1].upper()
        if market == 'OU25':
            market = 'OU25'
        elif market == 'BTTS':
            market = 'BTTS'
        else:
            market = '1X2'
        
        try:
            _log(f"  {dataset_key} cekiliyor...")
            table = fetch_table(url, session)
            rows = extractor(table)
            
            if rows:
                # Her satır için match_id_hash hesapla ve fixture/snapshot oluştur
                for row in rows:
                    home = row.get('home', '')
                    away = row.get('away', '')
                    league = row.get('league', '')
                    date_str = row.get('date', '')
                    
                    # Kickoff UTC hesapla
                    kickoff_utc = parse_date_to_kickoff(date_str)
                    
                    # match_id_hash üret
                    match_id_hash = make_match_id_hash(home, away, league, kickoff_utc)
                    
                    # Fixture kaydet (unique by match_id_hash)
                    if match_id_hash not in all_fixtures:
                        fixture_date = kickoff_utc[:10]  # YYYY-MM-DD
                        all_fixtures[match_id_hash] = {
                            'match_id_hash': match_id_hash,
                            'home_team': home[:100],
                            'away_team': away[:100],
                            'league': league[:150],
                            'kickoff_utc': kickoff_utc,
                            'fixture_date': fixture_date
                        }
                    
                    # Snapshot oluştur
                    if is_moneyway:
                        # Moneyway snapshot - market bazlı selections
                        if market == '1X2':
                            selections = [
                                ('1', row.get('odds1'), row.get('pct1'), row.get('amt1')),
                                ('X', row.get('oddsx'), row.get('pctx'), row.get('amtx')),
                                ('2', row.get('odds2'), row.get('pct2'), row.get('amt2'))
                            ]
                        elif market == 'OU25':
                            selections = [
                                ('O', row.get('over'), row.get('pctover'), row.get('amtover')),
                                ('U', row.get('under'), row.get('pctunder'), row.get('amtunder'))
                            ]
                        else:  # BTTS
                            selections = [
                                ('Y', row.get('oddsyes'), row.get('pctyes'), row.get('amtyes')),
                                ('N', row.get('oddsno'), row.get('pctno'), row.get('amtno'))
                            ]
                        
                        for sel, odds, share, volume in selections:
                            if odds or share or volume:
                                all_moneyway_snapshots.append({
                                    'match_id_hash': match_id_hash,
                                    'market': market,
                                    'selection': sel,
                                    'odds': float(odds) if odds and odds.replace('.','').isdigit() else None,
                                    'volume': _parse_volume(volume) if volume else None,
                                    'share': _parse_percent_value(share) if share else None,
                                    'scraped_at_utc': scraped_at_utc
                                })
                    
                    elif is_dropping:
                        # Dropping odds snapshot
                        if market == '1X2':
                            selections = [
                                ('1', row.get('odds1'), row.get('odds1_prev'), row.get('pct1'), row.get('amt1')),
                                ('X', row.get('oddsx'), row.get('oddsx_prev'), row.get('pctx'), row.get('amtx')),
                                ('2', row.get('odds2'), row.get('odds2_prev'), row.get('pct2'), row.get('amt2'))
                            ]
                        elif market == 'OU25':
                            selections = [
                                ('O', row.get('over'), row.get('over_prev'), row.get('pctover'), row.get('amtover')),
                                ('U', row.get('under'), row.get('under_prev'), row.get('pctunder'), row.get('amtunder'))
                            ]
                        else:  # BTTS
                            selections = [
                                ('Y', row.get('oddsyes'), row.get('oddsyes_prev'), row.get('pctyes'), row.get('amtyes')),
                                ('N', row.get('oddsno'), row.get('oddsno_prev'), row.get('pctno'), row.get('amtno'))
                            ]
                        
                        for sel, current, opening, share, volume in selections:
                            if current or opening:
                                cur_val = float(current) if current and current.replace('.','').isdigit() else None
                                open_val = float(opening) if opening and opening.replace('.','').isdigit() else None
                                drop_pct = None
                                if cur_val and open_val and open_val > 0:
                                    drop_pct = round((open_val - cur_val) / open_val * 100, 2)
                                
                                all_dropping_snapshots.append({
                                    'match_id_hash': match_id_hash,
                                    'market': market,
                                    'selection': sel,
                                    'opening_odds': open_val,
                                    'current_odds': cur_val,
                                    'drop_pct': drop_pct,
                                    'volume': _parse_volume(volume) if volume else None,
                                    'scraped_at_utc': scraped_at_utc
                                })
                
                # Mevcut history tablolarına da yaz (geriye uyumluluk)
                main_ok = writer.replace_table(table_name, rows)
                history_ok = writer.append_history(history_table, rows, scraped_at)
                
                if main_ok and history_ok:
                    total_rows += len(rows)
                    market_stats.append(f"{dataset_key}: {len(rows)}")
                    _log(f"  [OK] {dataset_key}: {len(rows)} satir")
                else:
                    write_errors += 1
                    if not main_ok:
                        _log(f"  [HATA] {dataset_key}: Ana tablo yazma basarisiz!")
                    if not history_ok:
                        _log(f"  [HATA] {dataset_key}: History tablo yazma basarisiz!")
            else:
                _log(f"  [!] {dataset_key}: Veri bulunamadi")
        except Exception as e:
            _log(f"  [HATA] {dataset_key}: {e}")
            import traceback
            _log(f"  [TRACEBACK] {traceback.format_exc()}")
            write_errors += 1
    
    # Fixtures UPSERT
    if all_fixtures:
        fixtures_list = list(all_fixtures.values())
        _log(f"  [FIXTURES] {len(fixtures_list)} mac fixtures'a yaziliyor...")
        if writer.upsert_fixtures(fixtures_list):
            _log(f"  [OK] Fixtures: {len(fixtures_list)} mac")
        else:
            _log(f"  [HATA] Fixtures yazma basarisiz!")
            write_errors += 1
    
    # Snapshots INSERT
    if all_moneyway_snapshots:
        _log(f"  [SNAPSHOTS] {len(all_moneyway_snapshots)} moneyway snapshot yaziliyor...")
        if writer.insert_snapshots('moneyway_snapshots', all_moneyway_snapshots):
            _log(f"  [OK] Moneyway snapshots: {len(all_moneyway_snapshots)}")
        else:
            _log(f"  [HATA] Moneyway snapshots yazma basarisiz!")
            write_errors += 1
    
    if all_dropping_snapshots:
        _log(f"  [SNAPSHOTS] {len(all_dropping_snapshots)} dropping snapshot yaziliyor...")
        if writer.insert_snapshots('dropping_odds_snapshots', all_dropping_snapshots):
            _log(f"  [OK] Dropping snapshots: {len(all_dropping_snapshots)}")
        else:
            _log(f"  [HATA] Dropping snapshots yazma basarisiz!")
            write_errors += 1
    
    if write_errors > 0:
        _log(f"UYARI: {write_errors} tabloda yazma hatasi olustu!")
    
    _log(f"Scrape tamamlandi - Toplam: {total_rows} satir, {len(all_fixtures)} fixture, {len(all_moneyway_snapshots)+len(all_dropping_snapshots)} snapshot")
    return total_rows


def _parse_volume(vol_str: str) -> float:
    """Parse volume string like '£ 1.5M' or '£ 500K' to float"""
    if not vol_str:
        return 0.0
    vol_str = vol_str.replace('£', '').replace(',', '').strip()
    multiplier = 1.0
    if vol_str.upper().endswith('M'):
        multiplier = 1000000
        vol_str = vol_str[:-1]
    elif vol_str.upper().endswith('K'):
        multiplier = 1000
        vol_str = vol_str[:-1]
    try:
        return float(vol_str.strip()) * multiplier
    except:
        return 0.0


def _parse_percent_value(pct_str: str) -> float:
    """Parse percent string like '45.5%' to float"""
    if not pct_str:
        return 0.0
    pct_str = pct_str.replace('%', '').strip()
    try:
        return float(pct_str)
    except:
        return 0.0


def run_alarm_calculations_safe(supabase_url: str, supabase_key: str, logger_callback=None):
    """Safely run alarm calculations after each scrape - catches errors to not break main scraper"""
    _log = logger_callback if logger_callback else log
    try:
        from alarm_calculator import AlarmCalculator
        _log("[ALARM SYNC] Scrape tamamlandi - Alarm hesaplamasi baslatiliyor...")
        calculator = AlarmCalculator(supabase_url, supabase_key, logger_callback=_log)
        total = calculator.run_all_calculations()
        _log(f"[ALARM SYNC] Tamamlandi - Toplam {total} alarm hesaplandi")
    except ImportError as e:
        _log(f"[ALARM SYNC] HATA - Alarm modulu yuklenemedi: {e}")
    except Exception as e:
        import traceback
        _log(f"[ALARM SYNC] HATA - {e}")
        _log(f"[ALARM SYNC] Traceback: {traceback.format_exc()}")


def main():
    print("=" * 50)
    print(f"  SmartXFlow Standalone Scraper v{VERSION}")
    print("  PC'de calisan bagimsiz veri toplayici + Alarm Hesaplama")
    print("=" * 50)
    print()
    
    config = load_config()
    
    # SERVICE_ROLE_KEY tercih et (RLS bypass için), yoksa ANON_KEY kullan
    supabase_key = config.get('SUPABASE_SERVICE_ROLE_KEY') or config.get('SUPABASE_ANON_KEY')
    key_type = "SERVICE_ROLE" if config.get('SUPABASE_SERVICE_ROLE_KEY') else "ANON"
    log(f"Supabase key: {key_type}")
    
    writer = SupabaseWriter(config['SUPABASE_URL'], supabase_key)
    
    log(f"Supabase baglantisi hazir")
    log(f"Scrape araligi: {SCRAPE_INTERVAL_MINUTES} dakika")
    log("-" * 50)
    
    last_cleanup_date = None
    
    while True:
        try:
            run_scrape(writer)
        except Exception as e:
            log(f"HATA: {e}")
        
        run_alarm_calculations_safe(config['SUPABASE_URL'], config['SUPABASE_ANON_KEY'])
        
        if TURKEY_TZ:
            current_date = datetime.now(TURKEY_TZ).date()
        else:
            current_date = datetime.now().date()
        
        if last_cleanup_date != current_date:
            try:
                cleanup_old_matches(writer)
                last_cleanup_date = current_date
            except Exception as e:
                log(f"[Cleanup] Hata: {e}")
        
        log(f"{SCRAPE_INTERVAL_MINUTES} dakika bekleniyor...")
        log("-" * 50)
        time.sleep(SCRAPE_INTERVAL_MINUTES * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nProgram sonlandirildi.")
    except Exception as e:
        print(f"\nKritik hata: {e}")
        input("Devam etmek icin Enter'a basin...")
