"""
ALARM SAFETY LAYER - Append-Only + Idempotent + Self-Check

Bu modül alarm sisteminin güvenlik katmanını sağlar:
1. Append-only: Alarmlar asla silinmez veya üzerine yazılmaz
2. Idempotent: Aynı alarm birden fazla kez üretilmez
3. Self-check: Periyodik reconciliation ile eksik alarmlar tespit edilir
4. Error tracking: Hata durumları loglanır ve izlenir
"""

import os
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple, Set
import pytz

TR_TZ = pytz.timezone('Europe/Istanbul')

FAILED_ALARMS_LOG = os.path.join(os.path.dirname(__file__), '..', 'data', 'failed_alarms.json')
RECONCILIATION_LOG = os.path.join(os.path.dirname(__file__), '..', 'data', 'reconciliation_log.json')


def generate_alarm_fingerprint(alarm: Dict[str, Any]) -> str:
    """
    Generate a unique fingerprint for an alarm.
    This is used for deduplication without losing alarms.
    
    Fingerprint = match_id|alarm_type|side|market|window_bucket
    
    window_bucket: 10-minute precision (e.g., "2025-11-28T14:10")
    This ensures separate alarms for each 10-minute window:
    - 14:00-14:09 → "2025-11-28T14:0"
    - 14:10-14:19 → "2025-11-28T14:1"
    - 14:20-14:29 → "2025-11-28T14:2"
    etc.
    """
    match_id = alarm.get('match_id', '')
    alarm_type = alarm.get('type', alarm.get('alarm_type', ''))
    side = alarm.get('side', '')
    market = alarm.get('market', '')
    
    window_start = alarm.get('window_start', '')
    if window_start and len(window_start) >= 16:
        minute_str = window_start[14:16]
        try:
            minute = int(minute_str)
            bucket_minute = (minute // 10) * 10
            window_bucket = f"{window_start[:14]}{bucket_minute:02d}"
        except ValueError:
            window_bucket = window_start[:16]
    elif window_start and len(window_start) >= 13:
        window_bucket = window_start[:13]
    else:
        window_bucket = ''
    
    return f"{match_id}|{alarm_type}|{side}|{market}|{window_bucket}"


def log_failed_alarm(alarm: Dict[str, Any], error: str, context: str = '') -> None:
    """
    Log a failed alarm insert for later retry.
    This ensures no alarm is silently lost.
    """
    try:
        os.makedirs(os.path.dirname(FAILED_ALARMS_LOG), exist_ok=True)
        
        failed_entry = {
            'alarm': alarm,
            'error': str(error),
            'context': context,
            'timestamp': datetime.now(TR_TZ).isoformat(),
            'fingerprint': generate_alarm_fingerprint(alarm)
        }
        
        existing = []
        if os.path.exists(FAILED_ALARMS_LOG):
            try:
                with open(FAILED_ALARMS_LOG, 'r') as f:
                    existing = json.load(f)
            except:
                existing = []
        
        existing.append(failed_entry)
        
        existing = existing[-1000:]
        
        with open(FAILED_ALARMS_LOG, 'w') as f:
            json.dump(existing, f, indent=2, default=str)
        
        print(f"[AlarmSafety] FAILED ALARM LOGGED: {error}")
        
    except Exception as e:
        print(f"[AlarmSafety] Could not log failed alarm: {e}")


def get_failed_alarms() -> List[Dict[str, Any]]:
    """Get all failed alarms for retry."""
    try:
        if os.path.exists(FAILED_ALARMS_LOG):
            with open(FAILED_ALARMS_LOG, 'r') as f:
                return json.load(f)
    except:
        pass
    return []


def clear_failed_alarm(fingerprint: str) -> None:
    """Remove a failed alarm after successful retry."""
    try:
        failed = get_failed_alarms()
        failed = [f for f in failed if f.get('fingerprint') != fingerprint]
        with open(FAILED_ALARMS_LOG, 'w') as f:
            json.dump(failed, f, indent=2, default=str)
    except:
        pass


def cleanup_old_failed_alarms(days: int = 7) -> int:
    """
    Remove failed alarms older than specified days.
    Called periodically to prevent log file from growing indefinitely.
    
    Returns number of removed entries.
    """
    try:
        failed = get_failed_alarms()
        if not failed:
            return 0
        
        cutoff = datetime.now(TR_TZ) - timedelta(days=days)
        original_count = len(failed)
        
        filtered = []
        for entry in failed:
            try:
                ts = entry.get('timestamp', '')
                if ts:
                    entry_time = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                    if entry_time.tzinfo is None:
                        entry_time = TR_TZ.localize(entry_time)
                    if entry_time >= cutoff:
                        filtered.append(entry)
                else:
                    filtered.append(entry)
            except:
                filtered.append(entry)
        
        removed_count = original_count - len(filtered)
        
        if removed_count > 0:
            with open(FAILED_ALARMS_LOG, 'w') as f:
                json.dump(filtered, f, indent=2, default=str)
            print(f"[AlarmSafety] Cleaned up {removed_count} old failed alarms (>{days} days)")
        
        return removed_count
        
    except Exception as e:
        print(f"[AlarmSafety] Cleanup error: {e}")
        return 0


def log_reconciliation_result(
    total_expected: int,
    total_found: int,
    missing_count: int,
    inserted_count: int,
    details: List[str] = None
) -> None:
    """Log reconciliation job results."""
    try:
        os.makedirs(os.path.dirname(RECONCILIATION_LOG), exist_ok=True)
        
        entry = {
            'timestamp': datetime.now(TR_TZ).isoformat(),
            'total_expected': total_expected,
            'total_found': total_found,
            'missing_count': missing_count,
            'inserted_count': inserted_count,
            'status': 'OK' if missing_count == 0 else 'FIXED' if inserted_count == missing_count else 'PARTIAL',
            'details': details or []
        }
        
        existing = []
        if os.path.exists(RECONCILIATION_LOG):
            try:
                with open(RECONCILIATION_LOG, 'r') as f:
                    existing = json.load(f)
            except:
                existing = []
        
        existing.append(entry)
        existing = existing[-100:]
        
        with open(RECONCILIATION_LOG, 'w') as f:
            json.dump(existing, f, indent=2, default=str)
        
        print(f"[Reconciliation] Logged: expected={total_expected}, found={total_found}, missing={missing_count}, fixed={inserted_count}")
        
    except Exception as e:
        print(f"[Reconciliation] Could not log result: {e}")


def run_reconciliation(
    supabase_client,
    markets: List[str],
    lookback_days: int = 7
) -> Dict[str, Any]:
    """
    RECONCILIATION JOB - Self-check for missing alarms.
    
    This job:
    1. Gets all today/future matches
    2. Runs alarm detection on their history
    3. Compares expected alarms (SET A) with DB alarms (SET B)
    4. Inserts any missing alarms
    
    Returns summary of what was found/fixed.
    """
    from core.alarms.main import analyze_match_alarms
    from core.timezone import is_match_today_or_future
    
    print("[Reconciliation] Starting self-check...")
    
    DEMO_TEAMS = {'Whale FC', 'Sharp FC', 'Pro Bettors XI', 'Casual City', 'Target United', 
                  'Small Fish', 'Budget Boys', 'Line Freeze FC', 'Bookmaker XI', 
                  'Public Money FC', 'Trending Town', 'Accelerate FC', 'Brake City',
                  'Volume Kings', 'Momentum FC', 'Surge United', 'Popular FC', 'Underdog Utd',
                  'No Move Utd', 'Steady State', 'Frozen FC', 'Static City', 'Money Makers',
                  'Fan Favorite', 'NoName FC', 'Rising Stars', 'Slow Movers'}
    
    def is_demo(home, away):
        return home in DEMO_TEAMS or away in DEMO_TEAMS
    
    try:
        matches_data = supabase_client.get_all_matches_with_latest('moneyway_1x2')
        future_matches = [
            m for m in matches_data 
            if is_match_today_or_future(m.get('date', '')) 
            and not is_demo(m.get('home_team', ''), m.get('away_team', ''))
        ]
        
        print(f"[Reconciliation] Checking {len(future_matches)} future matches across {len(markets)} markets...")
        
        SET_A = {}
        
        match_pairs = [(m.get('home_team', ''), m.get('away_team', '')) for m in future_matches]
        match_info = {
            (m.get('home_team', ''), m.get('away_team', '')): {
                'league': m.get('league', ''),
                'date': m.get('date', '')
            } for m in future_matches
        }
        
        for market in markets:
            bulk_history = supabase_client.get_bulk_history_for_alarms(market, match_pairs)
            
            for (home, away), history in bulk_history.items():
                if len(history) < 2:
                    continue
                
                info = match_info.get((home, away), {})
                match_date = info.get('date', '')
                league = info.get('league', '')
                
                alarms = analyze_match_alarms(history, market, match_date=match_date)
                
                for alarm in alarms:
                    alarm['match_id'] = f"{home}|{away}|{league}|{match_date}"
                    alarm['home'] = home
                    alarm['away'] = away
                    alarm['league'] = league
                    alarm['match_date'] = match_date
                    alarm['market'] = market
                    
                    fingerprint = generate_alarm_fingerprint(alarm)
                    if fingerprint not in SET_A:
                        SET_A[fingerprint] = alarm
        
        print(f"[Reconciliation] SET A (expected): {len(SET_A)} unique alarms")
        
        db_alarms = supabase_client.get_persistent_alarms()
        SET_B = set()
        
        for alarm in db_alarms:
            match_date = alarm.get('match_date', '')
            home = alarm.get('home', '')
            away = alarm.get('away', '')
            
            if is_match_today_or_future(match_date) and not is_demo(home, away):
                fingerprint = generate_alarm_fingerprint(alarm)
                SET_B.add(fingerprint)
        
        print(f"[Reconciliation] SET B (in DB): {len(SET_B)} unique alarms")
        
        missing = set(SET_A.keys()) - SET_B
        print(f"[Reconciliation] Missing alarms: {len(missing)}")
        
        inserted = 0
        details = []
        
        for fingerprint in missing:
            alarm = SET_A[fingerprint]
            try:
                success = supabase_client.save_smart_money_alarm(alarm)
                if success:
                    inserted += 1
                    details.append(f"FIXED: {alarm.get('home')} vs {alarm.get('away')} | {alarm.get('type')}")
                else:
                    details.append(f"FAILED: {alarm.get('home')} vs {alarm.get('away')} | {alarm.get('type')}")
                    log_failed_alarm(alarm, "Insert returned False", "reconciliation")
            except Exception as e:
                details.append(f"ERROR: {alarm.get('home')} vs {alarm.get('away')} | {str(e)}")
                log_failed_alarm(alarm, str(e), "reconciliation")
        
        log_reconciliation_result(
            total_expected=len(SET_A),
            total_found=len(SET_B),
            missing_count=len(missing),
            inserted_count=inserted,
            details=details[:50]
        )
        
        print(f"[Reconciliation] Complete: {len(missing)} missing, {inserted} fixed")
        
        return {
            'status': 'success',
            'expected': len(SET_A),
            'found': len(SET_B),
            'missing': len(missing),
            'inserted': inserted,
            'details': details
        }
        
    except Exception as e:
        print(f"[Reconciliation] Error: {e}")
        import traceback
        traceback.print_exc()
        return {
            'status': 'error',
            'error': str(e)
        }


def retry_failed_alarms(supabase_client) -> Dict[str, Any]:
    """
    Retry inserting failed alarms.
    Called periodically to recover from temporary failures.
    """
    failed = get_failed_alarms()
    if not failed:
        return {'status': 'no_failures', 'count': 0}
    
    print(f"[AlarmSafety] Retrying {len(failed)} failed alarms...")
    
    success_count = 0
    for entry in failed:
        alarm = entry.get('alarm', {})
        fingerprint = entry.get('fingerprint', '')
        
        try:
            if supabase_client.save_smart_money_alarm(alarm):
                success_count += 1
                clear_failed_alarm(fingerprint)
        except:
            pass
    
    print(f"[AlarmSafety] Retry complete: {success_count}/{len(failed)} recovered")
    
    return {
        'status': 'retried',
        'total': len(failed),
        'recovered': success_count
    }


class AlarmSafetyGuard:
    """
    Safety guard that wraps alarm operations.
    Ensures append-only behavior and proper error handling.
    """
    
    def __init__(self, supabase_client):
        self.supabase = supabase_client
        self.seen_fingerprints: Set[str] = set()
    
    def safe_save_alarm(self, alarm: Dict[str, Any]) -> bool:
        """
        Safely save an alarm with full error handling and logging.
        
        - Generates fingerprint for deduplication
        - Logs failures for later retry
        - Never throws exceptions to caller
        - CRITICAL: Short-circuits if Supabase unavailable
        """
        if not self.supabase or not getattr(self.supabase, 'is_available', False):
            log_failed_alarm(alarm, "Supabase unavailable", "safe_save_unavailable")
            return False
        
        fingerprint = generate_alarm_fingerprint(alarm)
        
        if fingerprint in self.seen_fingerprints:
            return True
        
        try:
            success = self.supabase.save_smart_money_alarm(alarm)
            
            if not success:
                print(f"[AlarmSafety] Save returned False for alarm_type={alarm.get('type')} match_id={alarm.get('match_id')}")
            
            if success:
                self.seen_fingerprints.add(fingerprint)
                print(f"[AlarmSafety] Saved alarm_type={alarm.get('type')} side={alarm.get('side')} odds={alarm.get('odds_from')}->{alarm.get('odds_to')}")
                return True
            else:
                log_failed_alarm(alarm, "Insert returned False", "safe_save")
                return False
                
        except Exception as e:
            log_failed_alarm(alarm, str(e), "safe_save_exception")
            print(f"[AlarmSafety] Save failed for {alarm.get('type')}: {e}")
            return False
    
    def safe_save_batch(self, alarms: List[Dict[str, Any]]) -> int:
        """
        Save multiple alarms safely.
        
        CRITICAL: Returns immediately if Supabase is unavailable to prevent hanging.
        """
        if not self.supabase or not getattr(self.supabase, 'is_available', False):
            print(f"[AlarmSafety] Supabase unavailable - skipping batch save of {len(alarms)} alarms")
            for alarm in alarms:
                log_failed_alarm(alarm, "Supabase unavailable", "batch_unavailable")
            return 0
        
        saved = 0
        for alarm in alarms:
            if self.safe_save_alarm(alarm):
                saved += 1
        return saved


def verify_no_delete_operations() -> Dict[str, Any]:
    """
    SAFETY CHECK: Verify that no DELETE operations exist in alarm-related code.
    This is a defensive check to ensure append-only behavior.
    
    Checks for actual executable DELETE SQL statements, not documentation strings.
    """
    import re
    
    dangerous_sql_patterns = [
        r'\.delete\s*\(\s*\)',
        r'DELETE\s+FROM\s+smart_money_alarms',
        r'supabase.*\.delete\(',
        r'execute.*DELETE',
    ]
    
    found_issues = []
    
    files_to_check = [
        'app.py',
        'services/supabase_client.py',
        'core/alarms.py',
    ]
    
    for filepath in files_to_check:
        try:
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    content = f.read()
                    for pattern in dangerous_sql_patterns:
                        matches = re.findall(pattern, content, re.IGNORECASE)
                        if matches:
                            found_issues.append(f"{filepath}: contains dangerous pattern '{pattern}'")
        except:
            pass
    
    return {
        'safe': len(found_issues) == 0,
        'issues': found_issues
    }
