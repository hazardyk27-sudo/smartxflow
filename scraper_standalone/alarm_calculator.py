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
            return resp.status_code in [200, 201]
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
                    # Preserve ALL timestamp fields from first detection
                    if orig.get('trigger_at'):
                        alarm['trigger_at'] = orig['trigger_at']
                        alarm['event_time'] = orig['trigger_at']
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
                    enabled = setting.get('enabled', True)
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
        """Batch fetch all history for a market with pagination - OPTIMIZED"""
        history_table = f"{market}_history"
        
        if history_table in self._history_cache:
            return self._history_cache[history_table]
        
        yesterday = (now_turkey() - timedelta(days=1)).strftime('%Y-%m-%dT00:00:00')
        
        log(f"FETCH {history_table} (batch with pagination)...")
        
        rows = []
        offset = 0
        page_size = 1000
        max_pages = 10
        
        for page in range(max_pages):
            params = f"select=*&scraped_at=gte.{yesterday}&order=scraped_at.asc&limit={page_size}&offset={offset}"
            batch = self._get(history_table, params)
            if not batch:
                break
            rows.extend(batch)
            if len(batch) < page_size:
                break
            offset += page_size
        
        log(f"  -> {len(rows)} history rows")
        
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
        log("ALARM HESAPLAMA BASLADI")
        log(f"Supabase URL: {self.url[:40]}...")
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
        log(f"HESAPLAMA TAMAMLANDI - TOPLAM: {total_alarms} alarm")
        summary = " | ".join([f"{k}:{v}" for k, v in alarm_counts.items()])
        log(f"  {summary}")
        log("=" * 50)
        
        self.last_alarm_count = total_alarms
        self.alarm_summary = alarm_counts
        
        return total_alarms
    
    def _is_valid_match_date(self, date_str: str) -> bool:
        """Check if match is today or tomorrow (D-2+ filter)"""
        match_date = parse_match_date(date_str)
        if not match_date:
            return True
        
        today = now_turkey().date()
        yesterday = today - timedelta(days=1)
        return match_date.date() >= yesterday
    
    def calculate_sharp_alarms(self) -> int:
        """Calculate Sharp Move alarms"""
        # Her hesaplamada ÖNCE tabloyu temizle - config kontrolünden ÖNCE
        try:
            self._delete('sharp_alarms', '')
            log("[Sharp] Table cleared before recalculation")
        except Exception as e:
            log(f"[Sharp] Table clear failed: {e}")
        
        config = self.configs.get('sharp')
        if not config:
            log("[Sharp] CONFIG YOK - Supabase'de sharp ayarlarını kaydedin!")
            return 0
        
        # Config validation - kritik key'ler mevcut olmalı
        required_keys = ['min_sharp_score', 'min_volume_1x2', 'min_volume_ou25', 'min_volume_btts']
        missing_keys = [k for k in required_keys if config.get(k) is None]
        if missing_keys:
            log(f"[Sharp] CONFIG EKSIK KEY'LER: {missing_keys} - Supabase'de tamamlayın!")
            return 0
        
        # CRITICAL: parse_float ile float'a çevir - FALLBACK OLMADAN
        min_score = parse_float(config.get('min_sharp_score'))
        vol_mult = parse_float(config.get('volume_multiplier')) or 1.0
        odds_mult_default = parse_float(config.get('odds_multiplier')) or 1.0
        share_mult = parse_float(config.get('share_multiplier')) or 1.0
        min_amount_change = parse_float(config.get('min_amount_change')) or 0
        
        # Odds Range Multipliers - oran aralığına göre farklı çarpanlar
        odds_ranges = []
        for i in range(1, 5):
            range_min = parse_float(config.get(f'odds_range_{i}_min')) or 0
            range_max = parse_float(config.get(f'odds_range_{i}_max')) or 99
            range_mult = parse_float(config.get(f'odds_range_{i}_mult')) or odds_mult_default
            if range_min > 0 or range_max < 99:
                odds_ranges.append({'min': range_min, 'max': range_max, 'mult': range_mult})
        
        log(f"[Sharp Config] min_score: {min_score}, vol_mult: {vol_mult}, min_amount_change: {min_amount_change}")
        if odds_ranges:
            log(f"[Sharp Config] Odds ranges: {len(odds_ranges)} defined")
        
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
                first = history[0]
                
                for sel_idx, selection in enumerate(selections):
                    odds_key = odds_keys[sel_idx]
                    amount_key = amount_keys[sel_idx]
                    pct_key = pct_keys[sel_idx]
                    
                    current_odds = parse_float(latest.get(odds_key, 0))
                    prev_odds = parse_float(prev.get(odds_key, 0))
                    opening_odds = parse_float(first.get(odds_key, 0))
                    
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
                    
                    volume_contrib = min(10, (volume_change / 1000) * vol_mult)
                    
                    # Odds range'e göre multiplier seç
                    odds_mult = odds_mult_default
                    for odr in odds_ranges:
                        if odr['min'] <= current_odds <= odr['max']:
                            odds_mult = odr['mult']
                            break
                    
                    odds_contrib = min(10, (odds_drop / 0.05) * 2 * odds_mult)
                    share_contrib = min(10, share_change * share_mult) if share_change > 0 else 0
                    
                    sharp_score = volume_contrib + odds_contrib + share_contrib
                    
                    if sharp_score >= min_score:
                        trigger_at = latest.get('scraped_at', now_turkey_iso())
                        match_id = f"{home}|{away}|{match.get('date', '')}"
                        
                        drop_percentage = ((opening_odds - current_odds) / opening_odds * 100) if opening_odds > 0 else 0
                        share_change_pct = current_pct - prev_pct
                        
                        alarm = {
                            'match_id': match_id,
                            'home': home,
                            'away': away,
                            'market': market_names.get(market, market),
                            'selection': selection,
                            'sharp_score': round(sharp_score, 2),
                            'smart_score': round(sharp_score, 2),
                            'drop_percentage': round(drop_percentage, 2),
                            'volume_shock_multiplier': round(volume_contrib, 2),
                            'share_change_percent': round(share_change_pct, 2),
                            'weights': json.dumps({'volume': vol_mult, 'odds': odds_mult, 'share': share_mult}),
                            'volume_contrib': round(volume_contrib, 2),
                            'odds_contrib': round(odds_contrib, 2),
                            'share_contrib': round(share_contrib, 2),
                            'volume': volume_change,
                            'opening_odds': opening_odds,
                            'previous_odds': prev_odds,
                            'current_odds': current_odds,
                            'previous_share': prev_pct,
                            'current_share': current_pct,
                            'match_date': match.get('date', ''),
                            'event_time': trigger_at,
                            'trigger_at': trigger_at,
                            'created_at': now_turkey_iso(),
                            'alarm_type': 'sharp'
                        }
                        alarms.append(alarm)
                        log(f"  [SHARP] {home} vs {away} | {market_names.get(market, market)}-{selection} | Score: {sharp_score:.1f} | Vol: £{volume_change:,.0f}")
        
        if alarms:
            new_count = self._upsert_alarms('sharp_alarms', alarms, ['home', 'away', 'market', 'selection'])
            log(f"Sharp: {new_count} alarms upserted")
        else:
            log("Sharp: 0 alarm")
        
        return len(alarms)
    
    def calculate_insider_alarms(self) -> int:
        """Calculate Insider Info alarms"""
        # Her hesaplamada ÖNCE tabloyu temizle - config kontrolünden ÖNCE
        try:
            self._delete('insider_alarms', '')
            log("[Insider] Table cleared before recalculation")
        except Exception as e:
            log(f"[Insider] Table clear failed: {e}")
        
        config = self.configs.get('insider')
        if not config:
            log("[Insider] CONFIG YOK - Supabase'de insider ayarlarını kaydedin!")
            return 0
        
        # Config validation - TÜM gerekli key'ler mevcut olmalı
        required_keys = ['hacim_sok_esigi', 'oran_dusus_esigi', 'max_para', 'max_odds_esigi', 'sure_dakika']
        missing_keys = [k for k in required_keys if config.get(k) is None]
        if missing_keys:
            log(f"[Insider] CONFIG EKSIK KEY'LER: {missing_keys} - Supabase'de tamamlayın!")
            return 0
        
        # CRITICAL: parse_float ile float'a çevir - FALLBACK OLMADAN
        hacim_sok_esigi = parse_float(config.get('hacim_sok_esigi'))
        oran_dusus_esigi = parse_float(config.get('oran_dusus_esigi'))
        max_para = parse_float(config.get('max_para'))
        max_odds = parse_float(config.get('max_odds_esigi'))
        sure_dakika = parse_float(config.get('sure_dakika')) or 30  # Time window için minimum 30
        log(f"[Insider Config] hacim_sok: {hacim_sok_esigi}, oran_dusus: {oran_dusus_esigi}, max_para: {max_para}, max_odds: {max_odds}, sure: {sure_dakika}dk")
        
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
                    
                    if current_odds > max_odds:
                        continue
                    
                    if current_odds >= opening_odds:
                        continue
                    
                    oran_dusus_pct = ((opening_odds - current_odds) / opening_odds) * 100
                    
                    if oran_dusus_pct < oran_dusus_esigi:
                        continue
                    
                    # SADECE son sure_dakika içindeki snapshot'ları kullan - ESKİ VERİLERİ ATLA
                    now = now_turkey()
                    cutoff_time = now - timedelta(minutes=sure_dakika)
                    
                    # History'yi filtrele - sadece cutoff_time'dan sonraki snapshot'lar
                    recent_history = []
                    for snap in history:
                        scraped_at = snap.get('scraped_at', '')
                        if scraped_at:
                            try:
                                # ISO format parse et
                                if '+' in scraped_at:
                                    snap_time = datetime.fromisoformat(scraped_at.replace('Z', '+00:00'))
                                else:
                                    snap_time = datetime.fromisoformat(scraped_at)
                                    if TURKEY_TZ:
                                        snap_time = TURKEY_TZ.localize(snap_time)
                                
                                # Timezone-aware karşılaştırma
                                if snap_time.tzinfo:
                                    if cutoff_time.tzinfo is None and TURKEY_TZ:
                                        cutoff_time = TURKEY_TZ.localize(cutoff_time)
                                
                                if snap_time >= cutoff_time:
                                    recent_history.append(snap)
                            except:
                                recent_history.append(snap)  # Parse edilemezse dahil et
                        else:
                            recent_history.append(snap)
                    
                    # Yeterli recent snapshot yoksa atla
                    if len(recent_history) < 2:
                        continue
                    
                    total_incoming = 0
                    max_hacim_sok = 0
                    trigger_snap = recent_history[-1]
                    trigger_snap_index = len(recent_history) - 1
                    all_hacim_soks = []
                    
                    for i in range(1, len(recent_history)):
                        curr_amt = parse_volume(recent_history[i].get(amount_key, 0))
                        prev_amt = parse_volume(recent_history[i-1].get(amount_key, 0))
                        incoming = curr_amt - prev_amt
                        
                        if incoming > 0:
                            total_incoming += incoming
                            
                            prev_amts = [parse_volume(recent_history[j].get(amount_key, 0)) 
                                        for j in range(max(0, i-5), i)]
                            avg_prev = sum(prev_amts) / len(prev_amts) if prev_amts else 1
                            hacim_sok = incoming / avg_prev if avg_prev > 0 else 0
                            all_hacim_soks.append(hacim_sok)
                            
                            if hacim_sok > max_hacim_sok:
                                max_hacim_sok = hacim_sok
                                trigger_snap = recent_history[i]
                                trigger_snap_index = i
                    
                    # KRITIK: gelen_para = 0 ise alarm tetikleme!
                    # Insider = "para girmeden oran düşüşü" ama en az BİRAZ para hareketi olmalı
                    if total_incoming <= 0:
                        continue
                    
                    if total_incoming >= max_para:
                        continue
                    
                    # INSIDER MANTIK: Hacim şoku DÜŞÜK olmalı (para girmeden oran düşüşü)
                    # hacim_sok_esigi = maksimum kabul edilebilir hacim şoku
                    # Eğer hacim şoku bu eşikten BÜYÜKSE, bu insider değil normal hareket
                    if max_hacim_sok > hacim_sok_esigi:
                        continue
                    
                    trigger_at = trigger_snap.get('scraped_at', now_turkey_iso())
                    
                    start_idx = max(0, trigger_snap_index - 3)
                    end_idx = min(len(recent_history), trigger_snap_index + 4)
                    surrounding = []
                    surrounding_hacim_soks = []
                    surrounding_incomings = []
                    
                    for si in range(start_idx, end_idx):
                        snap = recent_history[si]
                        snap_amt = parse_volume(snap.get(amount_key, 0))
                        prev_snap_amt = parse_volume(recent_history[si-1].get(amount_key, 0)) if si > 0 else 0
                        snap_incoming = max(0, snap_amt - prev_snap_amt)
                        
                        prev_window = [parse_volume(recent_history[j].get(amount_key, 0)) for j in range(max(0, si-5), si)]
                        avg_prev_window = sum(prev_window) / len(prev_window) if prev_window else 1
                        snap_hacim_sok = snap_incoming / avg_prev_window if avg_prev_window > 0 and snap_incoming > 0 else 0
                        
                        surrounding_hacim_soks.append(snap_hacim_sok)
                        surrounding_incomings.append(snap_incoming)
                        
                        surrounding.append({
                            'index': si,
                            'scraped_at': snap.get('scraped_at', ''),
                            'odds': parse_float(snap.get(odds_key, 0)),
                            'amount': snap_amt,
                            'incoming': round(snap_incoming, 0),
                            'hacim_sok': round(snap_hacim_sok, 4),
                            'is_trigger': si == trigger_snap_index
                        })
                    
                    avg_hacim_sok = sum(surrounding_hacim_soks) / len(surrounding_hacim_soks) if surrounding_hacim_soks else 0
                    max_surrounding_hacim_sok = max(surrounding_hacim_soks) if surrounding_hacim_soks else 0
                    max_surrounding_incoming = max(surrounding_incomings) if surrounding_incomings else 0
                    match_id = f"{home}|{away}|{match.get('date', '')}"
                    
                    alarm = {
                        'match_id': match_id,
                        'home': home,
                        'away': away,
                        'market': market_names.get(market, market),
                        'selection': selection,
                        'odds_change_percent': round(oran_dusus_pct, 2),
                        'oran_dusus_pct': round(oran_dusus_pct, 2),
                        'gelen_para': total_incoming,
                        'hacim_sok': round(max_hacim_sok, 3),
                        'avg_volume_shock': round(avg_hacim_sok, 4),
                        'max_surrounding_hacim_sok': round(max_surrounding_hacim_sok, 4),
                        'max_surrounding_incoming': round(max_surrounding_incoming, 0),
                        'open_odds': opening_odds,
                        'opening_odds': opening_odds,
                        'current_odds': current_odds,
                        'drop_moment_index': trigger_snap_index,
                        'drop_moment': trigger_at,
                        'surrounding_snapshots': surrounding,
                        'surrounding_count': len(surrounding),
                        'snapshot_count': len(recent_history),
                        'match_date': match.get('date', ''),
                        'event_time': trigger_at,
                        'trigger_at': trigger_at,
                        'created_at': now_turkey_iso(),
                        'alarm_type': 'insider'
                    }
                    alarms.append(alarm)
                    log(f"  [INSIDER] {home} vs {away} | {market_names.get(market, market)}-{selection} | Oran: {opening_odds:.2f}->{current_odds:.2f} (-%{oran_dusus_pct:.1f}) | Para: {total_incoming:,.0f} GBP")
        
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
                            'event_time': trigger_at,
                            'trigger_at': trigger_at,
                            'created_at': now_turkey_iso()
                        }
                        alarms.append(alarm)
                        alarm_label = 'HUGE' if is_huge else 'BIG'
                        log(f"  [{alarm_label} MONEY] {home} vs {away} | {market_names.get(market, market)}-{selection} | £{snap['incoming']:,.0f} gelen")
        
        if alarms:
            # trigger_at dahil - her hareket ayrı kayıt olsun
            new_count = self._upsert_alarms('bigmoney_alarms', alarms, ['home', 'away', 'market', 'selection', 'trigger_at'])
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
                            'volume_shock_value': round(shock_value, 2),
                            'multiplier': round(shock_value, 2),
                            'new_money': incoming,
                            'incoming_money': incoming,
                            'avg_last_10': round(avg_prev, 0),
                            'avg_previous': round(avg_prev, 0),
                            'match_date': match.get('date', ''),
                            'event_time': trigger_at,
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
        """Calculate Dropping Odds alarms"""
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
        log(f"[Dropping Config] L1: {l1_min}-{l1_max}%, L2: {l2_min}-{l2_max}%, L3: {l3_min}%+")
        
        alarms = []
        markets = ['dropping_1x2', 'dropping_ou25', 'dropping_btts']
        market_names = {'dropping_1x2': '1X2', 'dropping_ou25': 'O/U 2.5', 'dropping_btts': 'BTTS'}
        
        for market in markets:
            if '1x2' in market:
                selections = ['1', 'X', '2']
                odds_keys = ['odds1', 'oddsx', 'odds2']
                odds_prev_keys = ['odds1_prev', 'oddsx_prev', 'odds2_prev']
            elif 'ou25' in market:
                selections = ['Over', 'Under']
                odds_keys = ['over', 'under']
                odds_prev_keys = ['over_prev', 'under_prev']
            else:
                selections = ['Yes', 'No']
                odds_keys = ['oddsyes', 'oddsno']
                odds_prev_keys = ['oddsyes_prev', 'oddsno_prev']
            
            matches = self.get_matches_with_latest(market)
            
            for match in matches:
                if not self._is_valid_match_date(match.get('date', '')):
                    continue
                
                home = match.get('home', match.get('Home', ''))
                away = match.get('away', match.get('Away', ''))
                if not home or not away:
                    continue
                
                for sel_idx, selection in enumerate(selections):
                    odds_key = odds_keys[sel_idx]
                    odds_prev_key = odds_prev_keys[sel_idx]
                    
                    current_odds = parse_float(match.get(odds_key, 0))
                    opening_odds = parse_float(match.get(odds_prev_key, 0))
                    
                    if current_odds <= 0 or opening_odds <= 0:
                        continue
                    
                    if current_odds >= opening_odds:
                        continue
                    
                    drop_pct = ((opening_odds - current_odds) / opening_odds) * 100
                    
                    if drop_pct < l1_min:
                        continue
                    
                    if drop_pct >= l3_min:
                        level = 'L3'
                    elif drop_pct >= l2_min:
                        level = 'L2'
                    else:
                        level = 'L1'
                    
                    trigger_at = now_turkey_iso()
                    match_id = f"{home}|{away}|{match.get('date', '')}"
                    
                    alarm = {
                        'match_id': match_id,
                        'home': home,
                        'away': away,
                        'market': market_names.get(market, market),
                        'selection': selection,
                        'open_odds': opening_odds,
                        'opening_odds': opening_odds,
                        'current_odds': current_odds,
                        'drop_percentage': round(drop_pct, 2),
                        'drop_pct': round(drop_pct, 2),
                        'level': level,
                        'match_date': match.get('date', ''),
                        'event_time': trigger_at,
                        'trigger_at': trigger_at,
                        'created_at': now_turkey_iso(),
                        'alarm_type': 'dropping'
                    }
                    alarms.append(alarm)
                    log(f"  [DROPPING-{level}] {home} vs {away} | {market_names.get(market, market)}-{selection} | {opening_odds:.2f}->{current_odds:.2f} (-%{drop_pct:.1f})")
        
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
                            'move_score': round(move_score, 2),
                            'volume': volume_change,
                            'odds_drop': odds_drop,
                            'share_before': round(prev_pct, 2),
                            'share_after': round(current_pct, 2),
                            'delta': round(share_change, 2),
                            'share_change': share_change,
                            'match_date': match.get('date', ''),
                            'event_time': trigger_at,
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
                        trigger_at = curr_snap.get('scraped_at', now_turkey_iso())
                        trigger_volume = curr_total
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
                            'event_time': trigger_at,
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
            
            new_alarms = []
            for alarm in alarms:
                key = f"{alarm['home']}_{alarm['away']}_{alarm['market']}_{alarm['old_leader']}_{alarm['new_leader']}"
                if key not in existing_keys:
                    new_alarms.append(alarm)
            
            if new_alarms:
                self._post('volume_leader_alarms', new_alarms, on_conflict='home,away,market,old_leader,new_leader')
                log(f"VolumeLeader: {len(new_alarms)} new alarms added")
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
