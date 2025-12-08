"""
SmartXFlow Alarm Calculator Module
Standalone alarm calculation for PC-based scraper
Calculates: Sharp, Insider, BigMoney, VolumeShock, Dropping, PublicMove, VolumeLeader
OPTIMIZED: Batch fetch per market, in-memory calculations
"""

import json
import os
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
            url = f"{self._rest_url(table)}?{params}"
            if hasattr(httpx, 'delete'):
                resp = httpx.delete(url, headers=self._headers(), timeout=30)
            else:
                resp = httpx.delete(url, headers=self._headers(), timeout=30)
            return resp.status_code in [200, 204]
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
        
        # VARSAYILAN DEĞER YOK - Sadece Supabase'den okunan config kullanılır
        if not self.configs:
            log("ERROR: alarm_settings tablosu boş! Supabase'de config ayarlayın.")
            log("Alarm hesaplaması YAPILMAYACAK - önce config'leri kaydedin.")
    
    def _default_configs(self) -> Dict:
        """VARSAYILAN DEĞER YOK - Boş dict döndür
        Tüm config değerleri Supabase alarm_settings tablosundan okunmalı.
        Eğer config yoksa alarm hesaplanmaz."""
        return {}
    
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
        
        log("1/7 Sharp hesaplaniyor...")
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
        
        log("2/7 Insider hesaplaniyor...")
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
        
        log("3/7 BigMoney hesaplaniyor...")
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
        
        log("5/7 Dropping hesaplaniyor...")
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
        
        log("6/7 PublicMove hesaplaniyor...")
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
        
        log("7/7 VolumeLeader hesaplaniyor...")
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
        
        log("=" * 50)
        log(f"[ALARM SYNC] HESAPLAMA TAMAMLANDI - TOPLAM: {total_alarms} alarm")
        summary = ", ".join([f"{k}={v}" for k, v in alarm_counts.items()])
        log(f"[ALARM SYNC] Upserted alarm records: {summary}")
        log("=" * 50)
        
        self.last_alarm_count = total_alarms
        self.alarm_summary = alarm_counts
        
        return total_alarms
    
    def _is_valid_match_date(self, date_str: str) -> bool:
        """Check if match is within valid date range (past 7 days to future 7 days)"""
        match_date = parse_match_date(date_str)
        if not match_date:
            return True
        
        today = now_turkey().date()
        past_limit = today - timedelta(days=7)
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
        try:
            self._delete('sharp_alarms', '')
            log("[Sharp] Table cleared before recalculation")
        except Exception as e:
            log(f"[Sharp] Table clear failed: {e}")
        
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
                        match_id = f"{home}|{away}|{match.get('date', '')}"
                        
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
        """
        try:
            self._delete('insider_alarms', '')
            log("[Insider] Table cleared before recalculation")
        except Exception as e:
            log(f"[Insider] Table clear failed: {e}")
        
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
                
                for sel_idx, selection in enumerate(selections):
                    odds_key = odds_keys[sel_idx]
                    amount_key = amount_keys[sel_idx]
                    
                    opening_odds = parse_float(first.get(odds_key, 0))
                    
                    if opening_odds <= 0:
                        continue
                    
                    # KURAL 1: En büyük tek seferlik ORAN düşüşünün olduğu snapshot'ı bul
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
                    
                    # KURAL 5: Window'daki son snapshot'ta kontroller
                    if not surrounding_details:
                        continue
                    
                    last_snap = surrounding_details[-1]
                    last_snap_drop = last_snap.get('drop_pct', 0)
                    last_snap_odds = last_snap.get('odds', 0)
                    
                    # Son snapshot'ta max_odds kontrolü
                    if last_snap_odds <= 0 or last_snap_odds > max_odds:
                        continue
                    
                    # Son snapshot'ta drop eşiği karşılanmalı
                    if last_snap_drop < oran_dusus_esigi:
                        # Oran düzelmiş, alarm tetiklenmez
                        continue
                    
                    # Güncel değerler window'un son snapshot'ından alınır
                    actual_current_odds = last_snap_odds
                    actual_drop_pct = last_snap_drop
                    
                    trigger_snap = history[drop_moment_index]
                    trigger_at = trigger_snap.get('scraped_at', now_turkey_iso())
                    match_id = f"{home}|{away}|{match.get('date', '')}"
                    
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
                    log(f"  [INSIDER] {home} vs {away} | {market_names.get(market, market)}-{selection} | Oran: {opening_odds:.2f}->{actual_current_odds:.2f} (-%{actual_drop_pct:.1f}) | DüsusAnı: S{drop_moment_index} | Para: {total_incoming:,.0f}")
        
        if alarms:
            new_count = self._upsert_alarms('insider_alarms', alarms, ['home', 'away', 'market', 'selection'])
            log(f"Insider: {new_count} alarms upserted")
        else:
            log("Insider: 0 alarm")
        
        return len(alarms)
    
    def calculate_bigmoney_alarms(self) -> int:
        """Calculate Big Money / Huge Money alarms"""
        # Her hesaplamada ÖNCE tabloyu temizle - config kontrolünden ÖNCE
        try:
            self._delete('bigmoney_alarms', '')
            log("[BigMoney] Table cleared before recalculation")
        except Exception as e:
            log(f"[BigMoney] Table clear failed: {e}")
        
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
                    match_id = f"{home}|{away}|{match.get('date', '')}"
                    
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
            # Constraint: match_id, market, selection
            new_count = self._upsert_alarms('bigmoney_alarms', alarms, ['match_id', 'market', 'selection'])
            log(f"BigMoney: {new_count} alarms upserted")
        else:
            log("BigMoney: 0 alarm")
        
        return len(alarms)
    
    def calculate_volumeshock_alarms(self) -> int:
        """Calculate Volume Shock alarms"""
        # Her hesaplamada ÖNCE tabloyu temizle - config kontrolünden ÖNCE
        try:
            self._delete('volumeshock_alarms', '')
            log("[VolumeShock] Table cleared before recalculation")
        except Exception as e:
            log(f"[VolumeShock] Table clear failed: {e}")
        
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
                    
                    latest_amt = parse_volume(history[-1].get(amount_key, 0))
                    prev_amt = parse_volume(history[-2].get(amount_key, 0))
                    incoming = latest_amt - prev_amt
                    
                    if incoming <= 0:
                        continue
                    
                    # min_son_snapshot_para filtresi
                    if incoming < min_incoming:
                        continue
                    
                    prev_amts = [parse_volume(history[i].get(amount_key, 0)) - 
                                parse_volume(history[i-1].get(amount_key, 0))
                                for i in range(-5, -1)]
                    prev_amts = [a for a in prev_amts if a > 0]
                    
                    if not prev_amts:
                        continue
                    
                    avg_prev = sum(prev_amts) / len(prev_amts)
                    shock_value = incoming / avg_prev if avg_prev > 0 else 0
                    
                    if shock_value >= shock_mult:
                        trigger_at = history[-1].get('scraped_at', now_turkey_iso())
                        match_id = f"{home}|{away}|{match.get('date', '')}"
                        
                        alarm = {
                            'match_id': match_id,
                            'home': home,
                            'away': away,
                            'market': market_names.get(market, market),
                            'selection': selection,
                            'volume_shock': round(shock_value, 2),
                            'volume_shock_multiplier': round(shock_value, 2),
                            'incoming_money': incoming,
                            'avg_previous': round(avg_prev, 0),
                            'match_date': match.get('date', ''),
                            'trigger_at': trigger_at,
                            'created_at': now_turkey_iso(),
                            'alarm_type': 'volumeshock'
                        }
                        alarms.append(alarm)
                        log(f"  [VOLUMESHOCK] {home} vs {away} | {market_names.get(market, market)}-{selection} | Shock: {shock_value:.1f}x | £{incoming:,.0f} gelen")
        
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
        """
        # Her hesaplamada ÖNCE tabloyu temizle - config kontrolünden ÖNCE
        try:
            self._delete('dropping_alarms', '')
            log("[Dropping] Table cleared before recalculation")
        except Exception as e:
            log(f"[Dropping] Table clear failed: {e}")
        
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
        
        log(f"[Dropping Config] L1: {l1_min}-{l1_max}%, L2: {l2_min}-{l2_max}%, L3: {l3_min}%+, Kalıcılık: {'AÇIK' if persistence_enabled else 'KAPALI'} ({persistence_minutes} dk)")
        
        alarms = []
        markets = ['dropping_1x2', 'dropping_ou25', 'dropping_btts']
        market_names = {'dropping_1x2': '1X2', 'dropping_ou25': 'O/U 2.5', 'dropping_btts': 'BTTS'}
        
        for market in markets:
            if '1x2' in market:
                selections = ['1', 'X', '2']
                odds_keys = ['odds1', 'oddsx', 'odds2']
            elif 'ou25' in market:
                selections = ['Over', 'Under']
                odds_keys = ['over', 'under']
            else:
                selections = ['Yes', 'No']
                odds_keys = ['oddsyes', 'oddsno']
            
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
                    match_id = f"{home}|{away}|{match.get('date', '')}"
                    
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
                        'persistence_minutes': persistence_minutes,
                        'snapshots_checked': len(recent_snapshots) if 'recent_snapshots' in dir() else 0
                    }
                    alarms.append(alarm)
                    log(f"  [DROPPING-{level}] {home} vs {away} | {market_names.get(market, market)}-{selection} | {opening_odds:.2f}->{current_odds:.2f} (-%{drop_pct:.1f}) | Kalıcı: {len(recent_snapshots) if 'recent_snapshots' in dir() else 0} snap")
        
        if alarms:
            new_count = self._upsert_alarms('dropping_alarms', alarms, ['home', 'away', 'market', 'selection'])
            log(f"Dropping: {new_count} alarms upserted")
        else:
            log("Dropping: 0 alarm")
        
        return len(alarms)
    
    def calculate_publicmove_alarms(self) -> int:
        """Calculate Public Move alarms - same logic as Sharp"""
        # Her hesaplamada ÖNCE tabloyu temizle - config kontrolünden ÖNCE
        try:
            self._delete('publicmove_alarms', '')
            log("[PublicMove] Table cleared before recalculation")
        except Exception as e:
            log(f"[PublicMove] Table clear failed: {e}")
        
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
                        match_id = f"{home}|{away}|{match.get('date', '')}"
                        
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
        # Her hesaplamada ÖNCE tabloyu temizle - config kontrolünden ÖNCE
        try:
            self._delete('volume_leader_alarms', '')
            log("[VolumeLeader] Table cleared before recalculation")
        except Exception as e:
            log(f"[VolumeLeader] Table clear failed: {e}")
        
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
                        match_id = f"{home}|{away}|{match.get('date', '')}"
                        
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
