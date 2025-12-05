"""
SmartXFlow Alarm Calculator Module
Standalone alarm calculation for PC-based scraper
Calculates: Sharp, Insider, BigMoney, VolumeShock, Dropping, PublicTrap, VolumeLeader
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
    return now_turkey().strftime('%Y-%m-%dT%H:%M:%S')


def log(msg: str):
    timestamp = now_turkey().strftime('%H:%M')
    full_msg = f"[{timestamp}] [AlarmCalc] {msg}"
    if _logger_callback:
        _logger_callback(full_msg)
    else:
        print(full_msg)


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
    
    def _post(self, table: str, data: List[Dict]) -> bool:
        try:
            headers = self._headers()
            headers["Prefer"] = "resolution=merge-duplicates"
            if hasattr(httpx, 'post'):
                resp = httpx.post(self._rest_url(table), headers=headers, json=data, timeout=30)
            else:
                resp = httpx.post(self._rest_url(table), headers=headers, json=data, timeout=30)
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
        """Upsert alarms - only add new ones based on key_fields"""
        if not alarms:
            return 0
        
        try:
            existing = self._get(table, f'select={",".join(key_fields)}')
            existing_keys = set()
            for e in existing:
                key = "_".join(str(e.get(f, '')) for f in key_fields)
                existing_keys.add(key)
            
            new_alarms = []
            for alarm in alarms:
                key = "_".join(str(alarm.get(f, '')) for f in key_fields)
                if key not in existing_keys:
                    new_alarms.append(alarm)
            
            if new_alarms:
                self._post(table, new_alarms)
            
            return len(new_alarms)
        except Exception as e:
            log(f"Upsert error {table}: {e}")
            return 0
    
    def load_configs(self):
        """Load all alarm configs from Supabase alarm_settings table"""
        try:
            settings = self._get('alarm_settings', 'select=*')
            for setting in settings:
                alarm_type = setting.get('alarm_type', '')
                enabled = setting.get('enabled', True)
                config = setting.get('config', {})
                if alarm_type:
                    self.configs[alarm_type] = {
                        'enabled': enabled,
                        **config
                    }
            if self.configs:
                log(f"Loaded {len(self.configs)} alarm settings from DB")
                for k, v in self.configs.items():
                    log(f"  - {k}: enabled={v.get('enabled', True)}")
        except Exception as e:
            log(f"Config load error: {e}")
        
        if not self.configs:
            self.configs = self._default_configs()
            log("Using default configs")
    
    def _default_configs(self) -> Dict:
        return {
            'sharp': {
                'min_sharp_score': 15,
                'min_volume_1x2': 3000,
                'min_volume_ou25': 1000,
                'min_volume_btts': 500,
                'volume_multiplier': 1.0,
                'odds_multiplier': 1.0,
                'share_multiplier': 1.0
            },
            'insider': {
                'insider_hacim_sok_esigi': 2,
                'insider_oran_dusus_esigi': 3,
                'insider_sure_dakika': 30,
                'insider_max_para': 5000,
                'insider_max_odds_esigi': 10.0
            },
            'bigmoney': {
                'big_money_limit': 15000
            },
            'volumeshock': {
                'volume_shock_multiplier': 3.0,
                'min_hours_to_kickoff': 2
            },
            'dropping': {
                'min_drop_l1': 7,
                'max_drop_l1': 10,
                'min_drop_l2': 10,
                'max_drop_l2': 15,
                'min_drop_l3': 15
            },
            'publictrap': {
                'min_sharp_score': 20,
                'min_volume_1x2': 5000,
                'min_volume_ou25': 2000,
                'min_volume_btts': 1000
            },
            'volumeleader': {
                'leader_threshold': 50,
                'min_volume_1x2': 5000,
                'min_volume_ou25': 2000,
                'min_volume_btts': 1000
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
            params = f"select=*&scrapedat=gte.{yesterday}&order=scrapedat.asc&limit={page_size}&offset={offset}"
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
            key = f"{home}|{away}"
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
        key = f"{home}|{away}"
        return history_map.get(key, [])
    
    def run_all_calculations(self):
        """Run all alarm calculations - OPTIMIZED with batch fetch"""
        log("=" * 50)
        log("Alarm hesaplamalari basliyor...")
        log("=" * 50)
        
        self._history_cache = {}
        self._matches_cache = {}
        
        markets = ['moneyway_1x2', 'moneyway_ou25', 'moneyway_btts']
        for market in markets:
            try:
                self.get_matches_with_latest(market)
                self.batch_fetch_history(market)
            except Exception as e:
                log(f"Prefetch error {market}: {e}")
        
        log("-" * 30)
        
        try:
            sharp_count = self.calculate_sharp_alarms()
            log(f"Sharp: {sharp_count} alarms")
        except Exception as e:
            log(f"Sharp error: {e}")
        
        try:
            insider_count = self.calculate_insider_alarms()
            log(f"Insider: {insider_count} alarms")
        except Exception as e:
            log(f"Insider error: {e}")
        
        try:
            bigmoney_count = self.calculate_bigmoney_alarms()
            log(f"BigMoney: {bigmoney_count} alarms")
        except Exception as e:
            log(f"BigMoney error: {e}")
        
        try:
            volumeshock_count = self.calculate_volumeshock_alarms()
            log(f"VolumeShock: {volumeshock_count} alarms")
        except Exception as e:
            log(f"VolumeShock error: {e}")
        
        try:
            dropping_count = self.calculate_dropping_alarms()
            log(f"Dropping: {dropping_count} alarms")
        except Exception as e:
            log(f"Dropping error: {e}")
        
        try:
            publictrap_count = self.calculate_publictrap_alarms()
            log(f"PublicTrap: {publictrap_count} alarms")
        except Exception as e:
            log(f"PublicTrap error: {e}")
        
        try:
            volumeleader_count = self.calculate_volumeleader_alarms()
            log(f"VolumeLeader: {volumeleader_count} alarms")
        except Exception as e:
            log(f"VolumeLeader error: {e}")
        
        log("=" * 50)
        log("Alarm hesaplamalari tamamlandi")
        log("=" * 50)
    
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
        config = self.configs.get('sharp', self._default_configs()['sharp'])
        min_score = config.get('min_sharp_score', 15)
        vol_mult = config.get('volume_multiplier', 1.0)
        odds_mult = config.get('odds_multiplier', 1.0)
        share_mult = config.get('share_multiplier', 1.0)
        
        alarms = []
        markets = ['moneyway_1x2', 'moneyway_ou25', 'moneyway_btts']
        market_names = {'moneyway_1x2': '1X2', 'moneyway_ou25': 'O/U 2.5', 'moneyway_btts': 'BTTS'}
        
        for market in markets:
            if '1x2' in market:
                min_volume = config.get('min_volume_1x2', 3000)
                selections = ['1', 'X', '2']
                odds_keys = ['odds1', 'oddsx', 'odds2']
                amount_keys = ['amt1', 'amtx', 'amt2']
                pct_keys = ['pct1', 'pctx', 'pct2']
            elif 'ou25' in market:
                min_volume = config.get('min_volume_ou25', 1000)
                selections = ['Over', 'Under']
                odds_keys = ['over', 'under']
                amount_keys = ['amtover', 'amtunder']
                pct_keys = ['pctover', 'pctunder']
            else:
                min_volume = config.get('min_volume_btts', 500)
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
                    
                    odds_drop = prev_odds - current_odds
                    if odds_drop <= 0:
                        continue
                    
                    share_change = current_pct - prev_pct
                    
                    volume_contrib = min(10, (volume_change / 1000) * vol_mult)
                    odds_contrib = min(10, (odds_drop / 0.05) * 2 * odds_mult)
                    share_contrib = min(10, share_change * share_mult) if share_change > 0 else 0
                    
                    sharp_score = volume_contrib + odds_contrib + share_contrib
                    
                    if sharp_score >= min_score:
                        trigger_at = latest.get('scrapedat', now_turkey_iso())
                        
                        alarm = {
                            'home': home,
                            'away': away,
                            'market': market_names.get(market, market),
                            'selection': selection,
                            'sharp_score': round(sharp_score, 2),
                            'volume_contrib': round(volume_contrib, 2),
                            'odds_contrib': round(odds_contrib, 2),
                            'share_contrib': round(share_contrib, 2),
                            'volume': volume_change,
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
        
        if alarms:
            new_count = self._upsert_alarms('sharp_alarms', alarms, ['home', 'away', 'market', 'selection'])
            log(f"Sharp: {new_count} new alarms added")
        
        return len(alarms)
    
    def calculate_insider_alarms(self) -> int:
        """Calculate Insider Info alarms"""
        config = self.configs.get('insider', self._default_configs()['insider'])
        hacim_sok_esigi = config.get('insider_hacim_sok_esigi', 2)
        oran_dusus_esigi = config.get('insider_oran_dusus_esigi', 3)
        max_para = config.get('insider_max_para', 5000)
        max_odds = config.get('insider_max_odds_esigi', 10.0)
        
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
                    
                    total_incoming = 0
                    max_hacim_sok = 0
                    trigger_snap = latest
                    
                    for i in range(1, len(history)):
                        curr_amt = parse_volume(history[i].get(amount_key, 0))
                        prev_amt = parse_volume(history[i-1].get(amount_key, 0))
                        incoming = curr_amt - prev_amt
                        
                        if incoming > 0:
                            total_incoming += incoming
                            
                            prev_amts = [parse_volume(history[j].get(amount_key, 0)) 
                                        for j in range(max(0, i-5), i)]
                            avg_prev = sum(prev_amts) / len(prev_amts) if prev_amts else 1
                            hacim_sok = incoming / avg_prev if avg_prev > 0 else 0
                            
                            if hacim_sok > max_hacim_sok:
                                max_hacim_sok = hacim_sok
                                trigger_snap = history[i]
                    
                    if total_incoming >= max_para:
                        continue
                    
                    if max_hacim_sok >= hacim_sok_esigi:
                        continue
                    
                    trigger_at = trigger_snap.get('scrapedat', now_turkey_iso())
                    
                    alarm = {
                        'home': home,
                        'away': away,
                        'market': market_names.get(market, market),
                        'selection': selection,
                        'oran_dusus_pct': round(oran_dusus_pct, 2),
                        'gelen_para': total_incoming,
                        'hacim_sok': round(max_hacim_sok, 3),
                        'opening_odds': opening_odds,
                        'current_odds': current_odds,
                        'match_date': match.get('date', ''),
                        'event_time': trigger_at,
                        'trigger_at': trigger_at,
                        'created_at': now_turkey_iso(),
                        'alarm_type': 'insider'
                    }
                    alarms.append(alarm)
        
        if alarms:
            new_count = self._upsert_alarms('insider_alarms', alarms, ['home', 'away', 'market', 'selection'])
            log(f"Insider: {new_count} new alarms added")
        
        return len(alarms)
    
    def calculate_bigmoney_alarms(self) -> int:
        """Calculate Big Money / Huge Money alarms"""
        config = self.configs.get('bigmoney', self._default_configs()['bigmoney'])
        limit = config.get('big_money_limit', 15000)
        
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
                                'scrapedat': history[i].get('scrapedat', '')
                            })
                    
                    if not big_snapshots:
                        continue
                    
                    is_huge = False
                    huge_total = 0
                    for j in range(len(big_snapshots) - 1):
                        if big_snapshots[j+1]['index'] - big_snapshots[j]['index'] == 1:
                            is_huge = True
                            huge_total = big_snapshots[j]['incoming'] + big_snapshots[j+1]['incoming']
                            break
                    
                    max_snap = max(big_snapshots, key=lambda s: s['incoming'])
                    selection_total = parse_volume(history[-1].get(amount_key, 0))
                    trigger_at = max_snap.get('scrapedat', now_turkey_iso())
                    
                    alarm = {
                        'home': home,
                        'away': away,
                        'market': market_names.get(market, market),
                        'selection': selection,
                        'incoming_money': max_snap['incoming'],
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
        
        if alarms:
            new_count = self._upsert_alarms('bigmoney_alarms', alarms, ['home', 'away', 'market', 'selection'])
            log(f"BigMoney: {new_count} new alarms added")
        
        return len(alarms)
    
    def calculate_volumeshock_alarms(self) -> int:
        """Calculate Volume Shock alarms"""
        config = self.configs.get('volumeshock', self._default_configs()['volumeshock'])
        shock_mult = config.get('volume_shock_multiplier', 3.0)
        min_hours = config.get('min_hours_to_kickoff', 2)
        
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
                    
                    prev_amts = [parse_volume(history[i].get(amount_key, 0)) - 
                                parse_volume(history[i-1].get(amount_key, 0))
                                for i in range(-5, -1)]
                    prev_amts = [a for a in prev_amts if a > 0]
                    
                    if not prev_amts:
                        continue
                    
                    avg_prev = sum(prev_amts) / len(prev_amts)
                    shock_value = incoming / avg_prev if avg_prev > 0 else 0
                    
                    if shock_value >= shock_mult:
                        trigger_at = history[-1].get('scrapedat', now_turkey_iso())
                        
                        alarm = {
                            'home': home,
                            'away': away,
                            'market': market_names.get(market, market),
                            'selection': selection,
                            'volume_shock_value': round(shock_value, 2),
                            'incoming_money': incoming,
                            'avg_previous': round(avg_prev, 0),
                            'match_date': match.get('date', ''),
                            'event_time': trigger_at,
                            'trigger_at': trigger_at,
                            'created_at': now_turkey_iso(),
                            'alarm_type': 'volumeshock'
                        }
                        alarms.append(alarm)
        
        if alarms:
            new_count = self._upsert_alarms('volumeshock_alarms', alarms, ['home', 'away', 'market', 'selection'])
            log(f"VolumeShock: {new_count} new alarms added")
        
        return len(alarms)
    
    def calculate_dropping_alarms(self) -> int:
        """Calculate Dropping Odds alarms"""
        config = self.configs.get('dropping', self._default_configs()['dropping'])
        l1_min = config.get('min_drop_l1', 7)
        l1_max = config.get('max_drop_l1', 10)
        l2_min = config.get('min_drop_l2', 10)
        l2_max = config.get('max_drop_l2', 15)
        l3_min = config.get('min_drop_l3', 15)
        
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
                    
                    alarm = {
                        'home': home,
                        'away': away,
                        'market': market_names.get(market, market),
                        'selection': selection,
                        'opening_odds': opening_odds,
                        'current_odds': current_odds,
                        'drop_pct': round(drop_pct, 2),
                        'level': level,
                        'match_date': match.get('date', ''),
                        'event_time': trigger_at,
                        'trigger_at': trigger_at,
                        'created_at': now_turkey_iso(),
                        'alarm_type': 'dropping'
                    }
                    alarms.append(alarm)
        
        if alarms:
            new_count = self._upsert_alarms('dropping_alarms', alarms, ['home', 'away', 'market', 'selection'])
            log(f"Dropping: {new_count} new alarms added")
        
        return len(alarms)
    
    def calculate_publictrap_alarms(self) -> int:
        """Calculate Public Trap (Halk Tuzagi) alarms - same logic as Sharp"""
        config = self.configs.get('publictrap', self._default_configs()['publictrap'])
        min_score = config.get('min_sharp_score', 20)
        
        alarms = []
        markets = ['moneyway_1x2', 'moneyway_ou25', 'moneyway_btts']
        market_names = {'moneyway_1x2': '1X2', 'moneyway_ou25': 'O/U 2.5', 'moneyway_btts': 'BTTS'}
        
        for market in markets:
            if '1x2' in market:
                min_volume = config.get('min_volume_1x2', 5000)
                selections = ['1', 'X', '2']
                odds_keys = ['odds1', 'oddsx', 'odds2']
                amount_keys = ['amt1', 'amtx', 'amt2']
                pct_keys = ['pct1', 'pctx', 'pct2']
            elif 'ou25' in market:
                min_volume = config.get('min_volume_ou25', 2000)
                selections = ['Over', 'Under']
                odds_keys = ['over', 'under']
                amount_keys = ['amtover', 'amtunder']
                pct_keys = ['pctover', 'pctunder']
            else:
                min_volume = config.get('min_volume_btts', 1000)
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
                    
                    current_pct = parse_float(latest.get(pct_key, 0))
                    prev_pct = parse_float(prev.get(pct_key, 0))
                    
                    if current_odds <= 0 or prev_odds <= 0:
                        continue
                    
                    volume_change = current_amount - prev_amount
                    if volume_change <= 0:
                        continue
                    
                    odds_drop = prev_odds - current_odds
                    if odds_drop <= 0:
                        continue
                    
                    share_change = current_pct - prev_pct
                    
                    trap_score = (volume_change / 500) + (odds_drop / 0.05) * 3 + share_change
                    
                    if trap_score >= min_score:
                        trigger_at = latest.get('scrapedat', now_turkey_iso())
                        
                        alarm = {
                            'home': home,
                            'away': away,
                            'market': market_names.get(market, market),
                            'selection': selection,
                            'trap_score': round(trap_score, 2),
                            'volume': volume_change,
                            'odds_drop': odds_drop,
                            'share_change': share_change,
                            'match_date': match.get('date', ''),
                            'event_time': trigger_at,
                            'trigger_at': trigger_at,
                            'created_at': now_turkey_iso(),
                            'alarm_type': 'publictrap'
                        }
                        alarms.append(alarm)
        
        if alarms:
            new_count = self._upsert_alarms('halktuzagi_alarms', alarms, ['home', 'away', 'market', 'selection'])
            log(f"PublicTrap: {new_count} new alarms added")
        
        return len(alarms)
    
    def calculate_volumeleader_alarms(self) -> int:
        """Calculate Volume Leader Changed alarms"""
        config = self.configs.get('volumeleader', self._default_configs()['volumeleader'])
        threshold = config.get('leader_threshold', 50)
        
        alarms = []
        markets = ['moneyway_1x2', 'moneyway_ou25', 'moneyway_btts']
        market_names = {'moneyway_1x2': '1X2', 'moneyway_ou25': 'O/U 2.5', 'moneyway_btts': 'BTTS'}
        
        for market in markets:
            if '1x2' in market:
                min_volume = config.get('min_volume_1x2', 5000)
                selections = ['1', 'X', '2']
                amount_keys = ['amt1', 'amtx', 'amt2']
            elif 'ou25' in market:
                min_volume = config.get('min_volume_ou25', 2000)
                selections = ['Over', 'Under']
                amount_keys = ['amtover', 'amtunder']
            else:
                min_volume = config.get('min_volume_btts', 1000)
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
                        trigger_at = curr_snap.get('scrapedat', now_turkey_iso())
                        trigger_volume = curr_total
                        
                        alarm = {
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
                self._post('volume_leader_alarms', new_alarms)
        
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
