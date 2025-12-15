"""
SmartXFlow Alarm Calculator Module v1.23
Standalone alarm calculation for PC-based scraper
Calculates: Sharp, Insider, BigMoney, VolumeShock, Dropping, PublicMove, VolumeLeader
OPTIMIZED: Batch fetch per market, in-memory calculations
DEFAULT_SETTINGS: Fallback values for all alarm types when Supabase config missing
PHASE 2: match_id_hash contract compliant (league|kickoff|home|away)
"""

import json
import os
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Callable

try:
    import pytz
    TURKEY_TZ = pytz.timezone('Europe/Istanbul')
except ImportError:
    TURKEY_TZ = None

try:
    import httpx
except ImportError:
    import requests as httpx

_logger_callback: Optional[Callable[[str], None]] = None


def set_logger(callback: Callable[[str], None]):
    global _logger_callback
    _logger_callback = callback


def now_turkey():
    if TURKEY_TZ:
        return datetime.now(TURKEY_TZ)
    return datetime.now()


def now_turkey_iso():
    """Return ISO timestamp WITH timezone offset (+03:00) to prevent double-conversion"""
    dt = now_turkey()
    # Include timezone offset in ISO string
    return dt.strftime('%Y-%m-%dT%H:%M:%S+03:00')


def log(msg: str):
    """Log message using callback or print - ALWAYS outputs something"""
    timestamp = now_turkey().strftime('%H:%M')
    full_msg = f"[{timestamp}] {msg}"
    
    # Always try callback first
    if _logger_callback:
        try:
            _logger_callback(full_msg)
        except Exception as e:
            print(f"[AlarmCalc] Logger callback error: {e}")
            print(full_msg)
    else:
        print(f"[AlarmCalc-NoCallback] {full_msg}")


def parse_float(val) -> float:
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    try:
        s = str(val).replace(',', '.').replace('£', '').replace('%', '').strip()
        return float(s) if s else 0.0
    except:
        return 0.0


def parse_volume(val) -> float:
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    try:
        s = str(val).replace('£', '').replace(',', '').replace(' ', '').strip()
        return float(s) if s else 0.0
    except:
        return 0.0


def normalize_team_name(name: str) -> str:
    """Normalize team name for consistent cache key matching.
    Removes common suffixes like FC, SC, etc. and normalizes whitespace.
    Examples: 'Aston Villa FC' -> 'aston villa', 'Man City' -> 'man city'
    """
    if not name:
        return ""
    n = name.lower().strip()
    suffixes = [' fc', ' sc', ' cf', ' afc', ' bc', ' fk', ' sk', ' as', ' ac', ' us', ' ss']
    for suffix in suffixes:
        if n.endswith(suffix):
            n = n[:-len(suffix)].strip()
    n = ' '.join(n.split())
    return n


def normalize_field(value: str) -> str:
    """
    IMMUTABLE CONTRACT: Normalize field for match_id_hash generation.
    Rules (per replit.md):
    - trim (strip leading/trailing whitespace)
    - Turkish dotted/dotless I normalization BEFORE lowercase: ı → i, İ → I, then lowercase
    - collapse multiple spaces to single space
    """
    if not value:
        return ""
    value = str(value).strip()
    value = value.replace('ı', 'i').replace('İ', 'I')
    value = value.lower()
    value = ' '.join(value.split())
    return value


def normalize_kickoff(kickoff: str) -> str:
    """
    IMMUTABLE CONTRACT: Normalize kickoff for match_id_hash generation.
    Rules (per replit.md):
    - Must be UTC timezone  
    - Output format: YYYY-MM-DDTHH:MM (minute precision, no seconds)
    - Strips ALL timezone suffixes (Z, +00:00, +03:00, etc.)
    
    WARNING: Admin.exe must provide UTC kickoff times. Turkey timezone (+03:00) 
    must be converted to UTC before calling this function.
    """
    if not kickoff:
        return ""
    kickoff = str(kickoff).strip()
    
    import re
    kickoff = re.sub(r'[+-]\d{2}:\d{2}$', '', kickoff)
    kickoff = kickoff.replace('Z', '')
    
    if 'T' in kickoff and len(kickoff) >= 16:
        return kickoff[:16]
    
    if len(kickoff) >= 10 and kickoff[4] == '-':
        return kickoff[:16] if len(kickoff) >= 16 else kickoff[:10] + "T00:00"
    
    return kickoff


def generate_match_id_hash(home: str, away: str, league: str, kickoff: str) -> str:
    """
    IMMUTABLE CONTRACT: Generate unique 12-character match ID hash.
    Format: league|kickoff|home|away (all normalized)
    Hash: MD5, first 12 hex characters
    
    This MUST match app.py generate_match_id() exactly.
    """
    home_norm = normalize_field(home)
    away_norm = normalize_field(away)
    league_norm = normalize_field(league)
    kickoff_norm = normalize_kickoff(kickoff)
    
    canonical = f"{league_norm}|{kickoff_norm}|{home_norm}|{away_norm}"
    
    return hashlib.md5(canonical.encode('utf-8')).hexdigest()[:12]


def parse_match_date(date_str: str) -> Optional[datetime]:
    if not date_str:
        return None
    try:
        today = now_turkey().date()
        date_part = date_str.split()[0]
        
        if '.' in date_part:
            parts = date_part.split('.')
            if len(parts) == 2:
                day = int(parts[0])
                month_abbr = parts[1][:3]
                month_map = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                            'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12}
                month = month_map.get(month_abbr, today.month)
                return datetime(today.year, month, day)
            elif len(parts) == 3:
                return datetime.strptime(date_part, '%d.%m.%Y')
        elif '-' in date_part:
            return datetime.strptime(date_part.split('T')[0], '%Y-%m-%d')
    except:
        pass
    return None


class AlarmCalculator:
    """Supabase-based alarm calculator - OPTIMIZED with batch fetch"""
    
    def __init__(self, supabase_url: str, supabase_key: str, logger_callback: Optional[Callable[[str], None]] = None):
        self.url = supabase_url
        self.key = supabase_key
        self.configs = {}
        self._history_cache = {}
        self._matches_cache = {}
        if logger_callback:
            set_logger(logger_callback)
        self.load_configs()
    
    def _headers(self) -> Dict[str, str]:
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
    
    def _rest_url(self, table: str) -> str:
        return f"{self.url}/rest/v1/{table}"
    
    def _get(self, table: str, params: str = "") -> List[Dict]:
        try:
            url = f"{self._rest_url(table)}?{params}" if params else self._rest_url(table)
            if hasattr(httpx, 'get'):
                resp = httpx.get(url, headers=self._headers(), timeout=30)
                if resp.status_code == 200:
                    return resp.json()
            else:
                resp = httpx.get(url, headers=self._headers(), timeout=30)
                if resp.status_code == 200:
                    return resp.json()
        except Exception as e:
            log(f"GET error {table}: {e}")
        return []
    
    def _post(self, table: str, data: List[Dict], on_conflict=None) -> bool:
        try:
            headers = self._headers()
            headers["Prefer"] = "resolution=merge-duplicates"
            url = self._rest_url(table)
            if on_conflict:
                url = f"{url}?on_conflict={on_conflict}"
            if hasattr(httpx, 'post'):
                resp = httpx.post(url, headers=headers, json=data, timeout=30)
            else:
                resp = httpx.post(url, headers=headers, json=data, timeout=30)
            
            if resp.status_code in [200, 201]:
                return True
            else:
                # HTTP ERROR LOGLAMA - Sessiz hataları önle
                log(f"[POST ERROR] {table}: HTTP {resp.status_code}")
                try:
                    error_body = resp.text[:500] if hasattr(resp, 'text') else str(resp.content[:500])
                    log(f"[POST ERROR] Response: {error_body}")
                except:
                    pass
                if data and len(data) > 0:
                    log(f"[POST ERROR] First record keys: {list(data[0].keys())}")
                return False
        except Exception as e:
            log(f"POST error {table}: {e}")
        return False
    
    def _delete(self, table: str, params: str) -> bool:
        try:
            if not params or params.strip() == '':
                params = 'id=gte.1'
            url = f"{self._rest_url(table)}?{params}"
            headers = self._headers()
            headers['Prefer'] = 'return=representation,count=exact'
            resp = httpx.delete(url, headers=headers, timeout=30)
            content_range = resp.headers.get('Content-Range', '')
            if resp.status_code in [200, 204]:
                deleted_count = 0
                if content_range:
                    try:
                        parts = content_range.split('/')
                        if len(parts) > 1 and parts[1] != '*':
                            deleted_count = int(parts[1])
                    except:
                        pass
                log(f"[DELETE] {table}: Deleted {deleted_count} rows (HTTP {resp.status_code})")
                return True
            else:
                log(f"[DELETE] {table}: Failed HTTP {resp.status_code} - {resp.text[:200]}")
                return False
        except Exception as e:
            log(f"DELETE error {table}: {e}")
        return False
    
    def _upsert_alarms(self, table: str, alarms: List[Dict], key_fields: List[str]) -> int:
        """True UPSERT - insert or update existing records based on key_fields
        IMPORTANT: Preserves original trigger_at AND created_at for existing alarms
        """
        if not alarms:
            return 0
        
        try:
            # Remove duplicates from batch (keep last occurrence)
            seen = {}
            for alarm in alarms:
                key_parts = [str(alarm.get(f, '')) for f in key_fields]
                key = '|'.join(key_parts)
                seen[key] = alarm
            alarms = list(seen.values())
            log(f"[UPSERT] {table}: {len(alarms)} unique alarms after dedup")
            
            # Build select fields dynamically from key_fields + timestamp fields
            select_fields = ','.join(key_fields + ['trigger_at', 'created_at'])
            existing_data = {}
            try:
                existing = self._get(table, f'select={select_fields}')
                if existing:
                    for e in existing:
                        # Build key from all key_fields dynamically
                        key_parts = [str(e.get(f, '')) for f in key_fields]
                        key = '|'.join(key_parts)
                        # Store both trigger_at and created_at
                        existing_data[key] = {
                            'trigger_at': e.get('trigger_at'),
                            'created_at': e.get('created_at')
                        }
                    log(f"[UPSERT] Found {len(existing_data)} existing {table} records")
            except Exception as ex:
                log(f"[UPSERT] Could not fetch existing records: {ex}")
            
            # Preserve original timestamps for existing alarms
            preserved_count = 0
            for alarm in alarms:
                # Build key from all key_fields dynamically
                key_parts = [str(alarm.get(f, '')) for f in key_fields]
                key = '|'.join(key_parts)
                if key in existing_data:
                    orig = existing_data[key]
                    # Preserve timestamp fields from first detection
                    if orig.get('trigger_at'):
                        alarm['trigger_at'] = orig['trigger_at']
                    if orig.get('created_at'):
                        alarm['created_at'] = orig['created_at']
                    preserved_count += 1
            
            if preserved_count > 0:
                log(f"[UPSERT] Preserved timestamps for {preserved_count} existing alarms")
            
            on_conflict = ",".join(key_fields)
            if self._post(table, alarms, on_conflict=on_conflict):
                log(f"[UPSERT] {table}: {len(alarms)} alarms upserted (on_conflict={on_conflict})")
                return len(alarms)
            else:
                log(f"[UPSERT] {table}: POST failed, trying without on_conflict")
                if self._post(table, alarms):
                    return len(alarms)
        except Exception as e:
            log(f"Upsert error {table}: {e}")
        return 0
    
    def load_configs(self):
        """Load all alarm configs from Supabase alarm_settings table"""
        self._load_configs_from_db()
    
    def save_config_to_db(self, alarm_type: str, config: Dict, enabled: bool = True) -> bool:
        """Save alarm config to Supabase alarm_settings table
        Admin Panel → Supabase yazma fonksiyonu
        
        Args:
            alarm_type: Alarm türü (sharp, insider, bigmoney, volumeshock, dropping, publicmove, volumeleader)
            config: Config dict (tüm ayarlar)
            enabled: Alarm aktif mi
        
        Returns:
            True if successful
        """
        try:
            payload = {
                'alarm_type': alarm_type,
                'enabled': enabled,
                'config': config,
                'updated_at': now_turkey_iso()
            }
            
            # UPSERT with on_conflict
            url = f"{self._rest_url('alarm_settings')}?on_conflict=alarm_type"
            headers = self._headers()
            headers['Prefer'] = 'resolution=merge-duplicates'
            
            if hasattr(httpx, 'post'):
                resp = httpx.post(url, headers=headers, json=[payload], timeout=30)
            else:
                import requests as req
                resp = req.post(url, headers=headers, json=[payload], timeout=30)
            
            if resp.status_code in [200, 201]:
                log(f"[CONFIG SAVE] {alarm_type}: Supabase'e kaydedildi")
                # Update local cache
                self.configs[alarm_type] = {'enabled': enabled, **config}
                return True
            else:
                log(f"[CONFIG SAVE ERROR] {alarm_type}: HTTP {resp.status_code}")
                log(f"[CONFIG SAVE ERROR] Response: {resp.text[:500]}")
                return False
        except Exception as e:
            log(f"[CONFIG SAVE ERROR] {alarm_type}: {e}")
            return False
    
    def save_all_configs_to_db(self, configs: Dict) -> int:
        """Save all alarm configs to Supabase
        
        Args:
            configs: Dict of {alarm_type: {config...}}
        
        Returns:
            Number of successfully saved configs
        """
        success_count = 0
        for alarm_type, config_data in configs.items():
            if isinstance(config_data, dict):
                # enabled'ı al - default yok, açıkça belirtilmeli
                enabled = config_data.get('enabled')
                if enabled is None:
                    log(f"[CONFIG SAVE] UYARI: {alarm_type} için enabled değeri yok!")
                    enabled = True  # Sadece None ise varsayılan
                # enabled hariç diğer key'leri config olarak gönder
                config_without_enabled = {k: v for k, v in config_data.items() if k != 'enabled'}
            else:
                log(f"[CONFIG SAVE] UYARI: {alarm_type} için geçersiz config tipi!")
                enabled = True
                config_without_enabled = {}
            
            if self.save_config_to_db(alarm_type, config_without_enabled, enabled):
                success_count += 1
        log(f"[CONFIG SAVE] {success_count}/{len(configs)} config kaydedildi")
        return success_count
    
    def upsert_fixture(self, match: Dict) -> Optional[int]:
        """
        PHASE 2: Upsert fixture to fixtures table.
        Creates or updates match record and returns internal_id.
        
        Args:
            match: Dict with home, away, league, kickoff_utc
        
        Returns:
            internal_id if successful, None otherwise
        """
        try:
            home = match.get('home', '')
            away = match.get('away', '')
            league = match.get('league', '')
            kickoff = match.get('kickoff', match.get('kickoff_utc', ''))
            
            if not all([home, away, league, kickoff]):
                return None
            
            match_id_hash = generate_match_id_hash(home, away, league, kickoff)
            
            kickoff_utc = normalize_kickoff(kickoff)
            if len(kickoff_utc) == 16:
                kickoff_utc += ':00'
            
            fixture_date = kickoff_utc[:10] if len(kickoff_utc) >= 10 else ''
            
            payload = {
                'match_id_hash': match_id_hash,
                'home_team': home,
                'away_team': away,
                'league': league,
                'kickoff_utc': kickoff_utc,
                'fixture_date': fixture_date
            }
            
            url = f"{self._rest_url('fixtures')}?on_conflict=match_id_hash"
            headers = self._headers()
            headers['Prefer'] = 'resolution=merge-duplicates,return=representation'
            
            if hasattr(httpx, 'post'):
                resp = httpx.post(url, headers=headers, json=[payload], timeout=30)
            else:
                resp = httpx.post(url, headers=headers, json=[payload], timeout=30)
            
            if resp.status_code in [200, 201]:
                result = resp.json()
                if result and len(result) > 0:
                    return result[0].get('internal_id')
            else:
                log(f"[FIXTURE UPSERT ERROR] HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            log(f"[FIXTURE UPSERT ERROR] {e}")
        return None
    
    def upsert_fixtures_batch(self, matches: List[Dict]) -> int:
        """
        PHASE 2: Batch upsert fixtures to fixtures table.
        
        Args:
            matches: List of match dicts with home, away, league, kickoff_utc
        
        Returns:
            Number of successfully upserted fixtures
        """
        if not matches:
            return 0
        
        try:
            payloads = []
            for match in matches:
                home = match.get('home', '')
                away = match.get('away', '')
                league = match.get('league', '')
                kickoff = match.get('kickoff', match.get('kickoff_utc', ''))
                
                if not all([home, away, league, kickoff]):
                    continue
                
                match_id_hash = generate_match_id_hash(home, away, league, kickoff)
                
                kickoff_utc = normalize_kickoff(kickoff)
                if len(kickoff_utc) == 16:
                    kickoff_utc += ':00'
                
                fixture_date = kickoff_utc[:10] if len(kickoff_utc) >= 10 else ''
                
                payloads.append({
                    'match_id_hash': match_id_hash,
                    'home_team': home,
                    'away_team': away,
                    'league': league,
                    'kickoff_utc': kickoff_utc,
                    'fixture_date': fixture_date
                })
            
            if not payloads:
                return 0
            
            seen = {}
            for p in payloads:
                seen[p['match_id_hash']] = p
            payloads = list(seen.values())
            
            url = f"{self._rest_url('fixtures')}?on_conflict=match_id_hash"
            headers = self._headers()
            headers['Prefer'] = 'resolution=merge-duplicates'
            
            if hasattr(httpx, 'post'):
                resp = httpx.post(url, headers=headers, json=payloads, timeout=60)
            else:
                resp = httpx.post(url, headers=headers, json=payloads, timeout=60)
            
            if resp.status_code in [200, 201]:
                log(f"[FIXTURES] Batch upsert: {len(payloads)} fixtures")
                return len(payloads)
            else:
                log(f"[FIXTURES BATCH ERROR] HTTP {resp.status_code}: {resp.text[:300]}")
        except Exception as e:
            log(f"[FIXTURES BATCH ERROR] {e}")
        return 0
    
    def write_moneyway_snapshot(self, match_id_hash: str, market: str, selection: str,
                                 odds: float, volume: float, share: float) -> bool:
        """
        PHASE 2: Write moneyway snapshot to moneyway_snapshots table.
        """
        try:
            payload = {
                'match_id_hash': match_id_hash,
                'market': market,
                'selection': selection,
                'odds': round(odds, 2) if odds else None,
                'volume': round(volume, 2) if volume else None,
                'share': round(share, 2) if share else None
            }
            
            if self._post('moneyway_snapshots', [payload]):
                return True
        except Exception as e:
            log(f"[MONEYWAY SNAPSHOT ERROR] {e}")
        return False
    
    def write_moneyway_snapshots_batch(self, snapshots: List[Dict]) -> int:
        """
        PHASE 2: Batch write moneyway snapshots.
        
        Args:
            snapshots: List of dicts with match_id_hash, market, selection, odds, volume, share
        
        Returns:
            Number of successfully written snapshots
        """
        if not snapshots:
            return 0
        
        try:
            payloads = []
            for snap in snapshots:
                payloads.append({
                    'match_id_hash': snap.get('match_id_hash'),
                    'market': snap.get('market'),
                    'selection': snap.get('selection'),
                    'odds': round(snap.get('odds', 0), 2) if snap.get('odds') else None,
                    'volume': round(snap.get('volume', 0), 2) if snap.get('volume') else None,
                    'share': round(snap.get('share', 0), 2) if snap.get('share') else None
                })
            
            if self._post('moneyway_snapshots', payloads):
                log(f"[MONEYWAY] Batch write: {len(payloads)} snapshots")
                return len(payloads)
        except Exception as e:
            log(f"[MONEYWAY BATCH ERROR] {e}")
        return 0
    
    def write_dropping_snapshot(self, match_id_hash: str, market: str, selection: str,
                                 opening_odds: float, current_odds: float, 
                                 drop_pct: float, volume: float) -> bool:
        """
        PHASE 2: Write dropping odds snapshot to dropping_odds_snapshots table.
        """
        try:
            payload = {
                'match_id_hash': match_id_hash,
                'market': market,
                'selection': selection,
                'opening_odds': round(opening_odds, 2) if opening_odds else None,
                'current_odds': round(current_odds, 2) if current_odds else None,
                'drop_pct': round(drop_pct, 2) if drop_pct else None,
                'volume': round(volume, 2) if volume else None
            }
            
            if self._post('dropping_odds_snapshots', [payload]):
                return True
        except Exception as e:
            log(f"[DROPPING SNAPSHOT ERROR] {e}")
        return False
    
    def write_dropping_snapshots_batch(self, snapshots: List[Dict]) -> int:
        """
        PHASE 2: Batch write dropping odds snapshots.
        
        Args:
            snapshots: List of dicts with match_id_hash, market, selection, 
                       opening_odds, current_odds, drop_pct, volume
        
        Returns:
            Number of successfully written snapshots
        """
        if not snapshots:
            return 0
        
        try:
            payloads = []
            for snap in snapshots:
                payloads.append({
                    'match_id_hash': snap.get('match_id_hash'),
                    'market': snap.get('market'),
                    'selection': snap.get('selection'),
                    'opening_odds': round(snap.get('opening_odds', 0), 2) if snap.get('opening_odds') else None,
                    'current_odds': round(snap.get('current_odds', 0), 2) if snap.get('current_odds') else None,
                    'drop_pct': round(snap.get('drop_pct', 0), 2) if snap.get('drop_pct') else None,
                    'volume': round(snap.get('volume', 0), 2) if snap.get('volume') else None
                })
            
            if self._post('dropping_odds_snapshots', payloads):
                log(f"[DROPPING] Batch write: {len(payloads)} snapshots")
                return len(payloads)
        except Exception as e:
            log(f"[DROPPING BATCH ERROR] {e}")
        return 0

    def cleanup_old_alarms(self, days_to_keep: int = 2) -> int:
        """
        D-2+ alarmları sil (bugün ve dün hariç tüm eski alarmlar)
        - D (bugün): Korunur
        - D-1 (dün): Korunur  
        - D-2+ (öncesi): Silinir
        
        Args:
            days_to_keep: Kaç gün tutulacak (default: 2 = bugün + dün)
        
        Returns:
            Silinen tablo sayısı
        """
        try:
            from datetime import datetime, timedelta
            import pytz
        except ImportError:
            from datetime import datetime, timedelta
            pytz = None
        
        if pytz:
            try:
                tz = pytz.timezone('Europe/Istanbul')
                now = datetime.now(tz)
            except:
                now = datetime.utcnow()
        else:
            now = datetime.utcnow()
        
        today = now.date()
        cutoff_date = today - timedelta(days=days_to_keep)
        cutoff_iso = cutoff_date.strftime('%Y-%m-%dT00:00:00')
        
        log(f"[Cleanup] Alarm D-2+ silme: {cutoff_date} öncesi silinecek (bugün={today})")
        
        from urllib.parse import quote
        cutoff_encoded = quote(cutoff_iso, safe='')
        
        alarm_tables = [
            'sharp_alarms',
            'insider_alarms',
            'bigmoney_alarms',
            'volumeshock_alarms',
            'dropping_alarms',
            'publicmove_alarms',
            'volume_leader_alarms',
            'mim_alarms'
        ]
        
        total_deleted = 0
        
        for table in alarm_tables:
            try:
                url = f"{self._rest_url(table)}?created_at=lt.{cutoff_encoded}"
                headers = self._headers()
                headers['Prefer'] = 'return=representation,count=exact'
                
                resp = httpx.delete(url, headers=headers, timeout=30)
                
                if resp.status_code in [200, 204]:
                    deleted_count = 0
                    # Try Content-Range header first: "*/123" means 123 total affected
                    content_range = resp.headers.get('Content-Range', '')
                    if content_range and '/' in content_range:
                        try:
                            count_part = content_range.split('/')[-1]
                            if count_part and count_part != '*':
                                deleted_count = int(count_part)
                        except:
                            pass
                    # Fallback: try JSON body
                    if deleted_count == 0 and resp.content:
                        try:
                            deleted_data = resp.json()
                            if isinstance(deleted_data, list):
                                deleted_count = len(deleted_data)
                        except:
                            pass
                    if deleted_count > 0:
                        log(f"  [Cleanup] {table}: {deleted_count} D-2+ kayıt silindi")
                        total_deleted += deleted_count
                    else:
                        log(f"  [Cleanup] {table}: D-2+ kayıt yok veya zaten temiz")
                elif resp.status_code == 404:
                    pass
                else:
                    log(f"  [Cleanup] {table}: Silme hatası {resp.status_code}")
            except Exception as e:
                log(f"  [Cleanup] {table}: Hata - {e}")
        
        if total_deleted > 0:
            log(f"[Cleanup] Alarm temizleme tamamlandı - {total_deleted} tablo temizlendi")
        
        return total_deleted

    def refresh_configs(self):
        """Refresh configs from DB before each calculation cycle - LIVE RELOAD"""
        log("Refreshing alarm configs from Supabase...")
        old_configs = self.configs.copy()
        self._load_configs_from_db()
        
        changes = []
        for key in set(list(old_configs.keys()) + list(self.configs.keys())):
            old_val = old_configs.get(key, {})
            new_val = self.configs.get(key, {})
            if old_val != new_val:
                changes.append(key)
        
        if changes:
            log(f"Config changes detected: {', '.join(changes)}")
        return len(changes) > 0
    
    def _load_configs_from_db(self):
        """Internal: Load configs from alarm_settings table"""
        try:
            settings = self._get('alarm_settings', 'select=*')
            if settings and len(settings) > 0:
                new_configs = {}
                for setting in settings:
                    alarm_type = setting.get('alarm_type', '')
                    enabled = setting.get('enabled')  # Default yok - Supabase'den gelen değer kullanılır
                    config = setting.get('config', {})
                    if alarm_type:
                        new_configs[alarm_type] = {
                            'enabled': enabled,
                            **config
                        }
                if new_configs:
                    self.configs = new_configs
                    log(f"Loaded {len(self.configs)} alarm settings from DB")
                    # Log each alarm type's key config values
                    for atype, cfg in self.configs.items():
                        if atype == 'insider':
                            log(f"  [DB] insider: oran_dusus={cfg.get('oran_dusus_esigi')}, hacim_sok={cfg.get('hacim_sok_esigi')}, max_para={cfg.get('max_para')}, max_odds={cfg.get('max_odds_esigi')}")
                        elif atype == 'sharp':
                            log(f"  [DB] sharp: min_score={cfg.get('min_sharp_score')}, vol_mult={cfg.get('volume_multiplier')}")
                        elif atype == 'bigmoney':
                            log(f"  [DB] bigmoney: limit={cfg.get('big_money_limit')}")
                        elif atype == 'volumeshock':
                            log(f"  [DB] volumeshock: shock_mult={cfg.get('hacim_soku_min_esik', cfg.get('volume_shock_multiplier'))}")
                    return
            else:
                log("WARNING: alarm_settings returned empty - using defaults!")
        except Exception as e:
            log(f"Config load error: {e}")
        
        # Supabase'de eksik config varsa default değerlerden tamamla
        defaults = self._default_configs()
        for alarm_type, default_config in defaults.items():
            if alarm_type not in self.configs:
                log(f"  [DEFAULT] {alarm_type}: Supabase'de yok, default kullanılıyor")
                self.configs[alarm_type] = default_config
            else:
                # Merge: Supabase'de olmayan alanları default'tan al
                for key, value in default_config.items():
                    if key not in self.configs[alarm_type]:
                        self.configs[alarm_type][key] = value
        
        if not self.configs:
            log("ERROR: alarm_settings tablosu boş! Default değerler kullanılıyor.")
            self.configs = defaults
    
    def _default_configs(self) -> Dict:
        """Default alarm configs - replit.md'deki değerler
        Supabase'de config yoksa bu değerler kullanılır (fallback)"""
        return {
            'sharp': {
                'enabled': True,
                'min_share': 1,
                'max_odds_cap': 125,
                'max_share_cap': 1,
                'max_volume_cap': 124,
                'min_volume_1x2': 2999,
                'min_sharp_score': 100,
                'min_volume_btts': 999,
                'min_volume_ou25': 1499,
                'odds_range_1_max': 1.6,
                'odds_range_1_min': 1.01,
                'odds_range_2_max': 2.1,
                'odds_range_2_min': 1.59,
                'odds_range_3_max': 3.5,
                'odds_range_3_min': 2.09,
                'odds_range_4_max': 7,
                'odds_range_4_min': 3.49,
                'min_amount_change': 1999,
                'odds_range_1_mult': 20,
                'odds_range_2_mult': 12,
                'odds_range_3_mult': 8,
                'odds_range_4_mult': 3,
                'share_range_1_max': 30,
                'share_range_1_min': 1,
                'share_range_2_max': 60,
                'share_range_2_min': 30,
                'share_range_3_max': 80,
                'share_range_3_min': 60,
                'share_range_4_max': 100,
                'share_range_4_min': 80,
                'volume_multiplier': 15,
                'share_range_1_mult': 1,
                'share_range_2_mult': 1,
                'share_range_3_mult': 1,
                'share_range_4_mult': 1,
                'odds_range_1_min_drop': 1.5,
                'odds_range_2_min_drop': 3,
                'odds_range_3_min_drop': 7,
                'odds_range_4_min_drop': 15
            },
            'insider': {
                'enabled': True,
                'max_para': 100,
                'sure_dakika': 7,
                'max_odds_esigi': 1.85,
                'min_volume_1x2': 3000,
                'hacim_sok_esigi': 0.1,
                'min_volume_btts': 1000,
                'min_volume_ou25': 1000,
                'oran_dusus_esigi': 6
            },
            'bigmoney': {
                'enabled': True,
                'big_money_limit': 1499
            },
            'volumeshock': {
                'enabled': True,
                'min_volume_1x2': 1999,
                'min_volume_btts': 599,
                'min_volume_ou25': 999,
                'hacim_soku_min_esik': 7,
                'hacim_soku_min_saat': 2,
                'min_son_snapshot_para': 499
            },
            'dropping': {
                'enabled': True,
                'l2_enabled': True,
                'l3_enabled': True,
                'max_drop_l1': 13,
                'max_drop_l2': 20,
                'min_drop_l1': 8,
                'min_drop_l2': 13,
                'min_drop_l3': 20,
                'max_odds_1x2': 3.5,
                'max_odds_btts': 2.35,
                'max_odds_ou25': 2.35,
                'min_volume_1x2': 1,
                'min_volume_btts': 1,
                'min_volume_ou25': 1,
                'persistence_enabled': True,
                'persistence_minutes': 30
            },
            'publicmove': {
                'enabled': True,
                'min_share': 1,
                'max_odds_cap': 80,
                'max_share_cap': 50,
                'max_volume_cap': 70,
                'min_volume_1x2': 2999,
                'min_sharp_score': 60,
                'min_volume_btts': 999,
                'min_volume_ou25': 1499,
                'odds_range_1_max': 1.6,
                'odds_range_1_min': 1.01,
                'odds_range_2_max': 2.1,
                'odds_range_2_min': 1.59,
                'odds_range_3_max': 3.5,
                'odds_range_3_min': 2.09,
                'odds_range_4_max': 7,
                'odds_range_4_min': 3.49,
                'min_amount_change': 1999,
                'odds_range_1_mult': 10,
                'odds_range_2_mult': 6,
                'odds_range_3_mult': 3,
                'odds_range_4_mult': 1.5,
                'share_range_1_max': 30,
                'share_range_1_min': 1,
                'share_range_2_max': 60,
                'share_range_2_min': 30,
                'share_range_3_max': 80,
                'share_range_3_min': 60,
                'share_range_4_max': 100,
                'share_range_4_min': 80,
                'volume_multiplier': 10,
                'share_range_1_mult': 1,
                'share_range_2_mult': 3,
                'share_range_3_mult': 6,
                'share_range_4_mult': 10
            },
            'volumeleader': {
                'enabled': True,
                'min_volume_1x2': 2999,
                'min_volume_btts': 999,
                'min_volume_ou25': 1499,
                'leader_threshold': 50
            },
            'mim': {
                'enabled': True,
                'min_impact_for_alarm': 0.20,
                'level2_threshold': 0.40,
                'level3_threshold': 0.70,
                'min_market_volume': 1000,
                'min_new_money': 300
            }
        }
    
    def get_matches_with_latest(self, market: str) -> List[Dict]:
        """Get all matches with their latest data for a market (cached)"""
        if market in self._matches_cache:
            return self._matches_cache[market]
        
        log(f"FETCH {market} (latest)...")
        matches = self._get(market, 'select=*')
        log(f"  -> {len(matches)} matches")
        self._matches_cache[market] = matches
        return matches
    
    def batch_fetch_history(self, market: str) -> Dict[str, List[Dict]]:
        """Batch fetch ALL history for a market - NO LIMIT, tüm snapshot'lar okunur
        History zaten dünden önce temizlendiği için boyut küçük kalır.
        """
        history_table = f"{market}_history"
        
        if history_table in self._history_cache:
            return self._history_cache[history_table]
        
        log(f"[HISTORY] Fetching {history_table} (NO LIMIT - tüm snapshot'lar)...")
        
        rows = []
        offset = 0
        page_size = 1000
        
        while True:
            params = f"select=*&order=scraped_at.asc&limit={page_size}&offset={offset}"
            batch = self._get(history_table, params)
            if not batch:
                break
            rows.extend(batch)
            if len(batch) < page_size:
                break
            offset += page_size
        
        log(f"[HISTORY] {history_table}: {len(rows)} total snapshots loaded")
        
        history_map = {}
        for row in rows:
            home = row.get('home', '')
            away = row.get('away', '')
            key = f"{normalize_team_name(home)}|{normalize_team_name(away)}"
            if key not in history_map:
                history_map[key] = []
            history_map[key].append(row)
        
        self._history_cache[history_table] = history_map
        return history_map
    
    def get_match_history(self, home: str, away: str, history_table: str) -> List[Dict]:
        """Get historical snapshots for a match from cache (no individual API calls)"""
        if history_table not in self._history_cache:
            market = history_table.replace('_history', '')
            self.batch_fetch_history(market)
        
        history_map = self._history_cache.get(history_table, {})
        key = f"{normalize_team_name(home)}|{normalize_team_name(away)}"
        return history_map.get(key, [])
    
    def run_all_calculations(self) -> int:
        """Run all alarm calculations - OPTIMIZED with batch fetch
        Returns: Total number of alarms calculated
        """
        log("=" * 50)
        log("[ALARM SYNC] ALARM HESAPLAMA BASLADI")
        log(f"[ALARM SYNC] Supabase URL: {self.url[:40]}...")
        log("=" * 50)
        
        # LIVE RELOAD: Refresh configs from Supabase before calculations
        log("Config yenileniyor...")
        self.refresh_configs()
        log(f"Loaded configs: {list(self.configs.keys())}")
        
        self._history_cache = {}
        self._matches_cache = {}
        
        # Prefetch all data
        markets = ['moneyway_1x2', 'moneyway_ou25', 'moneyway_btts']
        for market in markets:
            try:
                matches = self.get_matches_with_latest(market)
                log(f"  {market}: {len(matches) if matches else 0} matches")
                history = self.batch_fetch_history(market)
                log(f"  {market}_history: {len(history) if history else 0} unique matches")
            except Exception as e:
                import traceback
                log(f"!!! Prefetch error {market}: {e}")
                log(f"Traceback: {traceback.format_exc()}")
        
        log("-" * 30)
        log(f"Cache stats: matches={len(self._matches_cache)}, history={len(self._history_cache)}")
        
        total_alarms = 0
        alarm_counts = {}
        
        log("1/7 BigMoney hesaplaniyor...")
        try:
            bigmoney_count = self.calculate_bigmoney_alarms() or 0
            alarm_counts['BigMoney'] = bigmoney_count
            total_alarms += bigmoney_count
            log(f"  -> BigMoney: {bigmoney_count} alarm")
        except Exception as e:
            import traceback
            log(f"!!! BigMoney error: {e}")
            log(f"Traceback: {traceback.format_exc()}")
            alarm_counts['BigMoney'] = 0
        
        log("2/7 Sharp hesaplaniyor...")
        try:
            sharp_count = self.calculate_sharp_alarms() or 0
            alarm_counts['Sharp'] = sharp_count
            total_alarms += sharp_count
            log(f"  -> Sharp: {sharp_count} alarm")
        except Exception as e:
            import traceback
            log(f"!!! Sharp error: {e}")
            log(f"Traceback: {traceback.format_exc()}")
            alarm_counts['Sharp'] = 0
        
        log("3/7 Insider hesaplaniyor...")
        try:
            insider_count = self.calculate_insider_alarms() or 0
            alarm_counts['Insider'] = insider_count
            total_alarms += insider_count
            log(f"  -> Insider: {insider_count} alarm")
        except Exception as e:
            import traceback
            log(f"!!! Insider error: {e}")
            log(f"Traceback: {traceback.format_exc()}")
            alarm_counts['Insider'] = 0
        
        log("4/7 VolumeShock hesaplaniyor...")
        try:
            volumeshock_count = self.calculate_volumeshock_alarms() or 0
            alarm_counts['VolumeShock'] = volumeshock_count
            total_alarms += volumeshock_count
            log(f"  -> VolumeShock: {volumeshock_count} alarm")
        except Exception as e:
            import traceback
            log(f"!!! VolumeShock error: {e}")
            log(f"Traceback: {traceback.format_exc()}")
            alarm_counts['VolumeShock'] = 0
        
        log("5/8 Dropping hesaplaniyor...")
        try:
            dropping_count = self.calculate_dropping_alarms() or 0
            alarm_counts['Dropping'] = dropping_count
            total_alarms += dropping_count
            log(f"  -> Dropping: {dropping_count} alarm")
        except Exception as e:
            import traceback
            log(f"!!! Dropping error: {e}")
            log(f"Traceback: {traceback.format_exc()}")
            alarm_counts['Dropping'] = 0
        
        log("6/8 PublicMove hesaplaniyor...")
        try:
            publicmove_count = self.calculate_publicmove_alarms() or 0
            alarm_counts['PublicMove'] = publicmove_count
            total_alarms += publicmove_count
            log(f"  -> PublicMove: {publicmove_count} alarm")
        except Exception as e:
            import traceback
            log(f"!!! PublicMove error: {e}")
            log(f"Traceback: {traceback.format_exc()}")
            alarm_counts['PublicMove'] = 0
        
        log("7/8 VolumeLeader hesaplaniyor...")
        try:
            volumeleader_count = self.calculate_volumeleader_alarms() or 0
            alarm_counts['VolumeLeader'] = volumeleader_count
            total_alarms += volumeleader_count
            log(f"  -> VolumeLeader: {volumeleader_count} alarm")
        except Exception as e:
            import traceback
            log(f"!!! VolumeLeader error: {e}")
            log(f"Traceback: {traceback.format_exc()}")
            alarm_counts['VolumeLeader'] = 0
        
        log("8/8 MIM (Market Impact) hesaplaniyor...")
        try:
            mim_count = self.calculate_mim_alarms() or 0
            alarm_counts['MIM'] = mim_count
            total_alarms += mim_count
            log(f"  -> MIM: {mim_count} alarm")
        except Exception as e:
            import traceback
            log(f"!!! MIM error: {e}")
            log(f"Traceback: {traceback.format_exc()}")
            alarm_counts['MIM'] = 0
        
        log("=" * 50)
        log(f"[ALARM SYNC] HESAPLAMA TAMAMLANDI - TOPLAM: {total_alarms} alarm")
        summary = ", ".join([f"{k}={v}" for k, v in alarm_counts.items()])
        log(f"[ALARM SYNC] Upserted alarm records: {summary}")
        log("=" * 50)
        
        self.last_alarm_count = total_alarms
        self.alarm_summary = alarm_counts
        
        return total_alarms
    
    def _is_valid_match_date(self, date_str: str) -> bool:
        """Check if match is within valid date range (D-1 to D+7)
        D-2 and older matches are excluded from alarm calculations.
        """
        match_date = parse_match_date(date_str)
        if not match_date:
            return True
        
        today = now_turkey().date()
        past_limit = today - timedelta(days=1)  # D-1 dahil, D-2+ hariç
        future_limit = today + timedelta(days=7)
        match_dt = match_date.date()
        return past_limit <= match_dt <= future_limit
    
    def calculate_sharp_alarms(self) -> int:
        """Calculate Sharp Move alarms - UI ALAN ADLARIYLA UYUMLU
        
        UI Formülleri:
        1. Hacim Şoku:
           - amount_change = curr_amt - prev_amt
           - avg_last_amounts = son 5 snapshot'ın ortalaması
           - shock_raw = amount_change / avg_last_amounts
           - shock_value = shock_raw × volume_multiplier
           - volume_contrib = min(shock_value, max_volume_cap)
        
        2. Oran Düşüşü:
           - drop_pct = ((prev_odds - curr_odds) / prev_odds) × 100
           - odds_value = drop_pct × odds_multiplier
           - odds_contrib = min(odds_value, max_odds_cap)
        
        3. Pay Değişimi:
           - share_diff = curr_share - prev_share
           - share_value = share_diff × share_multiplier
           - share_contrib = min(share_value, max_share_cap)
        
        4. Final Skor:
           - sharp_score = volume_contrib + odds_contrib + share_contrib
        """
        # NOT: Sharp alarmları silinmez - sadece upsert yapılır
        # Tablo temizleme KALDIRILDI - alarmlar kalıcı olmalı
        
        config = self.configs.get('sharp')
        if not config:
            log("[Sharp] CONFIG YOK - Supabase'de sharp ayarlarını kaydedin!")
            return 0
        
        required_keys = ['min_sharp_score', 'min_volume_1x2', 'min_volume_ou25', 'min_volume_btts']
        missing_keys = [k for k in required_keys if config.get(k) is None]
        if missing_keys:
            log(f"[Sharp] CONFIG EKSIK KEY'LER: {missing_keys} - Supabase'de tamamlayın!")
            return 0
        
        min_score = parse_float(config.get('min_sharp_score'))
        min_amount_change = parse_float(config.get('min_amount_change')) or 0
        
        # Multipliers
        volume_multiplier = parse_float(config.get('volume_multiplier')) or 1.0
        odds_multiplier_default = parse_float(config.get('odds_multiplier')) or 1.0
        share_multiplier = parse_float(config.get('share_multiplier')) or 1.0
        
        # Cap değerleri - UI'dan gelen
        max_volume_cap = parse_float(config.get('max_volume_cap')) or 40.0
        max_odds_cap = parse_float(config.get('max_odds_cap')) or 10.0
        max_share_cap = parse_float(config.get('max_share_cap')) or 10.0
        
        # Odds Range Multipliers + Min Drop Eşikleri - oran aralığına göre farklı çarpanlar ve eşikler
        odds_ranges = []
        for i in range(1, 5):
            range_min = parse_float(config.get(f'odds_range_{i}_min')) or 0
            range_max = parse_float(config.get(f'odds_range_{i}_max')) or 99
            range_mult = parse_float(config.get(f'odds_range_{i}_mult')) or odds_multiplier_default
            range_drop = parse_float(config.get(f'odds_range_{i}_drop')) or 0  # Min drop eşiği
            if range_min > 0 or range_max < 99:
                odds_ranges.append({'min': range_min, 'max': range_max, 'mult': range_mult, 'drop': range_drop})
        
        log(f"[Sharp Config] UI ALAN ADLARIYLA HESAPLAMA:")
        log(f"  - min_sharp_score: {min_score}")
        log(f"  - min_amount_change: {min_amount_change}")
        log(f"  - volume_multiplier: {volume_multiplier}, max_volume_cap: {max_volume_cap}")
        log(f"  - odds_multiplier: {odds_multiplier_default}, max_odds_cap: {max_odds_cap}")
        log(f"  - share_multiplier: {share_multiplier}, max_share_cap: {max_share_cap}")
        if odds_ranges:
            log(f"  - Odds ranges: {len(odds_ranges)} defined")
        
        alarms = []
        markets = ['moneyway_1x2', 'moneyway_ou25', 'moneyway_btts']
        market_names = {'moneyway_1x2': '1X2', 'moneyway_ou25': 'O/U 2.5', 'moneyway_btts': 'BTTS'}
        
        for market in markets:
            if '1x2' in market:
                min_volume = parse_float(config.get('min_volume_1x2'))
                selections = ['1', 'X', '2']
                odds_keys = ['odds1', 'oddsx', 'odds2']
                amount_keys = ['amt1', 'amtx', 'amt2']
                pct_keys = ['pct1', 'pctx', 'pct2']
            elif 'ou25' in market:
                min_volume = parse_float(config.get('min_volume_ou25'))
                selections = ['Over', 'Under']
                odds_keys = ['over', 'under']
                amount_keys = ['amtover', 'amtunder']
                pct_keys = ['pctover', 'pctunder']
            else:
                min_volume = parse_float(config.get('min_volume_btts'))
                selections = ['Yes', 'No']
                odds_keys = ['oddsyes', 'oddsno']
                amount_keys = ['amtyes', 'amtno']
                pct_keys = ['pctyes', 'pctno']
            
            history_table = f"{market}_history"
            matches = self.get_matches_with_latest(market)
            
            for match in matches:
                if not self._is_valid_match_date(match.get('date', '')):
                    continue
                
                home = match.get('home', match.get('Home', ''))
                away = match.get('away', match.get('Away', ''))
                if not home or not away:
                    continue
                
                total_volume = parse_volume(match.get('volume', '0'))
                if total_volume < min_volume:
                    continue
                
                history = self.get_match_history(home, away, history_table)
                if len(history) < 2:
                    continue
                
                latest = history[-1]
                prev = history[-2]
                
                for sel_idx, selection in enumerate(selections):
                    odds_key = odds_keys[sel_idx]
                    amount_key = amount_keys[sel_idx]
                    pct_key = pct_keys[sel_idx]
                    
                    current_odds = parse_float(latest.get(odds_key, 0))
                    prev_odds = parse_float(prev.get(odds_key, 0))
                    
                    current_amount = parse_volume(latest.get(amount_key, 0))
                    prev_amount = parse_volume(prev.get(amount_key, 0))
                    
                    current_share = parse_float(latest.get(pct_key, 0))
                    previous_share = parse_float(prev.get(pct_key, 0))
                    
                    if current_odds <= 0 or prev_odds <= 0:
                        continue
                    
                    # === UI FORMÜLÜ: amount_change ===
                    amount_change = current_amount - prev_amount
                    if amount_change <= 0:
                        continue
                    
                    if amount_change < min_amount_change:
                        continue
                    
                    # === UI FORMÜLÜ: avg_last_amounts (son 5 snapshot ortalaması) ===
                    # PRIOR LOGIC: Deterministik fallback ile gerçek volume change korunur
                    last_5_amounts = []
                    for i in range(max(0, len(history) - 6), len(history) - 1):
                        amt = parse_volume(history[i].get(amount_key, 0))
                        last_5_amounts.append(amt)
                    
                    # UI Mantığı: Non-zero ortalaması, yoksa prev_amount, yoksa 1000 fallback
                    non_zero_amounts = [a for a in last_5_amounts if a > 0]
                    if len(non_zero_amounts) > 0:
                        avg_last_amounts = sum(non_zero_amounts) / len(non_zero_amounts)
                    elif prev_amount > 0:
                        avg_last_amounts = prev_amount
                    else:
                        # Deterministik fallback: 1000 (eski davranış korunur, shock_raw anlamlı kalır)
                        avg_last_amounts = 1000.0
                    
                    # === UI FORMÜLÜ: shock_raw = amount_change / avg_last_amounts ===
                    # Gerçek volume change korunur, sıfıra bölme koruması var
                    shock_raw = amount_change / avg_last_amounts
                    
                    # === UI FORMÜLÜ: shock_value = shock_raw × volume_multiplier ===
                    shock_value = shock_raw * volume_multiplier
                    
                    # === UI FORMÜLÜ: volume_contrib = min(shock_value, max_volume_cap) ===
                    volume_contrib = min(shock_value, max_volume_cap)
                    
                    # === UI FORMÜLÜ: drop_pct = ((prev_odds - curr_odds) / prev_odds) × 100 ===
                    if prev_odds > 0:
                        drop_pct = ((prev_odds - current_odds) / prev_odds) * 100
                    else:
                        drop_pct = 0
                    
                    if drop_pct <= 0:
                        continue
                    
                    # Odds range'e göre bucket multiplier ve min drop eşiği seç
                    odds_bucket_multiplier = odds_multiplier_default
                    min_drop_threshold = 0  # Varsayılan: eşik yok
                    for odr in odds_ranges:
                        if odr['min'] <= current_odds <= odr['max']:
                            odds_bucket_multiplier = odr['mult']
                            min_drop_threshold = odr.get('drop', 0)
                            break
                    
                    # Min drop eşiği kontrolü - drop_pct bu eşiğin altındaysa alarm tetiklenmez
                    if min_drop_threshold > 0 and drop_pct < min_drop_threshold:
                        continue
                    
                    # === UI FORMÜLÜ: odds_value = drop_pct × odds_multiplier ===
                    # Bucket multiplier aktif ise onu kullan, değilse base multiplier
                    odds_multiplier_used = odds_bucket_multiplier
                    odds_value = drop_pct * odds_multiplier_used
                    
                    # === UI FORMÜLÜ: odds_contrib = min(odds_value, max_odds_cap) ===
                    odds_contrib = min(odds_value, max_odds_cap)
                    
                    # === UI FORMÜLÜ: share_diff = curr_share - prev_share ===
                    # UI negatif share_diff'e izin verir ama contrib 0 olur
                    share_diff = current_share - previous_share
                    
                    # === UI FORMÜLÜ: share_value = share_diff × share_multiplier ===
                    # Negatif share_diff için share_value de negatif olabilir (UI gösterim için)
                    share_value = share_diff * share_multiplier
                    
                    # === UI FORMÜLÜ: share_contrib = min(share_value, max_share_cap) ===
                    # Negatif veya sıfır share_value için contrib 0
                    share_contrib = min(max(0, share_value), max_share_cap)
                    
                    # === UI FORMÜLÜ: sharp_score = volume_contrib + odds_contrib + share_contrib ===
                    sharp_score = volume_contrib + odds_contrib + share_contrib
                    
                    if sharp_score >= min_score:
                        trigger_at = latest.get('scraped_at', now_turkey_iso())
                        match_id = generate_match_id_hash(home, away, match.get('league', ''), match.get('kickoff', match.get('kickoff_utc', '')))
                        
                        # UI ALAN ADLARIYLA ALARM KAYDI
                        alarm = {
                            'match_id': match_id,
                            'home': home,
                            'away': away,
                            'market': market_names.get(market, market),
                            'selection': selection,
                            'match_date': match.get('date', ''),
                            'trigger_at': trigger_at,
                            'created_at': now_turkey_iso(),
                            'alarm_type': 'sharp',
                            
                            # Hacim Şoku - UI alan adları
                            'amount_change': round(amount_change, 2),
                            'avg_last_amounts': round(avg_last_amounts, 2),
                            'shock_raw': round(shock_raw, 4),
                            'volume_multiplier': volume_multiplier,
                            'shock_value': round(shock_value, 2),
                            'max_volume_cap': max_volume_cap,
                            'volume_contrib': round(volume_contrib, 2),
                            
                            # Oran Düşüşü - UI alan adları
                            # odds_multiplier_base = config'den gelen base, odds_multiplier_bucket = range'e göre uygulanan
                            'previous_odds': round(prev_odds, 2),
                            'current_odds': round(current_odds, 2),
                            'drop_pct': round(drop_pct, 2),
                            'odds_multiplier_base': odds_multiplier_default,
                            'odds_multiplier_bucket': odds_multiplier_used,
                            'odds_multiplier': odds_multiplier_used,  # UI backwards compat
                            'odds_value': round(odds_value, 2),
                            'max_odds_cap': max_odds_cap,
                            'odds_contrib': round(odds_contrib, 2),
                            
                            # Pay Değişimi - UI alan adları
                            # share_value negatif olabilir (UI gösterim için), share_contrib ise 0'dan küçük olamaz
                            'previous_share': round(previous_share, 2),
                            'current_share': round(current_share, 2),
                            'share_diff': round(share_diff, 2),
                            'share_multiplier': share_multiplier,
                            'share_value': round(share_value, 2),  # İşaretli değer saklanır
                            'max_share_cap': max_share_cap,
                            'share_contrib': round(share_contrib, 2),  # Negatifse 0
                            
                            # Final Skor
                            'sharp_score': round(sharp_score, 2)
                        }
                        alarms.append(alarm)
                        log(f"  [SHARP] {home} vs {away} | {market_names.get(market, market)}-{selection} | Score: {sharp_score:.1f} | Vol: £{amount_change:,.0f} | Drop: {drop_pct:.1f}%")
        
        if alarms:
            new_count = self._upsert_alarms('sharp_alarms', alarms, ['home', 'away', 'market', 'selection'])
            log(f"Sharp: {new_count} alarms upserted")
        else:
            log("Sharp: 0 alarm")
        
        return len(alarms)
    
    def calculate_insider_alarms(self) -> int:
        """Calculate Insider Info alarms - GÖRSEL KURALLARINA GÖRE
        
        1. Açılış→Şimdi Düşüş: Oranlar açılıştan >= %X düştü mü?
        2. Düşüş Anını Bul: En büyük tek seferlik ORAN düşüşünün olduğu snapshot
        3. Etraf Snapshotları: Düşüş anının etrafındaki N snapshot'a bak (N = sure_dakika)
        4. Sessiz Hareket: Tüm N snapshot'ta HacimSok < Esik VE GelenPara < MaxPara
        
        RACE CONDITION FIX: Önce upsert, sonra eski alarmları temizle
        """
        
        config = self.configs.get('insider')
        if not config:
            log("[Insider] CONFIG YOK - Supabase'de insider ayarlarını kaydedin!")
            return 0
        
        required_keys = ['hacim_sok_esigi', 'oran_dusus_esigi', 'max_para', 'max_odds_esigi', 'sure_dakika']
        missing_keys = [k for k in required_keys if config.get(k) is None]
        if missing_keys:
            log(f"[Insider] CONFIG EKSIK KEY'LER: {missing_keys} - Supabase'de tamamlayın!")
            return 0
        
        hacim_sok_esigi = parse_float(config.get('hacim_sok_esigi'))
        oran_dusus_esigi = parse_float(config.get('oran_dusus_esigi'))
        max_para = parse_float(config.get('max_para'))
        max_odds = parse_float(config.get('max_odds_esigi'))
        if 'sure_dakika' not in config:
            log(f"[Insider] UYARI: sure_dakika config'de yok! Default 7 kullanılıyor.")
            n_snapshots = 7
        else:
            n_snapshots_raw = parse_float(config.get('sure_dakika'))
            n_snapshots = int(n_snapshots_raw) if n_snapshots_raw > 0 else 7
        
        log(f"[Insider Config] HESAPLAMAYLA KULLANILAN DEĞERLER:")
        log(f"  - hacim_sok_esigi: {hacim_sok_esigi}")
        log(f"  - oran_dusus_esigi: {oran_dusus_esigi}%")
        log(f"  - max_para: {max_para}")
        log(f"  - max_odds_esigi: {max_odds}")
        log(f"  - sure_dakika (N_snapshots): {n_snapshots}")
        
        alarms = []
        markets = ['moneyway_1x2', 'moneyway_ou25', 'moneyway_btts']
        market_names = {'moneyway_1x2': '1X2', 'moneyway_ou25': 'O/U 2.5', 'moneyway_btts': 'BTTS'}
        
        for market in markets:
            if '1x2' in market:
                selections = ['1', 'X', '2']
                odds_keys = ['odds1', 'oddsx', 'odds2']
                amount_keys = ['amt1', 'amtx', 'amt2']
            elif 'ou25' in market:
                selections = ['Over', 'Under']
                odds_keys = ['over', 'under']
                amount_keys = ['amtover', 'amtunder']
            else:
                selections = ['Yes', 'No']
                odds_keys = ['oddsyes', 'oddsno']
                amount_keys = ['amtyes', 'amtno']
            
            history_table = f"{market}_history"
            matches = self.get_matches_with_latest(market)
            
            for match in matches:
                if not self._is_valid_match_date(match.get('date', '')):
                    continue
                
                home = match.get('home', match.get('Home', ''))
                away = match.get('away', match.get('Away', ''))
                if not home or not away:
                    continue
                
                history = self.get_match_history(home, away, history_table)
                if len(history) < 3:
                    continue
                
                first = history[0]
                latest = history[-1]
                
                for sel_idx, selection in enumerate(selections):
                    odds_key = odds_keys[sel_idx]
                    amount_key = amount_keys[sel_idx]
                    
                    opening_odds = parse_float(first.get(odds_key, 0))
                    current_odds = parse_float(latest.get(odds_key, 0))
                    
                    if opening_odds <= 0 or current_odds <= 0:
                        continue
                    
                    # Max odds kontrolü (son oran)
                    if current_odds > max_odds:
                        continue
                    
                    # KURAL 1: Açılış→Şimdi drop kontrolü
                    overall_drop_pct = ((opening_odds - current_odds) / opening_odds) * 100
                    if overall_drop_pct < oran_dusus_esigi:
                        # Açılıştan bugüne yeterli düşüş yok
                        continue
                    
                    # KURAL 2: En büyük tek seferlik ORAN düşüşünün olduğu snapshot'ı bul
                    max_odds_drop = 0
                    drop_moment_index = -1
                    
                    for i in range(1, len(history)):
                        curr_odds = parse_float(history[i].get(odds_key, 0))
                        prev_odds = parse_float(history[i-1].get(odds_key, 0))
                        
                        if prev_odds > 0 and curr_odds > 0 and curr_odds < prev_odds:
                            odds_drop = prev_odds - curr_odds
                            if odds_drop > max_odds_drop:
                                max_odds_drop = odds_drop
                                drop_moment_index = i
                    
                    if drop_moment_index < 0:
                        continue
                    
                    # KURAL 2: Düşüş anının etrafındaki N snapshot'a bak
                    # Tam olarak n_snapshots kadar (history izin veriyorsa)
                    history_len = len(history)
                    
                    # Merkez olarak drop_moment_index kullan
                    half_before = n_snapshots // 2
                    half_after = n_snapshots - half_before - 1
                    
                    start_idx = drop_moment_index - half_before
                    end_idx = drop_moment_index + half_after + 1
                    
                    # Sınırları düzelt - eksik tarafı diğer taraftan telafi et
                    if start_idx < 0:
                        # Baştan taştı, sonu genişlet
                        end_idx = min(history_len, end_idx + (-start_idx))
                        start_idx = 0
                    
                    if end_idx > history_len:
                        # Sondan taştı, başı geri al
                        start_idx = max(0, start_idx - (end_idx - history_len))
                        end_idx = history_len
                    
                    surrounding_snapshots = history[start_idx:end_idx]
                    if len(surrounding_snapshots) < 2:
                        continue
                    
                    # KURAL 4: Tüm N snapshot'ta HacimSok < Esik VE GelenPara < MaxPara
                    all_quiet = True
                    total_incoming = 0
                    max_hacim_sok = 0
                    surrounding_details = []
                    
                    # Tüm snapshot'ları kaydet (N adet)
                    for i, snap in enumerate(surrounding_snapshots):
                        curr_amt = parse_volume(snap.get(amount_key, 0))
                        curr_odds = parse_float(snap.get(odds_key, 0))
                        scraped_at = snap.get('scraped_at', '')
                        
                        # Önceki snapshot varsa incoming hesapla
                        if i > 0:
                            prev_amt = parse_volume(surrounding_snapshots[i-1].get(amount_key, 0))
                            incoming = max(0, curr_amt - prev_amt)
                            total_incoming += incoming
                            
                            # Hacim şoku hesapla: incoming / prev_amt
                            hacim_sok = incoming / prev_amt if prev_amt > 0 else 0
                            if hacim_sok > max_hacim_sok:
                                max_hacim_sok = hacim_sok
                            
                            # HER snapshot'ta: HacimSok < Esik VE GelenPara < MaxPara olmalı
                            if hacim_sok >= hacim_sok_esigi or incoming >= max_para:
                                all_quiet = False
                        else:
                            incoming = 0
                            hacim_sok = 0
                        
                        # Açılışa göre drop hesapla (her snapshot için)
                        snap_drop_pct = ((opening_odds - curr_odds) / opening_odds * 100) if opening_odds > 0 and curr_odds > 0 else 0
                        
                        surrounding_details.append({
                            'index': start_idx + i,
                            'scraped_at': scraped_at,
                            'odds': curr_odds,
                            'drop_pct': round(snap_drop_pct, 2),
                            'amount': curr_amt,
                            'incoming': round(incoming, 0),
                            'volume_shock': round(hacim_sok, 4),
                            'is_drop_moment': (start_idx + i) == drop_moment_index
                        })
                    
                    # Sessiz hareket değilse alarm yok
                    if not all_quiet:
                        continue
                    
                    # KURAL 5 (Recovery kontrolü): GERÇEK SON SNAPSHOT'ta açılışa göre drop hala >= eşik mi?
                    # NOT: surrounding_details değil, history[-1] kullan - çünkü yeni snapshot'lar window dışında kalabilir
                    true_latest = history[-1]
                    true_latest_odds = parse_float(true_latest.get(odds_key, 0))
                    
                    # DEBUG: history durumunu logla
                    log(f"  [DEBUG INSIDER] {home} vs {away} | {selection} | history_len={len(history)} | drop_idx={drop_moment_index} | window=[{start_idx}:{end_idx}] | history[-1]_odds={true_latest_odds:.2f} | scraped_at={true_latest.get('scraped_at', 'N/A')[:19]}")
                    
                    if true_latest_odds <= 0:
                        continue
                    
                    # Açılışa göre GERÇEK son snapshot'taki drop
                    true_latest_drop_pct = ((opening_odds - true_latest_odds) / opening_odds) * 100
                    
                    # Oran düzeldiyse (drop < eşik) alarm iptal
                    if true_latest_drop_pct < oran_dusus_esigi:
                        # Oran düzelmiş, alarm tetiklenmez - stale cleanup silecek
                        log(f"  [INSIDER RECOVERY] {home} vs {away} | {selection} | Oran düzeldi: {true_latest_odds:.2f} (drop %{true_latest_drop_pct:.1f} < eşik %{oran_dusus_esigi})")
                        continue
                    
                    # Güncel değerler - gerçek son snapshot'tan
                    actual_current_odds = true_latest_odds
                    actual_drop_pct = true_latest_drop_pct
                    
                    trigger_snap = history[drop_moment_index]
                    trigger_at = trigger_snap.get('scraped_at', now_turkey_iso())
                    match_id = generate_match_id_hash(home, away, match.get('league', ''), match.get('kickoff', match.get('kickoff_utc', '')))
                    
                    alarm = {
                        'match_id': match_id,
                        'home': home,
                        'away': away,
                        'market': market_names.get(market, market),
                        'selection': selection,
                        'odds_drop_pct': round(actual_drop_pct, 2),
                        'max_odds_drop': round(max_odds_drop, 3),
                        'incoming_money': total_incoming,
                        'volume_shock': round(max_hacim_sok, 4),
                        'opening_odds': opening_odds,
                        'current_odds': actual_current_odds,
                        'drop_moment_index': drop_moment_index,
                        'drop_moment': trigger_at,
                        'surrounding_snapshots': surrounding_details,
                        'snapshot_count': len(surrounding_snapshots),
                        'match_date': match.get('date', ''),
                        'trigger_at': trigger_at,
                        'created_at': now_turkey_iso(),
                        'alarm_type': 'insider'
                    }
                    alarms.append(alarm)
                    log(f"  [INSIDER] {home} vs {away} | {market_names.get(market, market)}-{selection} | Açılış: {opening_odds:.2f}->Şimdi: {actual_current_odds:.2f} (-%{actual_drop_pct:.1f}) | DüsusAnı: S{drop_moment_index} | Para: {total_incoming:,.0f}")
        
        if alarms:
            new_count = self._upsert_alarms('insider_alarms', alarms, ['home', 'away', 'market', 'selection'])
            log(f"Insider: {new_count} alarms upserted")
            
            # RACE CONDITION FIX: Upsert'ten SONRA geçersiz alarmları temizle
            valid_keys = set()
            for a in alarms:
                key = f"{a['home']}|{a['away']}|{a['market']}|{a['selection']}"
                valid_keys.add(key)
            
            try:
                existing = self._get('insider_alarms', 'select=id,home,away,market,selection') or []
                stale_ids = []
                for row in existing:
                    key = f"{row.get('home', '')}|{row.get('away', '')}|{row.get('market', '')}|{row.get('selection', '')}"
                    if key not in valid_keys:
                        stale_ids.append(row.get('id'))
                
                if stale_ids:
                    for stale_id in stale_ids:
                        self._delete('insider_alarms', f'id=eq.{stale_id}')
                    log(f"[Insider] Removed {len(stale_ids)} stale alarms")
            except Exception as e:
                log(f"[Insider] Stale alarm cleanup failed: {e}")
        else:
            # Hiç alarm yoksa tabloyu temizle
            try:
                self._delete('insider_alarms', 'id=gte.1')
                log("Insider: 0 alarm - table cleared")
            except Exception as e:
                log(f"[Insider] Table clear failed: {e}")
        
        return len(alarms)
    
    def calculate_bigmoney_alarms(self) -> int:
        """Calculate Big Money / Huge Money alarms"""
        # RACE CONDITION FIX: Silme YOK - önce mevcut alarmları oku, sonra geçmişe ekle
        existing_alarms = {}
        try:
            existing = self._get('bigmoney_alarms', 'select=*') or []
            for row in existing:
                key = f"{row.get('home', '')}|{row.get('away', '')}|{row.get('market', '')}|{row.get('selection', '')}"
                existing_alarms[key] = row
            log(f"[BigMoney] {len(existing_alarms)} existing alarms loaded for history tracking")
        except Exception as e:
            log(f"[BigMoney] Existing alarms load failed: {e}")
        
        config = self.configs.get('bigmoney')
        if not config:
            log("[BigMoney] CONFIG YOK - Supabase'de bigmoney ayarlarını kaydedin!")
            return 0
        
        # Config validation - big_money_limit zorunlu
        if config.get('big_money_limit') is None:
            log("[BigMoney] CONFIG EKSIK: big_money_limit key'i yok!")
            return 0
        
        # CRITICAL: parse_float ile float'a çevir - FALLBACK OLMADAN
        limit = parse_float(config.get('big_money_limit'))
        if limit <= 0:
            log("[BigMoney] CONFIG HATALI: big_money_limit 0 veya negatif!")
            return 0
        log(f"[BigMoney Config] limit: {limit}")
        
        alarms = []
        markets = ['moneyway_1x2', 'moneyway_ou25', 'moneyway_btts']
        market_names = {'moneyway_1x2': '1X2', 'moneyway_ou25': 'O/U 2.5', 'moneyway_btts': 'BTTS'}
        
        for market in markets:
            if '1x2' in market:
                selections = ['1', 'X', '2']
                amount_keys = ['amt1', 'amtx', 'amt2']
            elif 'ou25' in market:
                selections = ['Over', 'Under']
                amount_keys = ['amtover', 'amtunder']
            else:
                selections = ['Yes', 'No']
                amount_keys = ['amtyes', 'amtno']
            
            history_table = f"{market}_history"
            matches = self.get_matches_with_latest(market)
            
            for match in matches:
                if not self._is_valid_match_date(match.get('date', '')):
                    continue
                
                home = match.get('home', match.get('Home', ''))
                away = match.get('away', match.get('Away', ''))
                if not home or not away:
                    continue
                
                history = self.get_match_history(home, away, history_table)
                if len(history) < 2:
                    continue
                
                for sel_idx, selection in enumerate(selections):
                    amount_key = amount_keys[sel_idx]
                    
                    big_snapshots = []
                    
                    for i in range(1, len(history)):
                        curr_amt = parse_volume(history[i].get(amount_key, 0))
                        prev_amt = parse_volume(history[i-1].get(amount_key, 0))
                        incoming = curr_amt - prev_amt
                        
                        if incoming >= limit:
                            big_snapshots.append({
                                'index': i,
                                'incoming': incoming,
                                'scraped_at': history[i].get('scraped_at', '')
                            })
                    
                    if not big_snapshots:
                        continue
                    
                    selection_total = parse_volume(history[-1].get(amount_key, 0))
                    match_id = generate_match_id_hash(home, away, match.get('league', ''), match.get('kickoff', match.get('kickoff_utc', '')))
                    
                    # Her büyük para hareketini AYRI alarm olarak kaydet
                    for snap_idx, snap in enumerate(big_snapshots):
                        # Ardışık snapshot'lar HUGE MONEY
                        is_huge = False
                        huge_total = 0
                        if snap_idx < len(big_snapshots) - 1:
                            next_snap = big_snapshots[snap_idx + 1]
                            if next_snap['index'] - snap['index'] == 1:
                                is_huge = True
                                huge_total = snap['incoming'] + next_snap['incoming']
                        
                        trigger_at = snap.get('scraped_at', now_turkey_iso())
                        
                        alarm = {
                            'match_id': match_id,
                            'home': home,
                            'away': away,
                            'market': market_names.get(market, market),
                            'selection': selection,
                            'incoming_money': snap['incoming'],
                            'selection_total': selection_total,
                            'is_huge': is_huge,
                            'huge_total': huge_total,
                            'alarm_type': 'HUGE MONEY' if is_huge else 'BIG MONEY',
                            'match_date': match.get('date', ''),
                            'trigger_at': trigger_at,
                            'created_at': now_turkey_iso()
                        }
                        alarms.append(alarm)
                        alarm_label = 'HUGE' if is_huge else 'BIG'
                        log(f"  [{alarm_label} MONEY] {home} vs {away} | {market_names.get(market, market)}-{selection} | £{snap['incoming']:,.0f} gelen")
        
        if alarms:
            import json
            
            # Aynı key için tüm alarmları grupla - EN SON olanı ana, diğerleri history
            grouped_alarms = {}
            for alarm in alarms:
                key = (alarm['match_id'], alarm['market'], alarm['selection'])
                if key not in grouped_alarms:
                    grouped_alarms[key] = []
                grouped_alarms[key].append(alarm)
            
            filtered_alarms = []
            for key, alarm_list in grouped_alarms.items():
                # Zamana göre sırala (en son = ana alarm)
                alarm_list.sort(key=lambda x: x.get('trigger_at', ''), reverse=True)
                
                main_alarm = alarm_list[0]  # En son olan
                
                # Diğerleri history olarak ekle
                current_history = []
                for old in alarm_list[1:]:
                    current_history.append({
                        'incoming_money': old.get('incoming_money', 0),
                        'trigger_at': old.get('trigger_at', ''),
                        'selection_total': old.get('selection_total', 0),
                        'is_huge': old.get('is_huge', False)
                    })
                
                # Mevcut DB'deki history'yi de ekle
                str_key = f"{main_alarm['home']}|{main_alarm['away']}|{main_alarm['market']}|{main_alarm['selection']}"
                if str_key in existing_alarms:
                    old_alarm = existing_alarms[str_key]
                    db_history = old_alarm.get('alarm_history') or []
                    if isinstance(db_history, str):
                        try:
                            db_history = json.loads(db_history)
                        except:
                            db_history = []
                    
                    # DB'deki mevcut ana alarmı da history'ye ekle (eğer farklıysa)
                    old_trigger = old_alarm.get('trigger_at', '')
                    old_incoming = old_alarm.get('incoming_money', 0)
                    main_trigger = main_alarm.get('trigger_at', '')
                    
                    if old_trigger and old_trigger != main_trigger and old_incoming > 0:
                        db_history.append({
                            'incoming_money': old_incoming,
                            'trigger_at': old_trigger,
                            'selection_total': old_alarm.get('selection_total', 0),
                            'is_huge': old_alarm.get('is_huge', False)
                        })
                    
                    current_history.extend(db_history)
                
                # Tekrarları kaldır ve sırala (eski -> yeni)
                seen_triggers = set()
                unique_history = []
                for h in current_history:
                    t = h.get('trigger_at', '')
                    if t and t not in seen_triggers:
                        seen_triggers.add(t)
                        unique_history.append(h)
                
                unique_history.sort(key=lambda x: x.get('trigger_at', ''))
                unique_history = unique_history[-10:]  # Son 10 kayıt
                
                main_alarm['alarm_history'] = json.dumps(unique_history)
                filtered_alarms.append(main_alarm)
            
            log(f"BigMoney: {len(alarms)} -> {len(filtered_alarms)} (grouped with history)")
            
            # Constraint: match_id, market, selection - Supabase unique constraint ile uyumlu
            new_count = self._upsert_alarms('bigmoney_alarms', filtered_alarms, ['match_id', 'market', 'selection'])
            log(f"BigMoney: {new_count} alarms upserted (with history)")
            
            # NOT: BigMoney alarmları silinmez - sadece upsert yapılır
            # Stale cleanup KALDIRILDI - alarmlar kalıcı olmalı
        
        return len(alarms)
    
    def calculate_volumeshock_alarms(self) -> int:
        """Calculate Volume Shock alarms"""
        # NOT: VolumeShock alarmları silinmez - sadece upsert yapılır
        # Tablo temizleme KALDIRILDI - alarmlar kalıcı olmalı
        
        config = self.configs.get('volumeshock')
        if not config:
            log("[VolumeShock] CONFIG YOK - Supabase'de volumeshock ayarlarını kaydedin!")
            return 0
        
        # Config validation
        required_keys = ['hacim_soku_min_esik', 'hacim_soku_min_saat', 'min_son_snapshot_para']
        missing_keys = [k for k in required_keys if config.get(k) is None]
        if missing_keys:
            log(f"[VolumeShock] CONFIG EKSIK KEY'LER: {missing_keys} - Supabase'de tamamlayın!")
            return 0
        
        # CRITICAL: parse_float - FALLBACK OLMADAN
        shock_mult = parse_float(config.get('hacim_soku_min_esik'))
        min_hours = parse_float(config.get('hacim_soku_min_saat'))
        min_incoming = parse_float(config.get('min_son_snapshot_para'))
        log(f"[VolumeShock Config] shock_mult: {shock_mult}, min_hours: {min_hours}, min_incoming: {min_incoming}")
        
        alarms = []
        markets = ['moneyway_1x2', 'moneyway_ou25', 'moneyway_btts']
        market_names = {'moneyway_1x2': '1X2', 'moneyway_ou25': 'O/U 2.5', 'moneyway_btts': 'BTTS'}
        
        for market in markets:
            if '1x2' in market:
                selections = ['1', 'X', '2']
                amount_keys = ['amt1', 'amtx', 'amt2']
            elif 'ou25' in market:
                selections = ['Over', 'Under']
                amount_keys = ['amtover', 'amtunder']
            else:
                selections = ['Yes', 'No']
                amount_keys = ['amtyes', 'amtno']
            
            history_table = f"{market}_history"
            matches = self.get_matches_with_latest(market)
            
            for match in matches:
                if not self._is_valid_match_date(match.get('date', '')):
                    continue
                
                home = match.get('home', match.get('Home', ''))
                away = match.get('away', match.get('Away', ''))
                if not home or not away:
                    continue
                
                history = self.get_match_history(home, away, history_table)
                if len(history) < 5:
                    continue
                
                for sel_idx, selection in enumerate(selections):
                    amount_key = amount_keys[sel_idx]
                    
                    # Tüm history'yi tara - en yüksek şoku bul
                    best_shock = None
                    best_shock_value = 0
                    
                    for i in range(5, len(history)):
                        curr_amt = parse_volume(history[i].get(amount_key, 0))
                        prev_amt = parse_volume(history[i-1].get(amount_key, 0))
                        incoming = curr_amt - prev_amt
                        
                        if incoming <= 0:
                            continue
                        
                        # min_son_snapshot_para filtresi
                        if incoming < min_incoming:
                            continue
                        
                        # Önceki 4 snapshot'ın ortalaması
                        prev_amts = []
                        for j in range(max(1, i-4), i):
                            diff = parse_volume(history[j].get(amount_key, 0)) - parse_volume(history[j-1].get(amount_key, 0))
                            if diff > 0:
                                prev_amts.append(diff)
                        
                        if not prev_amts:
                            continue
                        
                        avg_prev = sum(prev_amts) / len(prev_amts)
                        shock_value = incoming / avg_prev if avg_prev > 0 else 0
                        
                        if shock_value >= shock_mult and shock_value > best_shock_value:
                            best_shock_value = shock_value
                            best_shock = {
                                'shock_value': shock_value,
                                'incoming': incoming,
                                'avg_prev': avg_prev,
                                'trigger_at': history[i].get('scraped_at', now_turkey_iso()),
                                'snapshot_idx': i
                            }
                    
                    if best_shock:
                        match_id = generate_match_id_hash(home, away, match.get('league', ''), match.get('kickoff', match.get('kickoff_utc', '')))
                        
                        alarm = {
                            'match_id': match_id,
                            'home': home,
                            'away': away,
                            'market': market_names.get(market, market),
                            'selection': selection,
                            'volume_shock_value': round(best_shock['shock_value'], 2),
                            'incoming_money': best_shock['incoming'],
                            'avg_previous': round(best_shock['avg_prev'], 0),
                            'match_date': match.get('date', ''),
                            'trigger_at': best_shock['trigger_at'],
                            'created_at': now_turkey_iso(),
                            'alarm_type': 'volumeshock'
                        }
                        alarms.append(alarm)
                        log(f"  [VOLUMESHOCK] {home} vs {away} | {market_names.get(market, market)}-{selection} | Shock: {best_shock['shock_value']:.1f}x | £{best_shock['incoming']:,.0f} gelen (snap #{best_shock['snapshot_idx']})")
        
        if alarms:
            new_count = self._upsert_alarms('volumeshock_alarms', alarms, ['home', 'away', 'market', 'selection'])
            log(f"VolumeShock: {new_count} alarms upserted")
        else:
            log("VolumeShock: 0 alarm")
        
        return len(alarms)
    
    def calculate_dropping_alarms(self) -> int:
        """Calculate Dropping Odds alarms
        
        KURALLAR:
        1. Opening odds = History'deki ilk snapshot'ın oranı
        2. Current odds = History'deki son snapshot'ın oranı
        3. 120 dakika kalıcılık = Son 120 dakikadaki TÜM snapshot'larda drop devam etmeli
        
        RACE CONDITION FIX: Önce upsert, sonra eski alarmları temizle
        """
        
        config = self.configs.get('dropping')
        if not config:
            log("[Dropping] CONFIG YOK - Supabase'de dropping ayarlarını kaydedin!")
            return 0
        
        # Config validation
        required_keys = ['min_drop_l1', 'max_drop_l1', 'min_drop_l2', 'max_drop_l2', 'min_drop_l3']
        missing_keys = [k for k in required_keys if config.get(k) is None]
        if missing_keys:
            log(f"[Dropping] CONFIG EKSIK KEY'LER: {missing_keys} - Supabase'de tamamlayın!")
            return 0
        
        # CRITICAL: parse_float - FALLBACK OLMADAN
        l1_min = parse_float(config.get('min_drop_l1'))
        l1_max = parse_float(config.get('max_drop_l1'))
        l2_min = parse_float(config.get('min_drop_l2'))
        l2_max = parse_float(config.get('max_drop_l2'))
        l3_min = parse_float(config.get('min_drop_l3'))
        
        # Kalıcılık süresi (dakika) - varsayılan 120 dk
        persistence_enabled = config.get('persistence_enabled', True)
        persistence_minutes = parse_float(config.get('persistence_minutes')) or 120
        
        # Max odds eşikleri - açılış oranı bu değerin üzerindeyse alarm tetiklenmez
        max_odds_1x2 = parse_float(config.get('max_odds_1x2')) or 999
        max_odds_ou25 = parse_float(config.get('max_odds_ou25')) or 999
        max_odds_btts = parse_float(config.get('max_odds_btts')) or 999
        
        log(f"[Dropping Config] L1: {l1_min}-{l1_max}%, L2: {l2_min}-{l2_max}%, L3: {l3_min}%+, Kalıcılık: {'AÇIK' if persistence_enabled else 'KAPALI'} ({persistence_minutes} dk)")
        log(f"[Dropping Config] Max Odds: 1X2={max_odds_1x2}, O/U2.5={max_odds_ou25}, BTTS={max_odds_btts}")
        
        alarms = []
        markets = ['dropping_1x2', 'dropping_ou25', 'dropping_btts']
        market_names = {'dropping_1x2': '1X2', 'dropping_ou25': 'O/U 2.5', 'dropping_btts': 'BTTS'}
        
        for market in markets:
            if '1x2' in market:
                selections = ['1', 'X', '2']
                odds_keys = ['odds1', 'oddsx', 'odds2']
                market_max_odds = max_odds_1x2
            elif 'ou25' in market:
                selections = ['Over', 'Under']
                odds_keys = ['over', 'under']
                market_max_odds = max_odds_ou25
            else:
                selections = ['Yes', 'No']
                odds_keys = ['oddsyes', 'oddsno']
                market_max_odds = max_odds_btts
            
            # History verilerini al
            history_table = f"{market}_history"
            self.batch_fetch_history(market)
            history_map = self._history_cache.get(history_table, {})
            
            matches = self.get_matches_with_latest(market)
            
            for match in matches:
                if not self._is_valid_match_date(match.get('date', '')):
                    continue
                
                home = match.get('home', match.get('Home', ''))
                away = match.get('away', match.get('Away', ''))
                if not home or not away:
                    continue
                
                # History'den maç verilerini al
                key = f"{normalize_team_name(home)}|{normalize_team_name(away)}"
                history_raw = history_map.get(key, [])
                
                if len(history_raw) < 2:
                    continue
                
                # History'i scraped_at'e göre sırala (kronolojik doğruluk için)
                def parse_timestamp(s):
                    try:
                        # Tüm timestamp'leri naive'e çevir (karşılaştırma için)
                        dt = datetime.fromisoformat(s.replace('Z', '+00:00'))
                        if dt.tzinfo:
                            dt = dt.replace(tzinfo=None)
                        return dt
                    except:
                        return datetime.min
                
                history = sorted(history_raw, key=lambda x: parse_timestamp(x.get('scraped_at', '')))
                
                for sel_idx, selection in enumerate(selections):
                    odds_key = odds_keys[sel_idx]
                    
                    # İlk snapshot = Opening odds
                    opening_odds = parse_float(history[0].get(odds_key, 0))
                    # Son snapshot = Current odds
                    current_odds = parse_float(history[-1].get(odds_key, 0))
                    
                    if current_odds <= 0 or opening_odds <= 0:
                        continue
                    
                    # Max odds filtresi - açılış oranı eşiğin üzerindeyse alarm tetiklenmez
                    if opening_odds > market_max_odds:
                        continue
                    
                    if current_odds >= opening_odds:
                        continue
                    
                    drop_pct = ((opening_odds - current_odds) / opening_odds) * 100
                    
                    if drop_pct < l1_min:
                        continue
                    
                    # === KALICILIK KONTROLÜ (persistence_enabled ise) ===
                    recent_snapshots = []
                    if persistence_enabled:
                        # Son snapshot'ın zamanından geriye X dakika içindeki TÜM snapshot'larda drop devam etmeli
                        
                        # Son snapshot'ın zamanını al (referans nokta) - naive datetime kullan
                        latest_scraped_at = parse_timestamp(history[-1].get('scraped_at', ''))
                        if latest_scraped_at == datetime.min:
                            latest_scraped_at = datetime.now()
                        
                        persistence_threshold = latest_scraped_at - timedelta(minutes=persistence_minutes)
                        
                        # Kalıcılık penceresi içindeki snapshot'ları filtrele
                        for snap in history:
                            snap_time = parse_timestamp(snap.get('scraped_at', ''))
                            if snap_time != datetime.min and snap_time >= persistence_threshold:
                                recent_snapshots.append(snap)
                        
                        # En az 2 snapshot olmalı kalıcılık kontrolü için
                        if len(recent_snapshots) < 2:
                            # Yeterli snapshot yok, alarm tetiklenmez
                            continue
                        
                        # Pencere içindeki TÜM snapshot'larda:
                        # 1. Oran opening_odds'un altında kalmalı (geri dönüş yok)
                        # 2. Her snapshot'ta minimum L1 drop_pct eşiği karşılanmalı
                        drop_persistent = True
                        for snap in recent_snapshots:
                            snap_odds = parse_float(snap.get(odds_key, 0))
                            if snap_odds <= 0:
                                continue
                            # Oran opening'e geri dönmüşse veya üstüne çıktıysa, kalıcı drop değil
                            if snap_odds >= opening_odds:
                                drop_persistent = False
                                break
                            # Her snapshot'ta minimum drop_pct (L1) karşılanmalı
                            snap_drop_pct = ((opening_odds - snap_odds) / opening_odds) * 100
                            if snap_drop_pct < l1_min:
                                drop_persistent = False
                                break
                        
                        if not drop_persistent:
                            continue
                    
                    # Level belirleme
                    if drop_pct >= l3_min:
                        level = 'L3'
                    elif drop_pct >= l2_min:
                        level = 'L2'
                    else:
                        level = 'L1'
                    
                    trigger_at = history[-1].get('scraped_at', now_turkey_iso())
                    match_id = generate_match_id_hash(home, away, match.get('league', ''), match.get('kickoff', match.get('kickoff_utc', '')))
                    
                    # Volume bilgisi (varsa)
                    volume = parse_float(match.get('volume', 0))
                    
                    alarm = {
                        'match_id': match_id,
                        'home': home,
                        'away': away,
                        'market': market_names.get(market, market),
                        'selection': selection,
                        'opening_odds': round(opening_odds, 2),
                        'current_odds': round(current_odds, 2),
                        'drop_pct': round(drop_pct, 2),
                        'level': level,
                        'volume': volume,
                        'match_date': match.get('date', ''),
                        'trigger_at': trigger_at,
                        'created_at': now_turkey_iso(),
                        'alarm_type': 'dropping',
                        'persistence_minutes': int(persistence_minutes),
                        'snapshots_checked': int(len(recent_snapshots))
                    }
                    alarms.append(alarm)
                    log(f"  [DROPPING-{level}] {home} vs {away} | {market_names.get(market, market)}-{selection} | {opening_odds:.2f}->{current_odds:.2f} (-%{drop_pct:.1f}) | Kalıcı: {len(recent_snapshots)} snap")
        
        if alarms:
            new_count = self._upsert_alarms('dropping_alarms', alarms, ['home', 'away', 'market', 'selection'])
            log(f"Dropping: {new_count} alarms upserted")
            
            # RACE CONDITION FIX: Upsert'ten SONRA geçersiz alarmları temizle
            # Hesaplanan alarm key'lerini topla
            valid_keys = set()
            for a in alarms:
                key = f"{a['home']}|{a['away']}|{a['market']}|{a['selection']}"
                valid_keys.add(key)
            
            # Mevcut alarmları çek ve geçersiz olanları sil
            try:
                existing = self._get('dropping_alarms', 'select=id,home,away,market,selection') or []
                stale_ids = []
                for row in existing:
                    key = f"{row.get('home', '')}|{row.get('away', '')}|{row.get('market', '')}|{row.get('selection', '')}"
                    if key not in valid_keys:
                        stale_ids.append(row.get('id'))
                
                if stale_ids:
                    for stale_id in stale_ids:
                        self._delete('dropping_alarms', f'id=eq.{stale_id}')
                    log(f"[Dropping] Removed {len(stale_ids)} stale alarms")
            except Exception as e:
                log(f"[Dropping] Stale alarm cleanup failed: {e}")
        else:
            # Hiç alarm yoksa tabloyu temizle (tüm koşullar artık geçersiz)
            try:
                self._delete('dropping_alarms', 'id=gte.1')
                log("Dropping: 0 alarm - table cleared")
            except Exception as e:
                log(f"[Dropping] Table clear failed: {e}")
        
        return len(alarms)
    
    def calculate_publicmove_alarms(self) -> int:
        """Calculate Public Move alarms - same logic as Sharp"""
        # NOT: PublicMove alarmları silinmez - sadece upsert yapılır
        # Tablo temizleme KALDIRILDI - alarmlar kalıcı olmalı
        
        config = self.configs.get('publicmove')
        if not config:
            log("[PublicMove] CONFIG YOK - Supabase'de publicmove ayarlarını kaydedin!")
            return 0
        
        # Config validation
        required_keys = ['min_sharp_score', 'min_volume_1x2', 'min_volume_ou25', 'min_volume_btts']
        missing_keys = [k for k in required_keys if config.get(k) is None]
        if missing_keys:
            log(f"[PublicMove] CONFIG EKSIK KEY'LER: {missing_keys} - Supabase'de tamamlayın!")
            return 0
        
        # CRITICAL: parse_float - FALLBACK OLMADAN
        min_score = parse_float(config.get('min_sharp_score'))
        min_amount_change = parse_float(config.get('min_amount_change')) or 0
        log(f"[PublicMove Config] min_score: {min_score}, min_amount_change: {min_amount_change}")
        
        alarms = []
        markets = ['moneyway_1x2', 'moneyway_ou25', 'moneyway_btts']
        market_names = {'moneyway_1x2': '1X2', 'moneyway_ou25': 'O/U 2.5', 'moneyway_btts': 'BTTS'}
        
        for market in markets:
            if '1x2' in market:
                min_volume = parse_float(config.get('min_volume_1x2'))
                selections = ['1', 'X', '2']
                odds_keys = ['odds1', 'oddsx', 'odds2']
                amount_keys = ['amt1', 'amtx', 'amt2']
                pct_keys = ['pct1', 'pctx', 'pct2']
            elif 'ou25' in market:
                min_volume = parse_float(config.get('min_volume_ou25'))
                selections = ['Over', 'Under']
                odds_keys = ['over', 'under']
                amount_keys = ['amtover', 'amtunder']
                pct_keys = ['pctover', 'pctunder']
            else:
                min_volume = parse_float(config.get('min_volume_btts'))
                selections = ['Yes', 'No']
                odds_keys = ['oddsyes', 'oddsno']
                amount_keys = ['amtyes', 'amtno']
                pct_keys = ['pctyes', 'pctno']
            
            history_table = f"{market}_history"
            matches = self.get_matches_with_latest(market)
            
            for match in matches:
                if not self._is_valid_match_date(match.get('date', '')):
                    continue
                
                home = match.get('home', match.get('Home', ''))
                away = match.get('away', match.get('Away', ''))
                if not home or not away:
                    continue
                
                total_volume = parse_volume(match.get('volume', '0'))
                if total_volume < min_volume:
                    continue
                
                history = self.get_match_history(home, away, history_table)
                if len(history) < 2:
                    continue
                
                # PUBLIC MOVE: Sadece son 2 saatteki hareketlere bak
                now = now_turkey()
                two_hours_ago = now - timedelta(hours=2)
                
                filtered_history = []
                for snap in history:
                    scraped_at = snap.get('scraped_at', snap.get('scrapedat', ''))
                    if scraped_at:
                        try:
                            if 'T' in str(scraped_at):
                                snap_time_str = str(scraped_at).split('+')[0].split('.')[0]
                                snap_time = datetime.strptime(snap_time_str, '%Y-%m-%dT%H:%M:%S')
                            else:
                                snap_time = datetime.strptime(str(scraped_at)[:19], '%Y-%m-%d %H:%M:%S')
                            
                            if snap_time >= two_hours_ago:
                                filtered_history.append(snap)
                        except:
                            filtered_history.append(snap)
                    else:
                        filtered_history.append(snap)
                
                history = filtered_history
                if len(history) < 2:
                    continue
                
                latest = history[-1]
                prev = history[-2]
                
                for sel_idx, selection in enumerate(selections):
                    odds_key = odds_keys[sel_idx]
                    amount_key = amount_keys[sel_idx]
                    pct_key = pct_keys[sel_idx]
                    
                    current_odds = parse_float(latest.get(odds_key, 0))
                    prev_odds = parse_float(prev.get(odds_key, 0))
                    
                    current_amount = parse_volume(latest.get(amount_key, 0))
                    prev_amount = parse_volume(prev.get(amount_key, 0))
                    
                    current_pct = parse_float(latest.get(pct_key, 0))
                    prev_pct = parse_float(prev.get(pct_key, 0))
                    
                    if current_odds <= 0 or prev_odds <= 0:
                        continue
                    
                    volume_change = current_amount - prev_amount
                    if volume_change <= 0:
                        continue
                    
                    # min_amount_change filtresi
                    if volume_change < min_amount_change:
                        continue
                    
                    odds_drop = prev_odds - current_odds
                    if odds_drop <= 0:
                        continue
                    
                    share_change = current_pct - prev_pct
                    
                    move_score = (volume_change / 500) + (odds_drop / 0.05) * 3 + share_change
                    
                    if move_score >= min_score:
                        trigger_at = latest.get('scraped_at', now_turkey_iso())
                        match_id = generate_match_id_hash(home, away, match.get('league', ''), match.get('kickoff', match.get('kickoff_utc', '')))
                        
                        alarm = {
                            'match_id': match_id,
                            'home': home,
                            'away': away,
                            'market': market_names.get(market, market),
                            'selection': selection,
                            'trap_score': round(move_score, 2),
                            'incoming_money': volume_change,
                            'odds_drop_pct': round((odds_drop / prev_odds * 100) if prev_odds > 0 else 0, 2),
                            'previous_share': round(prev_pct, 2),
                            'current_share': round(current_pct, 2),
                            'share_change': round(share_change, 2),
                            'match_date': match.get('date', ''),
                            'trigger_at': trigger_at,
                            'created_at': now_turkey_iso(),
                            'alarm_type': 'publicmove'
                        }
                        alarms.append(alarm)
                        log(f"  [PUBLICMOVE] {home} vs {away} | {market_names.get(market, market)}-{selection} | Score: {move_score:.1f} | Vol: £{volume_change:,.0f}")
        
        if alarms:
            new_count = self._upsert_alarms('publicmove_alarms', alarms, ['home', 'away', 'market', 'selection'])
            log(f"PublicMove: {new_count} alarms upserted")
        else:
            log("PublicMove: 0 alarm")
        
        return len(alarms)
    
    def calculate_volumeleader_alarms(self) -> int:
        """Calculate Volume Leader Changed alarms"""
        # NOT: VolumeLeader alarmları silinmez - sadece upsert yapılır
        # Tablo temizleme KALDIRILDI - alarmlar kalıcı olmalı
        
        config = self.configs.get('volumeleader')
        if not config:
            log("[VolumeLeader] CONFIG YOK - Supabase'de volumeleader ayarlarını kaydedin!")
            return 0
        
        # Config validation
        required_keys = ['min_volume_1x2', 'min_volume_ou25', 'min_volume_btts']
        missing_keys = [k for k in required_keys if config.get(k) is None]
        if missing_keys:
            log(f"[VolumeLeader] CONFIG EKSIK KEY'LER: {missing_keys} - Supabase'de tamamlayın!")
            return 0
        
        # threshold opsiyonel, yoksa 50 kullan
        threshold = parse_float(config.get('leader_threshold')) or 50
        log(f"[VolumeLeader Config] threshold: {threshold}%")
        
        alarms = []
        markets = ['moneyway_1x2', 'moneyway_ou25', 'moneyway_btts']
        market_names = {'moneyway_1x2': '1X2', 'moneyway_ou25': 'O/U 2.5', 'moneyway_btts': 'BTTS'}
        
        for market in markets:
            if '1x2' in market:
                min_volume = parse_float(config.get('min_volume_1x2'))
                selections = ['1', 'X', '2']
                amount_keys = ['amt1', 'amtx', 'amt2']
            elif 'ou25' in market:
                min_volume = parse_float(config.get('min_volume_ou25'))
                selections = ['Over', 'Under']
                amount_keys = ['amtover', 'amtunder']
            else:
                min_volume = parse_float(config.get('min_volume_btts'))
                selections = ['Yes', 'No']
                amount_keys = ['amtyes', 'amtno']
            
            history_table = f"{market}_history"
            matches = self.get_matches_with_latest(market)
            
            for match in matches:
                if not self._is_valid_match_date(match.get('date', '')):
                    continue
                
                home = match.get('home', match.get('Home', ''))
                away = match.get('away', match.get('Away', ''))
                if not home or not away:
                    continue
                
                total_volume = parse_volume(match.get('volume', '0'))
                if total_volume < min_volume:
                    continue
                
                history = self.get_match_history(home, away, history_table)
                if len(history) < 2:
                    continue
                
                for i in range(1, len(history)):
                    prev_snap = history[i-1]
                    curr_snap = history[i]
                    
                    prev_amounts = [(sel, parse_volume(prev_snap.get(key, 0))) 
                                   for sel, key in zip(selections, amount_keys)]
                    curr_amounts = [(sel, parse_volume(curr_snap.get(key, 0))) 
                                   for sel, key in zip(selections, amount_keys)]
                    
                    prev_total = sum(a[1] for a in prev_amounts)
                    curr_total = sum(a[1] for a in curr_amounts)
                    
                    if prev_total <= 0 or curr_total <= 0:
                        continue
                    
                    prev_shares = [(sel, (amt / prev_total) * 100) for sel, amt in prev_amounts]
                    curr_shares = [(sel, (amt / curr_total) * 100) for sel, amt in curr_amounts]
                    
                    prev_leader = max(prev_shares, key=lambda x: x[1])
                    curr_leader = max(curr_shares, key=lambda x: x[1])
                    
                    if prev_leader[0] != curr_leader[0] and curr_leader[1] >= threshold:
                        trigger_volume = curr_total
                        # Trigger anındaki volume da min_volume eşiğini geçmeli!
                        if trigger_volume < min_volume:
                            continue
                        
                        trigger_at = curr_snap.get('scraped_at', now_turkey_iso())
                        match_id = generate_match_id_hash(home, away, match.get('league', ''), match.get('kickoff', match.get('kickoff_utc', '')))
                        
                        alarm = {
                            'match_id': match_id,
                            'home': home,
                            'away': away,
                            'market': market_names.get(market, market),
                            'old_leader': prev_leader[0],
                            'old_leader_share': round(prev_leader[1], 1),
                            'new_leader': curr_leader[0],
                            'new_leader_share': round(curr_leader[1], 1),
                            'total_volume': trigger_volume,
                            'match_date': match.get('date', ''),
                            'trigger_at': trigger_at,
                            'created_at': now_turkey_iso(),
                            'alarm_type': 'volumeleader'
                        }
                        alarms.append(alarm)
                        log(f"  [VOLUMELEADER] {home} vs {away} | {market_names.get(market, market)} | {prev_leader[0]}(%{prev_leader[1]:.0f})->{curr_leader[0]}(%{curr_leader[1]:.0f})")
        
        if alarms:
            existing = self._get('volume_leader_alarms', 'select=home,away,market,old_leader,new_leader')
            existing_keys = set()
            for e in existing:
                key = f"{e.get('home')}_{e.get('away')}_{e.get('market')}_{e.get('old_leader')}_{e.get('new_leader')}"
                existing_keys.add(key)
            
            # BATCH İÇİ TEKİLLEŞTİRME - Aynı key'e sahip alarm varsa son olanı tut
            unique_alarms = {}
            for alarm in alarms:
                key = f"{alarm['home']}_{alarm['away']}_{alarm['market']}_{alarm['old_leader']}_{alarm['new_leader']}"
                if key not in existing_keys:
                    # Aynı key varsa üzerine yaz (son/en güncel olanı tutar)
                    unique_alarms[key] = alarm
            
            new_alarms = list(unique_alarms.values())
            
            if new_alarms:
                self._post('volume_leader_alarms', new_alarms, on_conflict='home,away,market,old_leader,new_leader')
                log(f"VolumeLeader: {len(new_alarms)} new alarms added (tekilleştirildi)")
            else:
                log("VolumeLeader: 0 yeni alarm (mevcut alarmlar)")
        else:
            log("VolumeLeader: 0 alarm")
        
        return len(alarms)


    def calculate_mim_alarms(self) -> int:
        """Calculate MIM (Market Impact) alarms
        
        MIM Formülü:
        - Impact = (current_volume - prev_volume) / current_volume
        - Alarm üretilir: impact >= min_impact_threshold AND prev_volume >= min_prev_volume
        """
        config = self.configs.get('mim')
        if not config:
            log("[MIM] CONFIG YOK - Supabase'de mim ayarlarını kaydedin!")
            return 0
        
        if not config.get('enabled', True):
            log("[MIM] Alarm devre dışı")
            return 0
        
        min_impact_threshold = parse_float(config.get('min_impact_threshold')) or 0.10
        min_prev_volume = parse_float(config.get('min_prev_volume')) or 1000
        
        log(f"[MIM] Config: min_impact_threshold={min_impact_threshold}, min_prev_volume={min_prev_volume}")
        
        alarms = []
        market = 'moneyway_1x2'
        market_name = '1X2'
        
        matches = self.get_matches_with_latest(market)
        if not matches:
            log("[MIM] moneyway_1x2'de maç yok")
            return 0
        
        for match in matches:
            home = match.get('home', '')
            away = match.get('away', '')
            
            if not self._is_valid_match_date(match.get('date', '')):
                continue
            
            history = self.get_match_history(home, away, f"{market}_history")
            if len(history) < 2:
                continue
            
            sorted_history = sorted(history, key=lambda x: x.get('scraped_at', ''))
            
            for i in range(1, len(sorted_history)):
                prev_snap = sorted_history[i - 1]
                curr_snap = sorted_history[i]
                
                prev_amt_1 = parse_volume(prev_snap.get('total_amount_1', 0))
                prev_amt_x = parse_volume(prev_snap.get('total_amount_x', 0))
                prev_amt_2 = parse_volume(prev_snap.get('total_amount_2', 0))
                prev_volume = prev_amt_1 + prev_amt_x + prev_amt_2
                
                curr_amt_1 = parse_volume(curr_snap.get('total_amount_1', 0))
                curr_amt_x = parse_volume(curr_snap.get('total_amount_x', 0))
                curr_amt_2 = parse_volume(curr_snap.get('total_amount_2', 0))
                curr_volume = curr_amt_1 + curr_amt_x + curr_amt_2
                
                if prev_volume < min_prev_volume:
                    continue
                
                if curr_volume <= 0:
                    continue
                
                impact = (curr_volume - prev_volume) / curr_volume
                
                if impact < min_impact_threshold:
                    continue
                
                trigger_at = curr_snap.get('scraped_at', now_turkey_iso())
                match_id = generate_match_id_hash(home, away, match.get('league', ''), match.get('kickoff', match.get('kickoff_utc', '')))
                
                alarm = {
                    'match_id': match_id,
                    'home': home,
                    'away': away,
                    'league': match.get('league', ''),
                    'market': market_name,
                    'impact': round(impact, 4),
                    'prev_volume': round(prev_volume, 2),
                    'current_volume': round(curr_volume, 2),
                    'match_date': match.get('date', ''),
                    'trigger_at': trigger_at,
                    'created_at': now_turkey_iso(),
                    'alarm_type': 'mim'
                }
                alarms.append(alarm)
                log(f"  [MIM] {home} vs {away} | Impact: {impact:.2%} | £{prev_volume:,.0f} -> £{curr_volume:,.0f}")
        
        if alarms:
            new_count = self._upsert_alarms('mim_alarms', alarms, ['match_id', 'market', 'trigger_at'])
            log(f"MIM: {new_count} alarms upserted")
            return new_count
        else:
            log("MIM: 0 alarm")
        
        return 0


def run_alarm_calculations(supabase_url: str, supabase_key: str):
    """Main entry point for alarm calculations"""
    calculator = AlarmCalculator(supabase_url, supabase_key)
    calculator.run_all_calculations()


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3:
        run_alarm_calculations(sys.argv[1], sys.argv[2])
    else:
        print("Usage: python alarm_calculator.py <SUPABASE_URL> <SUPABASE_KEY>")
