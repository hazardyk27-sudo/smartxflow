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
        """String normalizasyonu for match_id_hash - MUST match core/hash_utils.py exactly"""
        if not value:
            return ""
        value = value.strip()
        # Türkçe karakter normalizasyonu
        tr_map = {'ş': 's', 'Ş': 'S', 'ğ': 'g', 'Ğ': 'G', 'ü': 'u', 'Ü': 'U',
                  'ı': 'i', 'İ': 'I', 'ö': 'o', 'Ö': 'O', 'ç': 'c', 'Ç': 'C'}
        for tr_char, en_char in tr_map.items():
            value = value.replace(tr_char, en_char)
        value = value.lower()
        # Remove special characters (keep only lowercase letters, digits, space)
        value = re.sub(r'[^a-z0-9\s]', '', value)
        value = ' '.join(value.split())
        # Remove team suffixes (fc, fk, sk, sc, afc, cf, ac, as)
        suffixes = ['fc', 'fk', 'sk', 'sc', 'afc', 'cf', 'ac', 'as']
        changed = True
        while changed:
            changed = False
            for suffix in suffixes:
                if value.endswith(' ' + suffix):
                    value = value[:-len(suffix)-1].strip()
                    changed = True
                    break
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

    def make_match_id_hash(home: str, away: str, league: str, kickoff_utc: str = None) -> str:
        """12 karakterlik MD5 hash üret - Format: league|home|away (kickoff KULLANILMIYOR)"""
        home_norm = normalize_field_for_hash(home)
        away_norm = normalize_field_for_hash(away)
        league_norm = normalize_field_for_hash(league)
        canonical = f"{league_norm}|{home_norm}|{away_norm}"
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

JSON_API_URL = "https://arbworld.net/api/get-runners.php"

DATASETS = {
    "moneyway-1x2":  {"type": "mw", "market": "MATCH_ODDS"},
    "moneyway-ou25": {"type": "mw", "market": "OVER_UNDER_25"},
    "moneyway-btts": {"type": "mw", "market": "BOTH_TEAMS_TO_SCORE"},
    "dropping-1x2":  {"type": "do", "market": "MATCH_ODDS"},
    "dropping-ou25": {"type": "do", "market": "OVER_UNDER_25"},
    "dropping-btts": {"type": "do", "market": "BOTH_TEAMS_TO_SCORE"},
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
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://arbworld.net/?lang=en&type=mw&sport=soccer",
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


def fetch_json(params: Dict[str, str], session: requests.Session) -> List[Dict[str, Any]]:
    """Fetch JSON data from Arbworld get-runners.php API.

    params: {"type": "mw|do", "market": "MATCH_ODDS|OVER_UNDER_25|BOTH_TEAMS_TO_SCORE"}
    Returns: list of match dicts (the 'data' field of the response).
    """
    full_params = {
        "type": params["type"],
        "sport": "soccer",
        "order": "date",
        "market": params["market"],
        "day": "",
        "lang": "en",
    }
    headers = dict(HEADERS)
    headers["Referer"] = (
        f"https://arbworld.net/?lang=en&type={params['type']}"
        f"&sport=soccer&market={params['market']}"
    )
    resp = session.get(
        JSON_API_URL,
        params=full_params,
        headers=headers,
        timeout=30,
        verify=SSL_VERIFY,
    )
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("success"):
        raise RuntimeError(f"API success=false: {str(payload)[:200]}")
    return payload.get("data") or []


def _normalize_json_date(date_str: str) -> str:
    """Convert Arbworld JSON date 'YYYY-MM-DD HH:MM:SS' (UTC) to ISO with +00:00."""
    if not date_str:
        return ""
    s = date_str.strip()
    try:
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    except Exception:
        return s


def _coef(v) -> str:
    """Format coefficient value to string, empty if zero/missing."""
    try:
        f = float(v)
        if f <= 0:
            return ""
        return f"{f:g}"
    except Exception:
        return ""


def _vol_amt(v) -> str:
    """Format volume to '£ N' string (compatible with downstream _parse_volume)."""
    try:
        f = float(v)
        if f <= 0:
            return ""
        if f == int(f):
            return f"£ {int(f)}"
        return f"£ {f:g}"
    except Exception:
        return ""


def _vol_pct(v: float, total: float) -> str:
    """Compute outcome share as 'NN.N%' string."""
    try:
        if total <= 0 or v <= 0:
            return ""
        return f"{(v / total * 100):.1f}%"
    except Exception:
        return ""


def _trend(cur, prev) -> str:
    """Calculate price-movement trend ('up'/'down'/'')."""
    try:
        c = float(cur) if cur not in (None, "", 0) else 0.0
        p = float(prev) if prev not in (None, "", 0) else 0.0
        if c <= 0 or p <= 0 or abs(c - p) < 0.001:
            return ""
        return "up" if c > p else "down"
    except Exception:
        return ""


def _row_common(rec: Dict[str, Any]) -> Dict[str, str]:
    """Shared fields extracted from JSON record."""
    return {
        "id": str(rec.get("market_id", "")),
        "league": rec.get("leage", "") or "",
        "date": _normalize_json_date(rec.get("date", "")),
        "home": rec.get("home", "") or "",
        "away": rec.get("away", "") or "",
    }


def extract_moneyway_1x2(data: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    rows = []
    for rec in data:
        if not rec.get("home") or not rec.get("away"):
            continue
        v1 = float(rec.get("volume_1") or 0)
        vx = float(rec.get("volume_x") or 0)
        v2 = float(rec.get("volume_2") or 0)
        total = v1 + vx + v2
        row = _row_common(rec)
        row.update({
            "odds1": _coef(rec.get("coef_1_new")),
            "oddsx": _coef(rec.get("coef_x_new")),
            "odds2": _coef(rec.get("coef_2_new")),
            "pct1": _vol_pct(v1, total),
            "amt1": _vol_amt(v1),
            "pctx": _vol_pct(vx, total),
            "amtx": _vol_amt(vx),
            "pct2": _vol_pct(v2, total),
            "amt2": _vol_amt(v2),
            "volume": _vol_amt(total),
        })
        rows.append(row)
    return rows


def extract_moneyway_ou25(data: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    rows = []
    for rec in data:
        if not rec.get("home") or not rec.get("away"):
            continue
        # JSON convention: coef_1 = Over, coef_2 = Under (matches site column order)
        v_over = float(rec.get("volume_1") or 0)
        v_under = float(rec.get("volume_2") or 0)
        total = v_over + v_under
        row = _row_common(rec)
        row.update({
            "over": _coef(rec.get("coef_1_new")),
            "line": "2.5",
            "under": _coef(rec.get("coef_2_new")),
            "pctover": _vol_pct(v_over, total),
            "amtover": _vol_amt(v_over),
            "pctunder": _vol_pct(v_under, total),
            "amtunder": _vol_amt(v_under),
            "volume": _vol_amt(total),
        })
        rows.append(row)
    return rows


def extract_moneyway_btts(data: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    rows = []
    for rec in data:
        if not rec.get("home") or not rec.get("away"):
            continue
        # JSON convention: coef_1 = Yes, coef_2 = No
        v_yes = float(rec.get("volume_1") or 0)
        v_no = float(rec.get("volume_2") or 0)
        total = v_yes + v_no
        row = _row_common(rec)
        row.update({
            "yes": _coef(rec.get("coef_1_new")),
            "no": _coef(rec.get("coef_2_new")),
            "pctyes": _vol_pct(v_yes, total),
            "amtyes": _vol_amt(v_yes),
            "pctno": _vol_pct(v_no, total),
            "amtno": _vol_amt(v_no),
            "volume": _vol_amt(total),
        })
        rows.append(row)
    return rows


def extract_dropping_1x2(data: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    rows = []
    for rec in data:
        if not rec.get("home") or not rec.get("away"):
            continue
        v1 = float(rec.get("volume_1") or 0)
        vx = float(rec.get("volume_x") or 0)
        v2 = float(rec.get("volume_2") or 0)
        total = v1 + vx + v2
        c1, cx, c2 = rec.get("coef_1_new"), rec.get("coef_x_new"), rec.get("coef_2_new")
        s1, sx, s2 = rec.get("coef_1"), rec.get("coef_x"), rec.get("coef_2")
        row = _row_common(rec)
        row.update({
            "odds1": _coef(c1),
            "odds1_prev": _coef(s1),
            "oddsx": _coef(cx),
            "oddsx_prev": _coef(sx),
            "odds2": _coef(c2),
            "odds2_prev": _coef(s2),
            "trend1": _trend(c1, s1),
            "trendx": _trend(cx, sx),
            "trend2": _trend(c2, s2),
            "volume": _vol_amt(total),
        })
        rows.append(row)
    return rows


def extract_dropping_ou25(data: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    rows = []
    for rec in data:
        if not rec.get("home") or not rec.get("away"):
            continue
        v_over = float(rec.get("volume_1") or 0)
        v_under = float(rec.get("volume_2") or 0)
        total = v_over + v_under
        c_over_cur, c_over_prev = rec.get("coef_1_new"), rec.get("coef_1")
        c_under_cur, c_under_prev = rec.get("coef_2_new"), rec.get("coef_2")
        row = _row_common(rec)
        row.update({
            "over": _coef(c_over_cur),
            "over_prev": _coef(c_over_prev),
            "line": "2.5",
            "under": _coef(c_under_cur),
            "under_prev": _coef(c_under_prev),
            "trendover": _trend(c_over_cur, c_over_prev),
            "trendunder": _trend(c_under_cur, c_under_prev),
            "pctover": _vol_pct(v_over, total),
            "amtover": _vol_amt(v_over),
            "pctunder": _vol_pct(v_under, total),
            "amtunder": _vol_amt(v_under),
            "volume": _vol_amt(total),
        })
        rows.append(row)
    return rows


def extract_dropping_btts(data: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    rows = []
    for rec in data:
        if not rec.get("home") or not rec.get("away"):
            continue
        v_yes = float(rec.get("volume_1") or 0)
        v_no = float(rec.get("volume_2") or 0)
        total = v_yes + v_no
        c_yes_cur, c_yes_prev = rec.get("coef_1_new"), rec.get("coef_1")
        c_no_cur, c_no_prev = rec.get("coef_2_new"), rec.get("coef_2")
        row = _row_common(rec)
        row.update({
            "oddsyes": _coef(c_yes_cur),
            "oddsyes_prev": _coef(c_yes_prev),
            "oddsno": _coef(c_no_cur),
            "oddsno_prev": _coef(c_no_prev),
            "trendyes": _trend(c_yes_cur, c_yes_prev),
            "trendno": _trend(c_no_cur, c_no_prev),
            "pctyes": _vol_pct(v_yes, total),
            "amtyes": _vol_amt(v_yes),
            "pctno": _vol_pct(v_no, total),
            "amtno": _vol_amt(v_no),
            "volume": _vol_amt(total),
        })
        rows.append(row)
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
    D-8+ maçlarını sil (son 7 gün hariç tüm eski maçlar)
    - D (bugün) ve D+1, D+2... (ileri tarihli): Korunur
    - D-1..D-7 (son 7 gün): Korunur
    - D-8+ (öncesi): Silinir
    
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
    d_minus_8 = today - timedelta(days=8)
    
    _log(f"[Cleanup] D-8+ silme: {d_minus_8} ve oncesi silinecek (bugun={today}, dun={yesterday}, son 7 gun korunur)")
    
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
            cutoff_iso = d_minus_8.strftime('%Y-%m-%dT00:00:00')
            url = f"{writer._rest_url(table)}?scraped_at=lt.{cutoff_iso}"
            resp = requests.delete(url, headers=writer._headers(), timeout=30)
            if resp.status_code in [200, 204]:
                _log(f"  [Cleanup] {table}: D-8+ kayitlar silindi")
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
    for offset in range(0, 8):
        d = today - timedelta(days=offset)
        if offset <= 7:
            month_str = months_map[d.month].capitalize()
            valid_dates.append(f"{d.day:02d}.{month_str}")
            valid_dates.append(f"{d.day}.{month_str}")
    
    _log(f"  [Cleanup] Gecerli tarihler: {valid_dates[:4]}... ({len(valid_dates)} kalip)")
    
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
        cutoff_date = d_minus_8.strftime('%Y-%m-%d')
        url = f"{writer._rest_url('fixtures')}?fixture_date=lt.{cutoff_date}"
        resp = requests.delete(url, headers=writer._headers(), timeout=30)
        if resp.status_code in [200, 204]:
            _log(f"  [Cleanup] fixtures: D-8+ kayitlar silindi")
            total_deleted += 1
    except Exception as e:
        _log(f"  [Cleanup] fixtures: Hata - {e}")
    
    if total_deleted > 0:
        _log(f"[Cleanup] Tamamlandi - {total_deleted} islem")
    
    # 4. Orphan history kayitlarini temizle (fixtures'da olmayan match_id_hash'ler)
    try:
        # Önce aktif fixture hash'lerini al (pagination ile)
        active_hashes = set()
        offset = 0
        page_size = 1000
        
        while True:
            fixture_resp = requests.get(
                f"{writer._rest_url('fixtures')}?select=match_id_hash&limit={page_size}&offset={offset}",
                headers=writer._headers(), timeout=60
            )
            if fixture_resp.status_code != 200:
                break
            batch = fixture_resp.json()
            if not batch:
                break
            for f in batch:
                if f.get('match_id_hash'):
                    active_hashes.add(f.get('match_id_hash'))
            if len(batch) < page_size:
                break
            offset += page_size
        
        if active_hashes:
            _log(f"  [Cleanup] {len(active_hashes)} aktif fixture hash'i")
            
            for table in history_tables:
                try:
                    # History tablosundaki tüm unique hash'leri al (pagination ile)
                    history_hashes = set()
                    offset = 0
                    
                    while True:
                        hist_resp = requests.get(
                            f"{writer._rest_url(table)}?select=match_id_hash&limit={page_size}&offset={offset}",
                            headers=writer._headers(), timeout=60
                        )
                        if hist_resp.status_code != 200:
                            break
                        batch = hist_resp.json()
                        if not batch:
                            break
                        for h in batch:
                            if h.get('match_id_hash'):
                                history_hashes.add(h.get('match_id_hash'))
                        if len(batch) < page_size:
                            break
                        offset += page_size
                    
                    orphan_hashes = history_hashes - active_hashes
                    
                    if orphan_hashes:
                        # Orphan hash'leri batch'ler halinde sil
                        orphan_list = list(orphan_hashes)
                        for i in range(0, len(orphan_list), 50):
                            batch = orphan_list[i:i+50]
                            hash_filter = ','.join(batch)
                            requests.delete(
                                f"{writer._rest_url(table)}?match_id_hash=in.({hash_filter})",
                                headers=writer._headers(), timeout=30
                            )
                        _log(f"  [Cleanup] {table}: {len(orphan_hashes)} orphan kayit silindi")
                        total_deleted += len(orphan_hashes)
                except Exception as e:
                    _log(f"  [Cleanup] {table} orphan cleanup hatasi: {e}")
    except Exception as e:
        _log(f"[Cleanup] Orphan cleanup hatasi: {e}")
    
    # 5. Alarm tablolarini temizle
    try:
        from alarm_calculator import AlarmCalculator
        alarm_calc = AlarmCalculator(
            supabase_url=writer.supabase_url,
            supabase_key=writer.supabase_key
        )
        alarm_deleted = alarm_calc.cleanup_old_alarms(days_to_keep=7)
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
    
    # Pattern 0: ISO format from JSON normalization "2026-04-29T19:00:00+00:00"
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})', date_str)
    if m:
        try:
            y, mo, d, h, mi, s = map(int, m.groups())
            dt = datetime(y, mo, d, h, mi, s)
            return dt.strftime('%Y-%m-%dT%H:%M:%S+00:00')
        except Exception:
            pass
    
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
    
    for dataset_key, params in DATASETS.items():
        table_name = MARKET_TABLE_MAP[dataset_key]
        history_table = f"{table_name}_history"
        extractor = EXTRACTORS[dataset_key]
        is_moneyway = dataset_key.startswith('moneyway')
        
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
            data = fetch_json(params, session)
            rows = extractor(data)
            
            if rows:
                # Maç başlamış (kickoff geçmiş) satırları filtrele - canlı veri live_scraper'a bırakılır
                _now_utc = datetime.utcnow()
                _prematch = []
                for _r in rows:
                    _ko = parse_date_to_kickoff(_r.get('date', ''))
                    try:
                        _ko_dt = datetime.strptime(_ko[:19], '%Y-%m-%dT%H:%M:%S')
                        if _ko_dt > _now_utc:
                            _prematch.append(_r)
                    except Exception:
                        _prematch.append(_r)
                _skipped = len(rows) - len(_prematch)
                if _skipped > 0:
                    _log(f"  [PREMATCH FILTER] {_skipped} canli mac atlandi (kickoff gecmis)")
                rows = _prematch

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
    
    if write_errors > 0:
        _log(f"UYARI: {write_errors} tabloda yazma hatasi olustu!")
    
    _log(f"Scrape tamamlandi - Toplam: {total_rows} satir, {len(all_fixtures)} fixture, {len(all_moneyway_snapshots)} snapshot")
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
