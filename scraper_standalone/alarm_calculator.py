"""
SmartXFlow Alarm Calculator Module v1.25
Standalone alarm calculation for PC-based scraper
Calculates: Sharp, Insider, BigMoney, VolumeShock, Dropping, VolumeLeader, MIM
OPTIMIZED: Batch fetch per market, in-memory calculations
DEFAULT_SETTINGS: Fallback values for all alarm types when Supabase config missing
PHASE 2: match_id_hash contract compliant (league|kickoff|home|away)
TELEGRAM: Integrated notification system for new alarms
"""

import json
import os
import hashlib
import time
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
    Rules:
    1. trim (strip leading/trailing whitespace)
    2. Turkish character normalization BEFORE lowercase:
       - i (dotless) -> i, I (dotted) -> I
       - s (cedilla) -> s, S (cedilla) -> S
       - g (breve) -> g, G (breve) -> G
       - u (umlaut) -> u, U (umlaut) -> U
       - o (umlaut) -> o, O (umlaut) -> O
       - c (cedilla) -> c, C (cedilla) -> C
    3. lowercase
    4. remove punctuation (keep alphanumeric + space)
    5. remove team suffixes: fc, fk, sk, sc, afc, cf, ac, as (word boundary)
    6. collapse multiple spaces to single space
    """
    if not value:
        return ""
    value = str(value).strip()
    
    # Turkish character normalization (BEFORE lowercase)
    tr_map = {
        'ı': 'i', 'İ': 'I',
        'ş': 's', 'Ş': 'S',
        'ğ': 'g', 'Ğ': 'G',
        'ü': 'u', 'Ü': 'U',
        'ö': 'o', 'Ö': 'O',
        'ç': 'c', 'Ç': 'C'
    }
    for tr_char, en_char in tr_map.items():
        value = value.replace(tr_char, en_char)
    
    value = value.lower()
    
    # Remove special characters (keep only lowercase letters, digits, space)
    # MUST match core/hash_utils.py regex exactly
    import re
    value = re.sub(r'[^a-z0-9\s]', '', value)
    value = ' '.join(value.split())
    
    # Remove team suffixes ONLY at end of string (core/hash_utils.py ile UYUMLU)
    # Suffixes: fc, fk, sk, sc, afc, cf, ac, as
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


def make_match_id_hash(home: str, away: str, league: str, kickoff_utc: str = None, debug: bool = False) -> str:
    """
    SINGLE SOURCE OF TRUTH: Generate unique 12-character match ID hash.
    
    Input Format (IMMUTABLE):
        "{league_norm}|{home_norm}|{away_norm}"
    
    NOTE: kickoff_utc parametresi geriye uyumluluk icin tutuldu ama KULLANILMIYOR.
    Hash sadece league, home, away bilgilerine gore uretilir.
    
    Args:
        home: Home team name
        away: Away team name  
        league: League name (or league_id)
        kickoff_utc: DEPRECATED - Geriye uyumluluk icin tutuldu, KULLANILMIYOR
        debug: If True, logs input and output for verification
    
    Returns:
        12-character MD5 hash
    """
    home_norm = normalize_field(home)
    away_norm = normalize_field(away)
    league_norm = normalize_field(league)
    
    canonical = f"{league_norm}|{home_norm}|{away_norm}"
    
    match_id_hash = hashlib.md5(canonical.encode('utf-8')).hexdigest()[:12]
    
    if debug:
        log(f"[HASH DEBUG] Input: home='{home}', away='{away}', league='{league}'")
        log(f"[HASH DEBUG] Normalized: home_norm='{home_norm}', away_norm='{away_norm}', league_norm='{league_norm}'")
        log(f"[HASH DEBUG] Canonical: '{canonical}'")
        log(f"[HASH DEBUG] Hash: '{match_id_hash}'")
    
    return match_id_hash


def generate_match_id_hash(home: str, away: str, league: str, kickoff: str = None) -> str:
    """DEPRECATED: Use make_match_id_hash() instead. kickoff parametresi KULLANILMIYOR."""
    return make_match_id_hash(home, away, league, kickoff)


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


def normalize_date_for_db(date_str: str) -> str:
    """
    Tüm tarih formatlarını PostgreSQL DATE formatına (YYYY-MM-DD) çevir.
    
    Desteklenen giriş formatları:
    - "18.Dec 09:00:00" -> "2025-12-18"
    - "18.Dec" -> "2025-12-18"
    - "2025-12-18T09:00:00" -> "2025-12-18"
    - "2025-12-18" -> "2025-12-18"
    - "18.12.2025" -> "2025-12-18"
    
    Returns:
        PostgreSQL DATE format (YYYY-MM-DD) veya boş string
    """
    if not date_str:
        return ""
    
    date_str = str(date_str).strip()
    
    try:
        today = now_turkey().date()
        
        if 'T' in date_str and '-' in date_str:
            return date_str.split('T')[0]
        
        if date_str.count('-') == 2 and len(date_str) >= 10:
            return date_str[:10]
        
        date_part = date_str.split()[0]
        
        if '.' in date_part:
            parts = date_part.split('.')
            if len(parts) == 2:
                day = int(parts[0])
                month_abbr = parts[1][:3]
                month_map = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                            'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12}
                month = month_map.get(month_abbr)
                if month:
                    year = today.year
                    if month < today.month - 6:
                        year += 1
                    return f"{year}-{month:02d}-{day:02d}"
            elif len(parts) == 3:
                day = int(parts[0])
                month = int(parts[1])
                year = int(parts[2])
                if year < 100:
                    year += 2000
                return f"{year}-{month:02d}-{day:02d}"
    except Exception as e:
        pass
    
    return ""


class AlarmCalculator:
    """Supabase-based alarm calculator - OPTIMIZED with batch fetch"""
    
    def __init__(self, supabase_url: str, supabase_key: str, logger_callback: Optional[Callable[[str], None]] = None):
        self.url = supabase_url
        self.key = supabase_key
        self.configs = {}
        self._history_cache = {}
        self._matches_cache = {}
        self._telegram_settings = None
        self._telegram_sent_cache = {}
        if logger_callback:
            set_logger(logger_callback)
        self.load_configs()
        self._load_telegram_settings()
    
    def _load_telegram_settings(self):
        """Load Telegram settings from Supabase"""
        try:
            settings = self._get('telegram_settings', 'select=*')
            if settings:
                self._telegram_settings = {}
                for row in settings:
                    key = row['setting_key']
                    value = row['setting_value']
                    if isinstance(value, bool):
                        value = 'true' if value else 'false'
                    elif str(value).lower() in ('true', 'false'):
                        value = str(value).lower()
                    self._telegram_settings[key] = value
                env_token = os.environ.get('TELEGRAM_BOT_TOKEN') or os.environ.get('TELEGRAM_TOKEN')
                env_chat_id = os.environ.get('TELEGRAM_CHAT_ID')
                log(f"[Telegram] Settings loaded: enabled={self._telegram_settings.get('telegram_enabled', 'false')}")
                log(f"[Telegram] Env credentials: Token={'SET' if env_token else 'NOT SET'}, ChatID={'SET' if env_chat_id else 'NOT SET'}")
            else:
                self._telegram_settings = {'telegram_enabled': 'false'}
                log("[Telegram] No settings found in Supabase")
        except Exception as e:
            log(f"[Telegram] Settings load error: {e}")
            self._telegram_settings = {'telegram_enabled': 'false'}
    
    def _normalize_alarm_type(self, alarm_type: str) -> str:
        """Normalize alarm type for consistent comparison
        Converts: volume_shock_alarms -> VOLUMESHOCK
                  big_money_alarms -> BIGMONEY
                  Big Money -> BIGMONEY
                  Volume Shock -> VOLUMESHOCK
        """
        normalized = alarm_type.upper()
        normalized = normalized.replace('_ALARMS', '')
        normalized = normalized.replace('_', '')
        normalized = normalized.replace(' ', '')
        normalized = normalized.replace('-', '')
        return normalized
    
    def _is_telegram_enabled(self, alarm_type: str) -> bool:
        """Check if Telegram is enabled for this alarm type"""
        if not self._telegram_settings:
            return False
        enabled_val = self._telegram_settings.get('telegram_enabled', 'false')
        if isinstance(enabled_val, bool):
            enabled_val = 'true' if enabled_val else 'false'
        if str(enabled_val).lower() != 'true':
            return False
        try:
            enabled_types = json.loads(self._telegram_settings.get('telegram_alarm_types', '[]'))
            normalized_alarm = self._normalize_alarm_type(alarm_type)
            normalized_enabled = [self._normalize_alarm_type(t) for t in enabled_types]
            return normalized_alarm in normalized_enabled
        except:
            return False
    
    def _check_dedupe(self, alarm: Dict, alarm_type: str) -> tuple:
        """Check if alarm was already sent, returns (should_send, is_retrigger, delta)"""
        # CRITICAL: Always use match_id_hash for consistent deduplication
        match_id_hash = alarm.get('match_id_hash', '')
        market = alarm.get('market', '')
        selection = alarm.get('selection', '')
        normalized_type = self._normalize_alarm_type(alarm_type)
        dedupe_key = f"{match_id_hash}|{normalized_type}|{market}|{selection}"
        
        try:
            existing = self._get('telegram_sent_log', f'dedupe_key=eq.{dedupe_key}&select=*')
            if not existing or len(existing) == 0:
                return True, False, 0
            
            last_record = existing[0]
            last_delta = float(last_record.get('last_delta', 0))
            last_sent = last_record.get('last_sent_at', '')
            
            if normalized_type == 'BIGMONEY':
                settings = self._telegram_settings or {}
                retrigger_enabled = settings.get('big_money_retrigger_enabled', 'true') == 'true'
                if not retrigger_enabled:
                    return False, False, 0
                
                min_delta = float(settings.get('big_money_retrigger_min_delta', 500))
                cooldown_min = int(settings.get('big_money_retrigger_cooldown_min', 10))
                
                current_delta = float(alarm.get('delta', 0) or alarm.get('money_in', 0) or 0)
                new_delta = current_delta - last_delta
                
                if new_delta >= min_delta:
                    try:
                        from datetime import datetime, timezone
                        if last_sent:
                            last_time = datetime.fromisoformat(last_sent.replace('Z', '+00:00'))
                            now = datetime.now(timezone.utc)
                            elapsed_min = (now - last_time).total_seconds() / 60
                            if elapsed_min >= cooldown_min:
                                return True, True, new_delta
                    except:
                        return True, True, new_delta
                return False, False, 0
            
            if normalized_type == 'VOLUMESHOCK':
                settings = self._telegram_settings or {}
                
                # Shock değeri kontrolü - aynı değerse gönderme
                current_shock = float(alarm.get('volume_shock_value', 0) or alarm.get('volume_shock', 0) or 0)
                
                # Eğer shock değeri değişmediyse (veya çok az değiştiyse) gönderme
                # min_shock_delta: yeni alarm için gereken minimum shock farkı (örn: 0.5 = 0.5x artış)
                min_shock_delta = float(settings.get('volumeshock_min_shock_delta', 0.5))
                
                shock_diff = current_shock - last_delta
                
                if shock_diff < min_shock_delta:
                    log(f"[Telegram] VolumeShock değer değişmedi - gönderilmeyecek (mevcut: {current_shock:.2f}x, önceki: {last_delta:.2f}x, fark: {shock_diff:.2f}x < min: {min_shock_delta})")
                    return False, False, 0
                
                # Shock değeri yeterince değiştiyse, cooldown kontrolü yap
                cooldown_min = int(settings.get('volumeshock_cooldown_min', 10))
                
                try:
                    from datetime import datetime, timezone
                    if last_sent:
                        last_time = datetime.fromisoformat(last_sent.replace('Z', '+00:00'))
                        now = datetime.now(timezone.utc)
                        elapsed_min = (now - last_time).total_seconds() / 60
                        if elapsed_min >= cooldown_min:
                            log(f"[Telegram] VolumeShock YENİ DEĞER - gönderilecek ({current_shock:.2f}x vs {last_delta:.2f}x, fark: {shock_diff:.2f}x)")
                            return True, True, current_shock
                        else:
                            log(f"[Telegram] VolumeShock cooldown bekliyor ({elapsed_min:.0f} min < {cooldown_min} min)")
                            return False, False, 0
                    else:
                        log(f"[Telegram] VolumeShock YENİ DEĞER - gönderilecek ({current_shock:.2f}x)")
                        return True, True, current_shock
                except Exception as e:
                    log(f"[Telegram] VolumeShock error: {e}")
                    return False, False, 0
                return False, False, 0
            
            return False, False, 0
        except Exception as e:
            log(f"[Telegram] Dedupe check error: {e}")
            return True, False, 0
    
    def _format_bigmoney_telegram(self, alarm: Dict, home: str, away: str, market: str, selection: str, timestamp: str, is_retrigger: bool = False) -> str:
        """Format BigMoney alarm for Telegram"""
        retrigger_text = " (RETRIGGER)" if is_retrigger else ""
        incoming = float(alarm.get('incoming_money', 0) or alarm.get('delta', 0) or alarm.get('money_in', 0) or 0)
        total = float(alarm.get('selection_total', 0) or alarm.get('total_volume', 0) or 0)
        
        match_date = alarm.get('match_date', '')
        kickoff = alarm.get('kickoff', alarm.get('kickoff_utc', ''))
        if kickoff:
            try:
                from datetime import datetime
                if 'T' in str(kickoff):
                    dt = datetime.fromisoformat(str(kickoff).replace('Z', '+00:00'))
                    match_date_str = dt.strftime('%d %b - %H:%M')
                else:
                    match_date_str = str(kickoff)[:16]
            except:
                match_date_str = str(match_date) if match_date else ''
        else:
            match_date_str = str(match_date) if match_date else ''
        
        history = alarm.get('alarm_history', [])
        if isinstance(history, str):
            try:
                history = json.loads(history)
            except:
                history = []
        
        trigger_count = len(history) + 1
        
        lines = [
            f"[BIG MONEY]{retrigger_text} - {market}-{selection} secenegine yuksek para girisi oldu",
            f"Zaman: {timestamp}",
            "",
            f"<b>{home}</b> vs <b>{away}</b>",
            "",
            f"> {selection}: GBP {incoming:,.0f}",
            f"> Toplam: GBP {total:,.0f}",
        ]
        
        if match_date_str:
            lines.append("")
            lines.append(f"Mac: {match_date_str}")
        
        if history and len(history) > 0:
            lines.append("")
            lines.append("Onceki:")
            for h in history[:3]:
                h_time = h.get('trigger_at', '')[:16].replace('T', ' ').replace('-', '.') if h.get('trigger_at') else ''
                h_money = float(h.get('incoming_money', 0) or 0)
                if h_time and h_money > 0:
                    lines.append(f"  - {h_time} = GBP {h_money:,.0f}")
        
        if trigger_count > 1:
            lines.append("")
            lines.append(f"x{trigger_count} tetikleme")
        
        vol1 = parse_volume(alarm.get('amt1') or alarm.get('vol_1', 0))
        volx = parse_volume(alarm.get('amtx') or alarm.get('vol_x', 0))
        vol2 = parse_volume(alarm.get('amt2') or alarm.get('vol_2', 0))
        total_vol = vol1 + volx + vol2
        
        if total_vol > 0:
            pct1 = (vol1 / total_vol * 100) if total_vol > 0 else 0
            pctx = (volx / total_vol * 100) if total_vol > 0 else 0
            pct2 = (vol2 / total_vol * 100) if total_vol > 0 else 0
            lines.append("")
            lines.append("----------------")
            lines.append("Hacimler:")
            lines.append(f"  1: GBP {vol1:,.0f} ({pct1:.0f}%)")
            lines.append(f"  X: GBP {volx:,.0f} ({pctx:.0f}%)")
            lines.append(f"  2: GBP {vol2:,.0f} ({pct2:.0f}%)")
            lines.append(f"  Total: GBP {total_vol:,.0f}")
        
        return "\n".join(lines)
    
    def _format_volumeshock_telegram(self, alarm: Dict, home: str, away: str, market: str, selection: str, timestamp: str) -> str:
        """Format VolumeShock alarm for Telegram"""
        prev_vol = float(alarm.get('avg_previous', 0) or alarm.get('prev_volume', 0) or 0)
        incoming = float(alarm.get('incoming_money', 0) or alarm.get('current_volume', 0) or 0)
        curr_vol = prev_vol + incoming
        multiplier = float(alarm.get('volume_shock_value', 0) or alarm.get('multiplier', 0) or 0)
        
        if multiplier == 0 and prev_vol > 0:
            multiplier = incoming / prev_vol
        
        match_date = alarm.get('match_date', '')
        kickoff = alarm.get('kickoff', alarm.get('kickoff_utc', ''))
        if kickoff:
            try:
                from datetime import datetime
                if 'T' in str(kickoff):
                    dt = datetime.fromisoformat(str(kickoff).replace('Z', '+00:00'))
                    match_date_str = dt.strftime('%d %b \u2022 %H:%M')
                else:
                    match_date_str = str(kickoff)[:16]
            except:
                match_date_str = str(match_date) if match_date else ''
        else:
            match_date_str = str(match_date) if match_date else ''
        
        lines = [
            "\U0001F4CA <b>VOLUME SHOCK</b> \u2014 " + f"{market}-{selection}'de ani hacim artisi tespit edildi",
            "\U0001F551 " + timestamp,
            "",
            "\u26BD <b>" + home + "</b> vs <b>" + away + "</b>",
            "",
            "\U0001F4CA " + f"{selection}: \u00A3{prev_vol:,.0f} \u2192 \u00A3{curr_vol:,.0f}",
            "\U0001F525 " + f"{multiplier:.1f}x artis (10 dk icinde)",
        ]
        
        if match_date_str:
            lines.append("")
            lines.append("\U0001F4C5 Mac: " + match_date_str)
        
        vol1 = parse_volume(alarm.get('amt1') or alarm.get('vol_1', 0))
        volx = parse_volume(alarm.get('amtx') or alarm.get('vol_x', 0))
        vol2 = parse_volume(alarm.get('amt2') or alarm.get('vol_2', 0))
        total_vol = vol1 + volx + vol2
        
        if total_vol > 0:
            pct1 = (vol1 / total_vol * 100) if total_vol > 0 else 0
            pctx = (volx / total_vol * 100) if total_vol > 0 else 0
            pct2 = (vol2 / total_vol * 100) if total_vol > 0 else 0
            lines.append("")
            lines.append("\u2501" * 18)
            lines.append("\U0001F4CA Mevcut Hacimler:")
            lines.append(f"  1: \u00A3{vol1:,.0f} ({pct1:.0f}%)")
            lines.append(f"  X: \u00A3{volx:,.0f} ({pctx:.0f}%)")
            lines.append(f"  2: \u00A3{vol2:,.0f} ({pct2:.0f}%)")
            lines.append(f"  Total: \u00A3{total_vol:,.0f}")
        
        return "\n".join(lines)
    
    def _format_dropping_telegram(self, alarm: Dict, home: str, away: str, market: str, selection: str, timestamp: str) -> str:
        """Format Dropping alarm for Telegram"""
        old_odds = float(alarm.get('opening_odds', 0) or alarm.get('old_odds', 0) or 0)
        new_odds = float(alarm.get('current_odds', 0) or alarm.get('new_odds', 0) or 0)
        drop_pct = float(alarm.get('drop_pct', 0) or 0)
        
        lines = [
            f"[DROPPING ODDS] - {market}-{selection}'de oran dususu",
            f"Zaman: {timestamp}",
            "",
            f"<b>{home}</b> vs <b>{away}</b>",
            "",
            f"> Oran: {old_odds:.2f} -> {new_odds:.2f} ({drop_pct:.1f}% dusus)",
        ]
        
        return "\n".join(lines)
    
    def _format_sharp_telegram(self, alarm: Dict, home: str, away: str, market: str, selection: str, timestamp: str) -> str:
        """Format Sharp alarm for Telegram"""
        level = alarm.get('level', '')
        delta = float(alarm.get('delta', 0) or alarm.get('money_in', 0) or 0)
        
        lines = [
            f"[SHARP] ({level}) - {market}-{selection}'de keskin hareket",
            f"Zaman: {timestamp}",
            "",
            f"<b>{home}</b> vs <b>{away}</b>",
            "",
            f"> Para Girisi: GBP {delta:,.0f}",
        ]
        
        return "\n".join(lines)
    
    def _format_insider_telegram(self, alarm: Dict, home: str, away: str, market: str, selection: str, timestamp: str) -> str:
        """Format Insider alarm for Telegram"""
        level = alarm.get('level', '')
        delta = float(alarm.get('delta', 0) or alarm.get('money_in', 0) or 0)
        
        lines = [
            f"[INSIDER] ({level}) - {market}-{selection}'de supeli hareket",
            f"Zaman: {timestamp}",
            "",
            f"<b>{home}</b> vs <b>{away}</b>",
            "",
            f"> Para Girisi: GBP {delta:,.0f}",
        ]
        
        return "\n".join(lines)
    
    def _format_volumeleader_telegram(self, alarm: Dict, home: str, away: str, market: str, selection: str, timestamp: str) -> str:
        """Format VolumeLeader alarm for Telegram"""
        share = float(alarm.get('share', 0) or alarm.get('current_share', 0) or 0)
        volume = float(alarm.get('volume', 0) or alarm.get('current_volume', 0) or 0)
        
        lines = [
            f"[VOLUME LEADER] - {market}-{selection} hacim lideri",
            f"Zaman: {timestamp}",
            "",
            f"<b>{home}</b> vs <b>{away}</b>",
            "",
            f"> Pay: {share:.1f}%",
            f"> Hacim: GBP {volume:,.0f}",
        ]
        
        return "\n".join(lines)
    
    def _format_mim_telegram(self, alarm: Dict, home: str, away: str, market: str, selection: str, timestamp: str) -> str:
        """Format MIM alarm for Telegram"""
        impact = float(alarm.get('impact', 0) or alarm.get('market_impact', 0) or 0)
        
        lines = [
            f"[MIM] - {market}-{selection}'de piyasa etkisi",
            f"Zaman: {timestamp}",
            "",
            f"<b>{home}</b> vs <b>{away}</b>",
            "",
            f"> Etki: {impact:.2f}",
        ]
        
        return "\n".join(lines)
    
    def _format_default_telegram(self, alarm: Dict, alarm_type: str, home: str, away: str, market: str, selection: str, timestamp: str) -> str:
        """Format default alarm for Telegram"""
        lines = [
            f"[{alarm_type.upper()}]",
            f"Zaman: {timestamp}",
            "",
            f"<b>{home}</b> vs <b>{away}</b>",
            f"> Market: {market} / {selection}",
        ]
        
        return "\n".join(lines)
    
    def _log_telegram_sent(self, alarm: Dict, alarm_type: str, delta: float = 0):
        """Log sent notification to Supabase for deduplication"""
        try:
            # CRITICAL: Always use match_id_hash for consistent deduplication
            match_id_hash = alarm.get('match_id_hash', '')
            market = alarm.get('market', '')
            selection = alarm.get('selection', '')
            normalized_type = self._normalize_alarm_type(alarm_type)
            dedupe_key = f"{match_id_hash}|{normalized_type}|{market}|{selection}"
            
            payload = [{
                'dedupe_key': dedupe_key,
                'match_id_hash': match_id_hash[:12] if match_id_hash else '',
                'alarm_type': normalized_type,
                'market': market,
                'selection': selection,
                'last_sent_at': now_turkey_iso(),
                'last_delta': delta,
                'send_count': 1
            }]
            
            self._post('telegram_sent_log', payload, on_conflict='dedupe_key')
        except Exception as e:
            log(f"[Telegram] Log sent error: {e}")
    
    def _send_telegram_notification(self, alarm: Dict, alarm_type: str, is_retrigger: bool = False, delta: float = 0):
        """Send Telegram notification for an alarm"""
        try:
            token = os.environ.get('TELEGRAM_BOT_TOKEN') or os.environ.get('TELEGRAM_TOKEN')
            chat_id = os.environ.get('TELEGRAM_CHAT_ID')
            
            if not token or not chat_id:
                log(f"[Telegram] CREDENTIALS MISSING - Token: {'SET' if token else 'NOT SET'}, ChatID: {'SET' if chat_id else 'NOT SET'}")
                return False
            
            home = alarm.get('home', alarm.get('home_team', ''))
            away = alarm.get('away', alarm.get('away_team', ''))
            market = alarm.get('market', '')
            selection = alarm.get('selection', '')
            
            now = now_turkey()
            timestamp = now.strftime('%d.%m - %H:%M')
            
            normalized_type = self._normalize_alarm_type(alarm_type)
            
            if normalized_type == 'BIGMONEY':
                text = self._format_bigmoney_telegram(alarm, home, away, market, selection, timestamp, is_retrigger)
            elif normalized_type == 'VOLUMESHOCK':
                text = self._format_volumeshock_telegram(alarm, home, away, market, selection, timestamp)
            elif normalized_type == 'DROPPING':
                text = self._format_dropping_telegram(alarm, home, away, market, selection, timestamp)
            elif normalized_type == 'SHARP':
                text = self._format_sharp_telegram(alarm, home, away, market, selection, timestamp)
            elif normalized_type == 'INSIDER':
                text = self._format_insider_telegram(alarm, home, away, market, selection, timestamp)
            elif normalized_type == 'VOLUMELEADER':
                text = self._format_volumeleader_telegram(alarm, home, away, market, selection, timestamp)
            elif normalized_type == 'MIM':
                text = self._format_mim_telegram(alarm, home, away, market, selection, timestamp)
            else:
                text = self._format_default_telegram(alarm, alarm_type, home, away, market, selection, timestamp)
            
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": text,
                "disable_web_page_preview": True,
                "parse_mode": "HTML"
            }
            
            for attempt in range(3):
                try:
                    if hasattr(httpx, 'post'):
                        resp = httpx.post(url, json=payload, timeout=30)
                    else:
                        import requests as req
                        resp = req.post(url, json=payload, timeout=30)
                    
                    if resp.status_code == 200:
                        log(f"[Telegram] Sent: {alarm_type} - {home} vs {away}")
                        return True
                    elif resp.status_code == 429:
                        retry_after = 5
                        try:
                            retry_after = resp.json().get('parameters', {}).get('retry_after', 5)
                        except:
                            pass
                        log(f"[Telegram] Rate limited, waiting {retry_after}s...")
                        time.sleep(retry_after)
                    else:
                        log(f"[Telegram] Send failed: HTTP {resp.status_code}")
                        return False
                except Exception as e:
                    log(f"[Telegram] Send error attempt {attempt+1}: {e}")
                    time.sleep(2)
            
            return False
        except Exception as e:
            log(f"[Telegram] Notification error: {e}")
            return False
    
    def _notify_new_alarms(self, alarms: List[Dict], alarm_type: str, existing_keys: set, updated_keys: set = None):
        """Send Telegram notifications for new alarms and updated alarms (BigMoney/VolumeShock refresh)
        
        Args:
            alarms: List of alarms to check
            alarm_type: Table name (e.g., 'bigmoney_alarms')
            existing_keys: Keys that already exist in DB (existing alarms)
            updated_keys: Keys that have updated trigger_at (refreshed alarms - BigMoney/VolumeShock)
        """
        if not self._is_telegram_enabled(alarm_type):
            return
        
        if updated_keys is None:
            updated_keys = set()
        
        alarm_type_clean = alarm_type.replace('_alarms', '').upper()
        sent_count = 0
        
        for alarm in alarms:
            # CRITICAL: Always use match_id_hash for deduplication key
            # existing_keys uses match_id_hash from key_fields, so we must match
            key_parts = [
                str(alarm.get('match_id_hash', '')),
                str(alarm.get('market', '')),
                str(alarm.get('selection', ''))
            ]
            key = '|'.join(key_parts)
            
            is_new = key not in existing_keys
            is_refreshed = key in updated_keys
            
            # For refreshed alarms (BigMoney/VolumeShock with new trigger_at), still check dedupe
            # to prevent duplicate Telegram messages
            if is_refreshed:
                should_send, is_retrigger, delta = self._check_dedupe(alarm, alarm_type_clean)
                if should_send:
                    log(f"[Telegram] Refreshed alarm detected: {alarm_type_clean} - sending notification")
                    if self._send_telegram_notification(alarm, alarm_type_clean, is_retrigger, delta):
                        # VolumeShock için shock değerini, diğerleri için para değerini kaydet
                        if alarm_type_clean == 'VOLUMESHOCK':
                            current_delta = float(alarm.get('volume_shock_value', 0) or alarm.get('volume_shock', 0) or 0)
                        else:
                            current_delta = float(alarm.get('delta', 0) or alarm.get('money_in', 0) or alarm.get('incoming_money', 0) or 0)
                        self._log_telegram_sent(alarm, alarm_type_clean, current_delta)
                        sent_count += 1
                        time.sleep(0.5)
            elif is_new:
                # Normal new alarm - check dedupe
                should_send, is_retrigger, delta = self._check_dedupe(alarm, alarm_type_clean)
                if should_send:
                    if self._send_telegram_notification(alarm, alarm_type_clean, is_retrigger, delta):
                        # VolumeShock için shock değerini, diğerleri için para değerini kaydet
                        if alarm_type_clean == 'VOLUMESHOCK':
                            current_delta = float(alarm.get('volume_shock_value', 0) or alarm.get('volume_shock', 0) or 0)
                        else:
                            current_delta = float(alarm.get('delta', 0) or alarm.get('money_in', 0) or 0)
                        self._log_telegram_sent(alarm, alarm_type_clean, current_delta)
                        sent_count += 1
                        time.sleep(0.5)
        
        if sent_count > 0:
            log(f"[Telegram] Sent {sent_count} notifications for {alarm_type_clean}")
    
    def _headers(self) -> Dict[str, str]:
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
    
    def _rest_url(self, table: str) -> str:
        return f"{self.url}/rest/v1/{table}"
    
    def _reload_schema_cache(self) -> bool:
        """Supabase PostgREST schema cache'ini yenile"""
        try:
            url = f"{self.url}/rest/v1/rpc/reload_schema_cache"
            headers = self._headers()
            resp = httpx.post(url, headers=headers, json={}, timeout=30)
            if resp.status_code in [200, 204]:
                log("[SCHEMA] PostgREST schema cache reloaded successfully")
                return True
            else:
                log(f"[SCHEMA] Reload failed: HTTP {resp.status_code} - {resp.text[:200]}")
                return False
        except Exception as e:
            log(f"[SCHEMA] Reload error: {e}")
            return False
    
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
    
    # PostgREST schema cache sorunu workaround: her tablo için bilinen kolonlar
    # Supabase tablo şemasına göre güncellenmiş (2025-12-18)
    # match_id_hash kullanılıyor, match_id değil!
    KNOWN_COLUMNS = {
        'bigmoney_alarms': ['id', 'match_id_hash', 'home', 'away', 'league', 'market', 
                           'selection', 'incoming_money', 'total_selection', 'is_huge',
                           'match_date', 'trigger_at', 'created_at', 'alarm_history'],
        'volumeshock_alarms': ['id', 'match_id_hash', 'home', 'away', 'league', 'market', 
                              'selection', 'volume_shock_value', 'incoming_money',
                              'match_date', 'trigger_at', 'created_at', 'alarm_history'],
        'insider_alarms': ['id', 'match_id_hash', 'home', 'away', 'league', 'market', 
                          'selection', 'opening_odds', 'current_odds', 'drop_pct',
                          'total_money', 'match_date', 'alarm_history', 'trigger_at', 'created_at'],
        'sharp_alarms': ['id', 'match_id_hash', 'home', 'away', 'league', 'market', 
                        'selection', 'sharp_score', 'amount_change', 'drop_pct', 
                        'share_diff', 'match_date', 'trigger_at', 'created_at',
                        'volume_contrib', 'odds_contrib', 'share_contrib',
                        'previous_odds', 'current_odds', 'previous_share', 'current_share',
                        'avg_last_amounts', 'shock_raw', 'shock_value', 'max_volume_cap',
                        'volume_multiplier', 'odds_multiplier', 'odds_multiplier_base', 
                        'odds_multiplier_bucket', 'odds_value', 'max_odds_cap',
                        'share_multiplier', 'share_value', 'max_share_cap', 'alarm_type'],
        'volume_leader_alarms': ['id', 'match_id_hash', 'home', 'away', 'league', 'market', 'match_date',
                                'trigger_at', 'created_at', 'alarm_type', 'old_leader', 
                                'old_leader_share', 'new_leader', 'new_leader_share', 'total_volume'],
        'dropping_alarms': ['id', 'match_id_hash', 'home', 'away', 'league', 'market', 
                           'selection', 'opening_odds', 'current_odds', 'drop_pct', 'level',
                           'match_date', 'trigger_at', 'created_at'],
        'mim_alarms': ['id', 'match_id_hash', 'home', 'away', 'league', 'market', 
                      'selection', 'impact', 'prev_volume', 'current_volume',
                      'incoming_volume', 'total_market_volume',
                      'match_date', 'trigger_at', 'created_at', 'alarm_history'],
        'telegram_sent_log': ['id', 'dedupe_key', 'match_id_hash', 'alarm_type', 
                             'market', 'selection', 'last_sent_at', 'last_delta', 'send_count'],
    }
    
    # Alan adi donusumleri (calculator -> db) - GLOBAL
    # Sadece tüm tablolarda ortak olan dönüşümler burada
    FIELD_MAPPING = {
        'match_id': 'match_id_hash',
        'selection_total': 'total_selection',
        'oran_dusus_pct': 'drop_pct',
        'odds_drop_pct': 'drop_pct',
    }
    
    # Tablo bazlı ek dönüşümler (global mapping'i override eder)
    # Her tablonun kendi field mapping'i - çakışma önlenir
    TABLE_FIELD_MAPPING = {
        'bigmoney_alarms': {
            'stake': 'incoming_money',
            'volume': 'incoming_money',
        },
        'insider_alarms': {
            'odds_drop_pct': 'drop_pct',
            'oran_dusus_pct': 'drop_pct',
            'incoming_money': 'total_money',
            'stake': 'total_money',
            'volume': 'total_money',
        },
        'volumeshock_alarms': {
            'volume_shock': 'volume_shock_value',
            'volume_shock_multiplier': 'volume_shock_value',
            'multiplier': 'volume_shock_value',
            'stake': 'incoming_money',
        },
        'sharp_alarms': {
            'volume': 'amount_change',
            'stake': 'amount_change',
        },
        'mim_alarms': {
            'impact_score': 'impact',
            'curr_volume': 'current_volume',
        },
    }
    
    # Çoklu alias çözümlemesi için öncelik sıralaması
    # Aynı hedef alana birden fazla kaynak alan map edildiğinde
    # sıfır olmayan ilk değer kullanılır
    ALIAS_PRIORITY = {
        'volume_shock_value': ['volume_shock', 'volume_shock_multiplier', 'multiplier'],
    }
    
    def _to_float(self, val) -> float:
        """String veya numeric değeri float'a dönüştür."""
        if val is None:
            return 0.0
        try:
            return float(val)
        except (ValueError, TypeError):
            return 0.0
    
    def _is_nonzero(self, val) -> bool:
        """Değerin sıfır olmadığını kontrol et (string "0" dahil)."""
        return self._to_float(val) != 0.0
    
    def _resolve_aliases(self, record: Dict, table: str) -> Dict:
        """
        Çoklu alias durumunda sıfır olmayan değeri seç.
        Orn: volume_shock=2.5, multiplier=0 -> volume_shock_value=2.5
        
        ÖNEMLİ: Eğer hedef alan zaten sıfır olmayan değer içeriyorsa korur.
        String değerler ("0", "2.5") de doğru şekilde işlenir.
        """
        resolved = dict(record)
        
        for target_field, source_aliases in self.ALIAS_PRIORITY.items():
            # Sadece ilgili tablolar için çözümle
            if table == 'volumeshock_alarms' and target_field == 'volume_shock_value':
                # Hedef alan zaten sıfır olmayan değer içeriyorsa koru
                existing_value = resolved.get(target_field)
                if existing_value is not None and self._is_nonzero(existing_value):
                    # Mevcut değeri koru, sadece alias'ları temizle
                    for alias in source_aliases:
                        if alias in resolved and alias != target_field:
                            del resolved[alias]
                    continue
                
                # Alias'lardan sıfır olmayan ilk değeri bul
                best_value = None
                for alias in source_aliases:
                    if alias in record:
                        val = record.get(alias)
                        if val is not None and self._is_nonzero(val):
                            best_value = val
                            break
                        elif best_value is None:
                            best_value = val  # Fallback: sıfır bile olsa al
                
                if best_value is not None:
                    resolved[target_field] = best_value
                
                # Kaynak alias'ları temizle
                for alias in source_aliases:
                    if alias in resolved and alias != target_field:
                        del resolved[alias]
        
        return resolved
    
    def _post(self, table: str, data: List[Dict], on_conflict=None, _retry=False) -> bool:
        try:
            # 0. Çoklu alias çözümlemesi (volume_shock_value gibi alanlar için)
            if table in ['volumeshock_alarms']:
                data = [self._resolve_aliases(record, table) for record in data]
            
            # 1. Alan adlarını dönüştür (global + tablo bazlı)
            # 2. Tabloda olmayan kolonları çıkar (schema cache workaround)
            known_cols = self.KNOWN_COLUMNS.get(table)
            table_mapping = self.TABLE_FIELD_MAPPING.get(table, {})
            
            if known_cols:
                cleaned_data = []
                for record in data:
                    mapped_record = {}
                    for k, v in record.items():
                        # Önce tablo bazlı, sonra global mapping uygula
                        new_key = table_mapping.get(k, self.FIELD_MAPPING.get(k, k))
                        # Çoklu alias için: sıfır olmayan değeri koru
                        if new_key in mapped_record and new_key in ['volume_shock_value']:
                            existing = mapped_record[new_key]
                            if existing is not None and existing != 0:
                                continue  # Mevcut değer sıfır değilse koru
                        mapped_record[new_key] = v
                    # Sadece bilinen kolonları tut
                    clean_record = {k: v for k, v in mapped_record.items() if k in known_cols}
                    cleaned_data.append(clean_record)
                data = cleaned_data
            
            headers = self._headers()
            headers["Prefer"] = "resolution=merge-duplicates"
            url = self._rest_url(table)
            if on_conflict:
                url = f"{url}?on_conflict={on_conflict}"
            
            resp = httpx.post(url, headers=headers, json=data, timeout=30)
            
            if resp.status_code in [200, 201]:
                return True
            else:
                error_body = resp.text[:500] if hasattr(resp, 'text') else str(resp.content[:500])
                
                # PGRST204 = Schema cache hatası - reload edip tekrar dene
                if resp.status_code == 400 and 'PGRST204' in error_body and not _retry:
                    log(f"[POST] {table}: Schema cache stale, reloading...")
                    if self._reload_schema_cache():
                        log(f"[POST] {table}: Retrying after schema reload...")
                        return self._post(table, data, on_conflict, _retry=True)
                
                log(f"[POST ERROR] {table}: HTTP {resp.status_code}")
                log(f"[POST ERROR] Response: {error_body}")
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
        """OPTIMIZED UPSERT - insert or update existing records based on key_fields
        Uses batch filtering instead of full-table read for better performance
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
            
            # OPTIMIZED: Only fetch existing records for current batch using first key field filter
            # Include alarm_history for BigMoney/VolumeShock refresh tracking
            refresh_tables = ['bigmoney_alarms', 'volumeshock_alarms']
            extra_fields = ['incoming_money', 'volume_shock_value', 'alarm_history'] if table in refresh_tables else []
            select_fields = ','.join(key_fields + ['trigger_at', 'created_at'] + extra_fields)
            existing_data = {}
            
            # Get unique values for the first key field (usually match_id or home)
            first_key = key_fields[0]
            unique_keys = list(set(str(a.get(first_key, '')) for a in alarms if a.get(first_key)))
            
            try:
                if unique_keys and len(unique_keys) <= 100:
                    # Batch query: only fetch records matching current batch keys
                    keys_param = ','.join(unique_keys)
                    existing = self._get(table, f'select={select_fields}&{first_key}=in.({keys_param})')
                else:
                    # Fallback: full table read for large batches (preserves correctness)
                    existing = self._get(table, f'select={select_fields}')
                
                if existing:
                    for e in existing:
                        key_parts = [str(e.get(f, '')) for f in key_fields]
                        key = '|'.join(key_parts)
                        existing_data[key] = {
                            'trigger_at': e.get('trigger_at'),
                            'created_at': e.get('created_at'),
                            'incoming_money': e.get('incoming_money', 0),
                            'volume_shock_value': e.get('volume_shock_value', 0),
                            'alarm_history': e.get('alarm_history', '[]')
                        }
                    query_type = "batch" if len(unique_keys) <= 100 else "full"
                    log(f"[UPSERT] Found {len(existing_data)} existing records ({query_type} query)")
            except Exception as ex:
                log(f"[UPSERT] Query failed, skipping timestamp preservation: {ex}")
            
            # Preserve original timestamps for existing alarms
            # EXCEPTION: bigmoney_alarms and volumeshock_alarms should UPDATE trigger_at
            # to show as "new" alarm when new money comes in
            should_preserve_trigger = table not in refresh_tables
            
            preserved_count = 0
            updated_alarms = []  # Track alarms with changed trigger_at
            for alarm in alarms:
                key_parts = [str(alarm.get(f, '')) for f in key_fields]
                key = '|'.join(key_parts)
                if key in existing_data:
                    orig = existing_data[key]
                    if should_preserve_trigger:
                        # Normal behavior: preserve trigger_at
                        if orig.get('trigger_at'):
                            alarm['trigger_at'] = orig['trigger_at']
                        if orig.get('created_at'):
                            alarm['created_at'] = orig['created_at']
                        preserved_count += 1
                    else:
                        # BigMoney/VolumeShock: check if trigger_at changed
                        old_trigger = orig.get('trigger_at', '')
                        new_trigger = alarm.get('trigger_at', '')
                        if old_trigger and new_trigger and old_trigger != new_trigger:
                            updated_alarms.append(alarm)
                            log(f"[UPSERT] {table}: trigger_at updated {old_trigger[:16]} -> {new_trigger[:16]}")
                        # Preserve only created_at
                        if orig.get('created_at'):
                            alarm['created_at'] = orig['created_at']
            
            if preserved_count > 0:
                log(f"[UPSERT] Preserved timestamps for {preserved_count} existing alarms")
            if updated_alarms:
                log(f"[UPSERT] {len(updated_alarms)} alarms will refresh (new trigger_at)")
            
            on_conflict = ",".join(key_fields)
            if self._post(table, alarms, on_conflict=on_conflict):
                log(f"[UPSERT] {table}: {len(alarms)} alarms upserted (on_conflict={on_conflict})")
                
                # Send Telegram notifications for NEW alarms and UPDATED alarms (BigMoney/VolumeShock)
                existing_keys = set(existing_data.keys())
                updated_keys = set()
                for a in updated_alarms:
                    key_parts = [str(a.get(f, '')) for f in key_fields]
                    updated_keys.add('|'.join(key_parts))
                self._notify_new_alarms(alarms, table, existing_keys, updated_keys)
                
                return len(alarms)
            else:
                log(f"[UPSERT] {table}: POST failed, trying without on_conflict")
                if self._post(table, alarms):
                    # Send Telegram notifications for NEW alarms and UPDATED alarms (BigMoney/VolumeShock)
                    existing_keys = set(existing_data.keys())
                    updated_keys = set()
                    for a in updated_alarms:
                        key_parts = [str(a.get(f, '')) for f in key_fields]
                        updated_keys.add('|'.join(key_parts))
                    self._notify_new_alarms(alarms, table, existing_keys, updated_keys)
                    return len(alarms)
        except Exception as e:
            log(f"Upsert error {table}: {e}")
        return 0
    
    def load_configs(self):
        """Load all alarm configs from Supabase alarm_settings table"""
        self._load_configs_from_db()
    
    def save_config_to_db(self, alarm_type: str, config: Dict, enabled: bool = True) -> bool:
        """Save alarm config to Supabase alarm_settings table
        Admin Panel -> Supabase yazma fonksiyonu
        
        Args:
            alarm_type: Alarm türü (sharp, insider, bigmoney, volumeshock, dropping, volumeleader, mim)
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
            kickoff = match.get('date', '')
            
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
                kickoff = match.get('date', '')
                
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
        """Get all matches with their latest data for a market (cached)
        
        Legacy tablolardan çeker: moneyway_1x2, moneyway_ou25, dropping_1x2 vb.
        """
        if market in self._matches_cache:
            return self._matches_cache[market]
        
        log(f"FETCH {market} (latest)...")
        
        matches = self._get(market, 'select=*')
        if matches:
            log(f"  -> {len(matches)} matches from {market} table")
            self._matches_cache[market] = matches
            return matches
        
        log(f"  -> 0 matches (no data found)")
        self._matches_cache[market] = []
        return []
    
    def batch_fetch_history(self, market: str) -> Dict[str, List[Dict]]:
        """Batch fetch ALL history for a market - NO LIMIT, tüm snapshot'lar okunur
        
        Legacy tablolardan okur: dropping_1x2_history, moneyway_1x2_history vb.
        KEY: match_id_hash (string eşleşmesi YOK)
        """
        cache_key = f"{market}_history"
        
        if cache_key in self._history_cache:
            return self._history_cache[cache_key]
        
        actual_table = f"{market}_history"
        log(f"[HISTORY] Fetching {actual_table}...")
        
        rows = []
        offset = 0
        page_size = 1000
        
        while True:
            params = f"select=*&order=scraped_at.asc&limit={page_size}&offset={offset}"
            
            batch = self._get(actual_table, params)
            if not batch:
                break
            rows.extend(batch)
            if len(batch) < page_size:
                break
            offset += page_size
        
        log(f"[HISTORY] {actual_table}: {len(rows)} total snapshots loaded")
        
        # KEY: match_id_hash ile gruplama, FALLBACK: league|home|away|date ile gruplama
        history_map = {}
        fallback_count = 0
        for row in rows:
            match_hash = row.get('match_id_hash', '')
            if not match_hash:
                # FALLBACK: league|home|away|date ile key oluştur (eski tablolar için)
                # Normalizasyon: lower, trim, çoklu boşluk temizliği
                home = ' '.join(row.get('home', '').strip().lower().split())
                away = ' '.join(row.get('away', '').strip().lower().split())
                league = ' '.join(row.get('league', '').strip().lower().split())
                # Kickoff date: normalize_date_for_db ile YYYY-MM-DD formatına çevir
                kickoff = row.get('date', row.get('kickoff', row.get('kickoff_utc', '')))
                kickoff_date = normalize_date_for_db(kickoff) if kickoff else ''
                
                if home and away:
                    # Güçlendirilmiş fallback key: league|home|away|date
                    match_hash = f"{league}|{home}|{away}|{kickoff_date}"
                    fallback_count += 1
                else:
                    continue
            if match_hash not in history_map:
                history_map[match_hash] = []
            history_map[match_hash].append(row)
        
        if fallback_count > 0:
            log(f"[HISTORY WARN] {cache_key}: match_id_hash missing -> {fallback_count} rows using fallback key (league|home|away|date)")
        log(f"[HISTORY] {cache_key}: {len(history_map)} unique matches")
        self._history_cache[cache_key] = history_map
        return history_map
    
    def get_match_history(self, match_id_hash: str, history_table: str, home: str = '', away: str = '', league: str = '', kickoff: str = '') -> List[Dict]:
        """Get historical snapshots for a match from cache
        MERGED: Hash ve fallback key kayıtlarını BİRLEŞTİRİR (eski + yeni veriler)
        """
        if history_table not in self._history_cache:
            market = history_table.replace('_history', '')
            self.batch_fetch_history(market)
        
        history_map = self._history_cache.get(history_table, {})
        
        # Fallback key oluştur
        fallback_key = None
        if home and away:
            home_norm = ' '.join(home.strip().lower().split())
            away_norm = ' '.join(away.strip().lower().split())
            league_norm = ' '.join(league.strip().lower().split()) if league else ''
            kickoff_date = normalize_date_for_db(kickoff) if kickoff else ''
            fallback_key = f"{league_norm}|{home_norm}|{away_norm}|{kickoff_date}"
        
        # MERGED: Hem hash hem fallback key'den gelen kayıtları birleştir
        combined = []
        seen_scraped_at = set()
        
        # Hash'li kayıtlar (yeni)
        if match_id_hash and match_id_hash in history_map:
            for snap in history_map.get(match_id_hash, []):
                scraped = snap.get('scraped_at', snap.get('scraped_at_utc', ''))
                if scraped not in seen_scraped_at:
                    combined.append(snap)
                    seen_scraped_at.add(scraped)
        
        # Fallback kayıtlar (eski, hash'siz)
        if fallback_key and fallback_key in history_map:
            for snap in history_map.get(fallback_key, []):
                scraped = snap.get('scraped_at', snap.get('scraped_at_utc', ''))
                if scraped not in seen_scraped_at:
                    combined.append(snap)
                    seen_scraped_at.add(scraped)
        
        # Zamana göre sırala (eski -> yeni)
        combined.sort(key=lambda x: x.get('scraped_at', x.get('scraped_at_utc', '')))
        
        return combined
    
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
        
        log("6/7 VolumeLeader hesaplaniyor...")
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
        
        log("7/7 MIM (Market Impact) hesaplaniyor...")
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
           - avg_last_amounts = son 20 snapshot'ın ortalaması
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
            range_drop = parse_float(config.get(f'odds_range_{i}_min_drop')) or 0  # Min drop eşiği
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
                
                # match_id_hash: Maçtan gelen değeri kullan, yoksa hesapla
                date_str = match.get('date', '')
                match_id_hash = match.get('match_id_hash') or generate_match_id_hash(home, away, match.get('league', ''), date_str)
                history = self.get_match_history(match_id_hash, history_table, home, away, match.get('league', ''), date_str)
                if len(history) < 2:
                    log(f"  [Sharp SKIP] {home} vs {away} | history < 2 ({len(history)} snapshots)")
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
                    
                    # === UI FORMÜLÜ: avg_last_amounts (son 20 snapshot ortalaması) ===
                    # PRIOR LOGIC: Deterministik fallback ile gerçek volume change korunur
                    last_20_amounts = []
                    for i in range(max(0, len(history) - 21), len(history) - 1):
                        amt = parse_volume(history[i].get(amount_key, 0))
                        last_20_amounts.append(amt)
                    
                    # UI Mantığı: Non-zero ortalaması, yoksa prev_amount, yoksa 1000 fallback
                    non_zero_amounts = [a for a in last_20_amounts if a > 0]
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
                        match_id = generate_match_id_hash(home, away, match.get('league', ''), match.get('date', ''))
                        
                        # UI ALAN ADLARIYLA ALARM KAYDI
                        alarm = {
                            'match_id_hash': match_id,
                            'home': home,
                            'away': away,
                            'league': match.get('league', ''),
                            'market': market_names.get(market, market),
                            'selection': selection,
                            'match_date': normalize_date_for_db(match.get('date', '')),
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
            new_count = self._upsert_alarms('sharp_alarms', alarms, ['match_id_hash', 'market', 'selection'])
            log(f"Sharp: {new_count} alarms upserted")
        else:
            log("Sharp: 0 alarm")
        
        return len(alarms)
    
    def calculate_insider_alarms(self) -> int:
        """Calculate Insider Info alarms - GÖRSEL KURALLARINA GÖRE
        
        1. Acilis->Simdi Dusus: Oranlar acilistan >= %X dustu mu?
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
                
                # match_id_hash: Maçtan gelen değeri kullan, yoksa hesapla
                date_str = match.get('date', '')
                match_id_hash = match.get('match_id_hash') or generate_match_id_hash(home, away, match.get('league', ''), date_str)
                history = self.get_match_history(match_id_hash, history_table, home, away, match.get('league', ''), date_str)
                if len(history) < 3:
                    log(f"  [Insider SKIP] {home} vs {away} | history < 3 ({len(history)} snapshots)")
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
                    
                    # KURAL 1: Acilis->Simdi drop kontrolu
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
                    match_id = generate_match_id_hash(home, away, match.get('league', ''), match.get('date', ''))
                    
                    alarm = {
                        'match_id_hash': match_id,
                        'home': home,
                        'away': away,
                        'league': match.get('league', ''),
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
                        'match_date': normalize_date_for_db(match.get('date', '')),
                        'trigger_at': trigger_at,
                        'created_at': now_turkey_iso(),
                        'alarm_type': 'insider'
                    }
                    alarms.append(alarm)
                    log(f"  [INSIDER] {home} vs {away} | {market_names.get(market, market)}-{selection} | Açılış: {opening_odds:.2f}->Şimdi: {actual_current_odds:.2f} (-%{actual_drop_pct:.1f}) | DüsusAnı: S{drop_moment_index} | Para: {total_incoming:,.0f}")
        
        if alarms:
            new_count = self._upsert_alarms('insider_alarms', alarms, ['match_id_hash', 'market', 'selection'])
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
                
                # DEBUG: Nott-Man City maçı için verbose log
                is_debug_match = 'nottingham' in home.lower() or 'forest' in home.lower() or 'man city' in away.lower() or 'manchester city' in away.lower()
                
                # match_id_hash: Maçtan gelen değeri kullan, yoksa hesapla
                date_str = match.get('date', '')
                match_id_hash = match.get('match_id_hash') or generate_match_id_hash(home, away, match.get('league', ''), date_str)
                
                if is_debug_match:
                    log(f"[BigMoney DEBUG] ========== {home} vs {away} ==========")
                    log(f"[BigMoney DEBUG] match_id_hash: {match_id_hash}")
                    log(f"[BigMoney DEBUG] market: {market}")
                    log(f"[BigMoney DEBUG] limit (threshold): {limit}")
                    log(f"[BigMoney DEBUG] date: {date_str}")
                
                history = self.get_match_history(match_id_hash, history_table, home, away, match.get('league', ''), date_str)
                
                if is_debug_match:
                    log(f"[BigMoney DEBUG] history snapshots: {len(history)}")
                
                if len(history) < 2:
                    log(f"  [BigMoney SKIP] {home} vs {away} | history < 2 ({len(history)} snapshots)")
                    if is_debug_match:
                        log(f"[BigMoney DEBUG] FAIL: history < 2 snapshots")
                    continue
                
                for sel_idx, selection in enumerate(selections):
                    amount_key = amount_keys[sel_idx]
                    
                    big_snapshots = []
                    max_incoming = 0
                    max_incoming_idx = -1
                    
                    if is_debug_match:
                        log(f"[BigMoney DEBUG] Selection: {selection}, amount_key: {amount_key}")
                    
                    for i in range(1, len(history)):
                        curr_amt = parse_volume(history[i].get(amount_key, 0))
                        prev_amt = parse_volume(history[i-1].get(amount_key, 0))
                        incoming = curr_amt - prev_amt
                        
                        if is_debug_match and incoming > 1000:
                            log(f"[BigMoney DEBUG]   snapshot[{i}]: prev={prev_amt:.0f}, curr={curr_amt:.0f}, delta={incoming:.0f}, limit={limit}, PASS={incoming >= limit}")
                        
                        if incoming > max_incoming:
                            max_incoming = incoming
                            max_incoming_idx = i
                        
                        if incoming >= limit:
                            big_snapshots.append({
                                'index': i,
                                'incoming': incoming,
                                'scraped_at': history[i].get('scraped_at', '')
                            })
                    
                    if is_debug_match:
                        log(f"[BigMoney DEBUG] {selection}: max_incoming={max_incoming:.0f} (idx={max_incoming_idx}), big_snapshots={len(big_snapshots)}")
                        if max_incoming < limit:
                            log(f"[BigMoney DEBUG] FAIL: max_incoming ({max_incoming:.0f}) < limit ({limit})")
                    
                    if not big_snapshots:
                        continue
                    
                    match_id = match_id_hash
                    
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
                        
                        # HER ALARM İÇİN O ANKİ selection_total değerini al
                        # snap['index'] = bu alarmın tetiklendiği history index
                        selection_total = parse_volume(history[snap['index']].get(amount_key, 0))
                        
                        alarm = {
                            'match_id_hash': match_id,
                            'home': home,
                            'away': away,
                            'league': match.get('league', ''),
                            'market': market_names.get(market, market),
                            'selection': selection,
                            'incoming_money': snap['incoming'],
                            'selection_total': selection_total,
                            'is_huge': is_huge,
                            'huge_total': huge_total,
                            'alarm_type': 'HUGE MONEY' if is_huge else 'BIG MONEY',
                            'match_date': normalize_date_for_db(match.get('date', '')),
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
                key = (alarm['match_id_hash'], alarm['market'], alarm['selection'])
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
            new_count = self._upsert_alarms('bigmoney_alarms', filtered_alarms, ['match_id_hash', 'market', 'selection'])
            log(f"BigMoney: {new_count} alarms upserted (with history)")
            
            # NOT: BigMoney alarmları silinmez - sadece upsert yapılır
            # Stale cleanup KALDIRILDI - alarmlar kalıcı olmalı
        
        return len(alarms)
    
    def calculate_volumeshock_alarms(self) -> int:
        """Calculate Volume Shock alarms"""
        # NOT: VolumeShock alarmları silinmez - sadece upsert yapılır
        # Tablo temizleme KALDIRILDI - alarmlar kalıcı olmalı
        
        # HISTORY TRACKING: Mevcut alarmları yükle (match_id ile - BigMoney gibi)
        existing_alarms = {}
        try:
            existing = self._get('volumeshock_alarms', 'select=*') or []
            for row in existing:
                key = f"{row.get('match_id', '')}|{row.get('market', '')}|{row.get('selection', '')}"
                existing_alarms[key] = row
            log(f"[VolumeShock] {len(existing_alarms)} existing alarms loaded for history tracking")
        except Exception as e:
            log(f"[VolumeShock] Existing alarms load failed: {e}")
        
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
                
                # match_id_hash: Maçtan gelen değeri kullan, yoksa hesapla
                date_str = match.get('date', '')
                match_id_hash = match.get('match_id_hash') or generate_match_id_hash(home, away, match.get('league', ''), date_str)
                history = self.get_match_history(match_id_hash, history_table, home, away, match.get('league', ''), date_str)
                if len(history) < 5:
                    log(f"  [VolumeShock SKIP] {home} vs {away} | history < 5 ({len(history)} snapshots)")
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
                        match_id = generate_match_id_hash(home, away, match.get('league', ''), match.get('date', ''))
                        
                        alarm = {
                            'match_id_hash': match_id,
                            'home': home,
                            'away': away,
                            'league': match.get('league', ''),
                            'market': market_names.get(market, market),
                            'selection': selection,
                            'volume_shock_value': round(best_shock['shock_value'], 2),
                            'incoming_money': best_shock['incoming'],
                            'avg_previous': round(best_shock['avg_prev'], 0),
                            'match_date': normalize_date_for_db(match.get('date', '')),
                            'trigger_at': best_shock['trigger_at'],
                            'created_at': now_turkey_iso(),
                            'alarm_type': 'volumeshock'
                        }
                        alarms.append(alarm)
                        log(f"  [VOLUMESHOCK] {home} vs {away} | {market_names.get(market, market)}-{selection} | Shock: {best_shock['shock_value']:.1f}x | £{best_shock['incoming']:,.0f} gelen (snap #{best_shock['snapshot_idx']})")
        
        if alarms:
            import json
            
            # HISTORY GROUPING: Aynı key için history oluştur (match_id ile - BigMoney gibi)
            filtered_alarms = []
            for alarm in alarms:
                str_key = f"{alarm['match_id_hash']}|{alarm['market']}|{alarm['selection']}"
                
                current_history = []
                
                # Mevcut DB'deki history'yi yükle (match_id ile)
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
                    old_shock = old_alarm.get('volume_shock_value', 0)
                    main_trigger = alarm.get('trigger_at', '')
                    
                    if old_trigger and old_trigger != main_trigger and old_incoming > 0:
                        db_history.append({
                            'incoming_money': old_incoming,
                            'trigger_at': old_trigger,
                            'volume_shock_value': old_shock,
                            'avg_previous': old_alarm.get('avg_previous', 0)
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
                
                alarm['alarm_history'] = json.dumps(unique_history)
                filtered_alarms.append(alarm)
            
            log(f"VolumeShock: {len(alarms)} alarms with history")
            
            new_count = self._upsert_alarms('volumeshock_alarms', filtered_alarms, ['match_id_hash', 'market', 'selection'])
            log(f"VolumeShock: {new_count} alarms upserted (with history)")
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
        seen_alarms = set()
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
                
                # match_id_hash: Maçtan gelen değeri kullan, yoksa hesapla
                match_id_hash = match.get('match_id_hash') or generate_match_id_hash(home, away, match.get('league', ''), match.get('date', ''))
                history_raw = self.get_match_history(match_id_hash, history_table, home, away, match.get('league', ''), match.get('date', ''))
                
                if len(history_raw) < 2:
                    log(f"  [Dropping SKIP] {home} vs {away} | history < 2 ({len(history_raw)} snapshots)")
                    continue
                
                # History'i scraped_at/scraped_at_utc'e göre sırala (kronolojik doğruluk için)
                def parse_timestamp(s):
                    try:
                        # Tüm timestamp'leri naive'e çevir (karşılaştırma için)
                        dt = datetime.fromisoformat(s.replace('Z', '+00:00'))
                        if dt.tzinfo:
                            dt = dt.replace(tzinfo=None)
                        return dt
                    except:
                        return datetime.min
                
                def get_scraped_at(x):
                    # scraped_at_utc (yeni şema) veya scraped_at (eski şema)
                    return x.get('scraped_at_utc', x.get('scraped_at', ''))
                
                history = sorted(history_raw, key=lambda x: parse_timestamp(get_scraped_at(x)))
                
                for sel_idx, selection in enumerate(selections):
                    odds_key = odds_keys[sel_idx]
                    
                    # Legacy şema: odds1, oddsx, odds2, over, under vb. kolonları kullan
                    opening_odds = parse_float(history[0].get(odds_key, 0))
                    current_odds = parse_float(history[-1].get(odds_key, 0))
                    history_for_persistence = history
                    
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
                        
                        # Son snapshot'ın zamanını al (referans nokta) - history_for_persistence kullan
                        latest_scraped_at = parse_timestamp(get_scraped_at(history_for_persistence[-1]))
                        if latest_scraped_at == datetime.min:
                            latest_scraped_at = datetime.now()
                        
                        persistence_threshold = latest_scraped_at - timedelta(minutes=persistence_minutes)
                        
                        # Kalıcılık penceresi içindeki snapshot'ları filtrele - history_for_persistence kullan
                        for snap in history_for_persistence:
                            snap_time = parse_timestamp(get_scraped_at(snap))
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
                            # Legacy şema: odds_key (odds1, oddsx vb.) kullan
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
                    
                    trigger_at = get_scraped_at(history_for_persistence[-1]) or now_turkey_iso()
                    match_id = generate_match_id_hash(home, away, match.get('league', ''), match.get('date', ''))
                    
                    # Volume bilgisi (varsa)
                    volume = parse_float(match.get('volume', 0))
                    
                    alarm_key = (match_id, market_names.get(market, market), selection)
                    if alarm_key in seen_alarms:
                        continue
                    seen_alarms.add(alarm_key)
                    
                    alarm = {
                        'match_id_hash': match_id,
                        'home': home,
                        'away': away,
                        'league': match.get('league', ''),
                        'market': market_names.get(market, market),
                        'selection': selection,
                        'opening_odds': round(opening_odds, 2),
                        'current_odds': round(current_odds, 2),
                        'drop_pct': round(drop_pct, 2),
                        'level': level,
                        'volume': volume,
                        'match_date': normalize_date_for_db(match.get('date', '')),
                        'trigger_at': trigger_at,
                        'created_at': now_turkey_iso(),
                        'alarm_type': 'dropping',
                        'persistence_minutes': int(persistence_minutes),
                        'snapshots_checked': int(len(recent_snapshots))
                    }
                    alarms.append(alarm)
                    log(f"  [DROPPING-{level}] {home} vs {away} | {market_names.get(market, market)}-{selection} | {opening_odds:.2f}->{current_odds:.2f} (-%{drop_pct:.1f}) | Kalıcı: {len(recent_snapshots)} snap")
        
        if alarms:
            new_count = self._upsert_alarms('dropping_alarms', alarms, ['match_id_hash', 'market', 'selection'])
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
                
                # match_id_hash: Maçtan gelen değeri kullan, yoksa hesapla
                date_str = match.get('date', '')
                match_id_hash = match.get('match_id_hash') or generate_match_id_hash(home, away, match.get('league', ''), date_str)
                history = self.get_match_history(match_id_hash, history_table, home, away, match.get('league', ''), date_str)
                if len(history) < 2:
                    log(f"  [VolumeLeader SKIP] {home} vs {away} | history < 2 ({len(history)} snapshots)")
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
                        match_id = match_id_hash
                        
                        alarm = {
                            'match_id_hash': match_id,
                            'home': home,
                            'away': away,
                            'league': match.get('league', ''),
                            'market': market_names.get(market, market),
                            'old_leader': prev_leader[0],
                            'old_leader_share': round(prev_leader[1], 1),
                            'new_leader': curr_leader[0],
                            'new_leader_share': round(curr_leader[1], 1),
                            'total_volume': trigger_volume,
                            'match_date': normalize_date_for_db(match.get('date', '')),
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
        """Calculate MIM (Market Impact) alarms - SELECTION BAZLI - 3 MARKET
        
        MIM Formülü:
        - Impact = (selection'a gelen yeni para) / (toplam volume)
        - Örnek: Over'a £2k geldi, toplam £3k ise Impact = 2k / 3k = %66
        - Alarm üretilir: impact >= min_impact_threshold
        - Her selection için AYRI alarm üretilir
        
        Marketler:
        - 1X2: selections = 1, X, 2
        - OU25: selections = O (Over), U (Under)
        - BTTS: selections = Y (Yes), N (No)
        """
        config = self.configs.get('mim')
        if not config:
            log("[MIM] CONFIG YOK - Supabase'de mim ayarlarını kaydedin!")
            return 0
        
        if not config.get('enabled', True):
            log("[MIM] Alarm devre dışı")
            return 0
        
        min_impact_threshold = parse_float(config.get('min_impact_threshold')) or 0.10
        min_total_volume = parse_float(config.get('min_prev_volume')) or 1000
        
        log(f"[MIM] Config: min_impact_threshold={min_impact_threshold} (%{min_impact_threshold*100:.0f}), min_total_volume={min_total_volume}")
        
        all_alarms = []
        
        markets_config = [
            {
                'table': 'moneyway_1x2',
                'name': '1X2',
                'selections': [
                    ('1', 'amt1', 'total_amount_1'),
                    ('X', 'amtx', 'total_amount_x'),
                    ('2', 'amt2', 'total_amount_2')
                ],
                'volume_keys': [('amt1', 'total_amount_1'), ('amtx', 'total_amount_x'), ('amt2', 'total_amount_2')],
                'component_labels': ('H', 'D', 'A')
            },
            {
                'table': 'moneyway_ou25',
                'name': 'OU25',
                'selections': [
                    ('O', 'amtover', 'total_amount_over'),
                    ('U', 'amtunder', 'total_amount_under')
                ],
                'volume_keys': [('amtover', 'total_amount_over'), ('amtunder', 'total_amount_under')],
                'component_labels': ('Over', 'Under')
            },
            {
                'table': 'moneyway_btts',
                'name': 'BTTS',
                'selections': [
                    ('Y', 'amtyes', 'total_amount_yes'),
                    ('N', 'amtno', 'total_amount_no')
                ],
                'volume_keys': [('amtyes', 'total_amount_yes'), ('amtno', 'total_amount_no')],
                'component_labels': ('Yes', 'No')
            }
        ]
        
        for mkt_config in markets_config:
            market_table = mkt_config['table']
            market_name = mkt_config['name']
            selections = mkt_config['selections']
            volume_keys = mkt_config['volume_keys']
            component_labels = mkt_config['component_labels']
            
            matches = self.get_matches_with_latest(market_table)
            if not matches:
                log(f"[MIM] {market_name}: maç yok")
                continue
            
            log(f"[MIM] {market_name}: {len(matches)} maç inceleniyor...")
            market_alarm_count = 0
            
            for match in matches:
                home = match.get('home', '')
                away = match.get('away', '')
                
                if not self._is_valid_match_date(match.get('date', '')):
                    continue
                
                # match_id_hash: Maçtan gelen değeri kullan, yoksa hesapla
                match_id_hash = match.get('match_id_hash') or generate_match_id_hash(home, away, match.get('league', ''), match.get('date', ''))
                history = self.get_match_history(match_id_hash, f"{market_table}_history", home, away, match.get('league', ''), match.get('date', ''))
                if len(history) < 2:
                    log(f"  [MIM SKIP] {home} vs {away} | history < 2 ({len(history)} snapshots)")
                    continue
                
                sorted_history = sorted(history, key=lambda x: x.get('scraped_at', ''))
                
                latest_alarm_per_selection = {}
                
                for i in range(1, len(sorted_history)):
                    prev_snap = sorted_history[i - 1]
                    curr_snap = sorted_history[i]
                    
                    prev_volumes = []
                    curr_volumes = []
                    for amt_key, alt_key in volume_keys:
                        prev_volumes.append(parse_volume(prev_snap.get(amt_key) or prev_snap.get(alt_key, 0)))
                        curr_volumes.append(parse_volume(curr_snap.get(amt_key) or curr_snap.get(alt_key, 0)))
                    
                    prev_total_volume = sum(prev_volumes)
                    curr_total_volume = sum(curr_volumes)
                    
                    if prev_total_volume < min_total_volume:
                        continue
                    
                    if curr_total_volume <= 0:
                        continue
                    
                    for selection, amt_key, alt_amt_key in selections:
                        prev_amt = parse_volume(prev_snap.get(amt_key) or prev_snap.get(alt_amt_key, 0))
                        curr_amt = parse_volume(curr_snap.get(amt_key) or curr_snap.get(alt_amt_key, 0))
                        
                        incoming_money = curr_amt - prev_amt
                        
                        if incoming_money <= 0:
                            continue
                        
                        impact = incoming_money / curr_total_volume
                        
                        if impact < min_impact_threshold:
                            continue
                        
                        trigger_at = curr_snap.get('scraped_at', now_turkey_iso())
                        
                        latest_alarm_per_selection[selection] = {
                            'match_id_hash': match_id_hash,
                            'home': home,
                            'away': away,
                            'league': match.get('league', ''),
                            'market': market_name,
                            'selection': selection,
                            'impact_score': round(impact, 4),
                            'prev_volume': round(prev_amt, 2),
                            'curr_volume': round(curr_amt, 2),
                            'incoming_volume': round(incoming_money, 2),
                            'total_market_volume': round(curr_total_volume, 2),
                            'match_date': normalize_date_for_db(match.get('date', '')),
                            'trigger_at': trigger_at,
                            'created_at': now_turkey_iso(),
                            'alarm_type': 'mim',
                            '_log_components': tuple(curr_volumes),
                            '_component_labels': component_labels
                        }
                
                for selection, alarm in latest_alarm_per_selection.items():
                    comp = alarm.pop('_log_components', ())
                    labels = alarm.pop('_component_labels', ())
                    all_alarms.append(alarm)
                    market_alarm_count += 1
                    
                    comp_str = ', '.join([f"{labels[j]}={comp[j]:,.0f}" for j in range(len(comp))])
                    log(f"  [MIM] {home} vs {away} | {market_name} | {selection} | vol: {alarm['prev_volume']:,.0f}->{alarm['curr_volume']:,.0f} (+{alarm['incoming_volume']:,.0f}) | market_total: {alarm['total_market_volume']:,.0f} | impact: {alarm['impact_score']:.3f} (%{alarm['impact_score']*100:.1f})")
                    log(f"        -> components: {comp_str}")
            
            log(f"[MIM] {market_name}: {market_alarm_count} alarm bulundu")
        
        if all_alarms:
            # Mevcut alarmları çek (alarm_history birleştirmesi için)
            existing = self._get('mim_alarms', 
                                 'select=match_id_hash,market,selection,impact,incoming_volume,trigger_at,alarm_history&limit=5000')
            existing_map = {}
            for e in existing:
                key = f"{e.get('match_id_hash')}_{e.get('market')}_{e.get('selection')}"
                existing_map[key] = e
            
            # Her alarm için history birleştir
            filtered_alarms = []
            for alarm in all_alarms:
                key = f"{alarm['match_id_hash']}_{alarm['market']}_{alarm['selection']}"
                
                # Mevcut history'i al
                current_history = []
                if key in existing_map:
                    old_alarm = existing_map[key]
                    try:
                        old_history = old_alarm.get('alarm_history', '[]')
                        if old_history:
                            current_history = json.loads(old_history) if isinstance(old_history, str) else old_history
                    except:
                        current_history = []
                    
                    # Eski alarmı history'e ekle
                    current_history.append({
                        'impact_score': old_alarm.get('impact', 0),
                        'incoming_volume': old_alarm.get('incoming_volume', 0),
                        'trigger_at': old_alarm.get('trigger_at', '')
                    })
                
                # Yeni (şu anki) alarmı da history'e ekle
                current_history.append({
                    'impact_score': alarm.get('impact_score', 0),
                    'incoming_volume': alarm.get('incoming_volume', 0),
                    'trigger_at': alarm.get('trigger_at', '')
                })
                
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
                
                alarm['alarm_history'] = json.dumps(unique_history)
                filtered_alarms.append(alarm)
            
            log(f"MIM: {len(all_alarms)} alarms with history")
            
            new_count = self._upsert_alarms('mim_alarms', filtered_alarms, ['match_id_hash', 'market', 'selection'])
            log(f"MIM TOPLAM: {new_count} alarms upserted (3 market, with history)")
            return new_count
        else:
            log("MIM: 0 alarm (3 market)")
        
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
