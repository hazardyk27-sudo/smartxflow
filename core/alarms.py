"""
Smart Money Alarm System
6 alarm types with priority ordering
Configurable thresholds from config/alarm_thresholds.py

SHARP SYSTEM (v2.1):
- 4 ana kriter ile profesyonel sharp tespiti
- Market hacmi filtresi (1X2: 5000, O/U: 3000, BTTS: 2000 GBP)
- Sharp Skor: 0-100 arası hesaplama
- 70+ = Sharp alarmı (gösterim: "Sharp 86/100")
- 40-69 = Orta Seviye (alarm yok, UI'da "Sharp Skor: 58/100 (orta seviye)" göster)
- <40 = Yok say
"""

from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from collections import defaultdict

try:
    from core.config.alarm_thresholds import ALARM_CONFIG, get_threshold, WINDOW_MINUTES, LOOKBACK_MINUTES
    from core.timezone import now_turkey, now_turkey_iso, format_time_only, TURKEY_TZ
    from core.alarm_state import should_fire_alarm, record_alarm_fired, cleanup_old_alarm_states
    from core.real_sharp import detect_sharp, SharpDetector
    from core.dropping_alert import detect_dropping_alerts, DroppingAlertDetector, DROP_THRESHOLD_PERCENT
    from core.reversal_move import detect_reversal_move, apply_reversal_effects, ReversalMoveDetector
    from core.momentum_spike import check_momentum_spike_for_match, detect_momentum_spike
    from core.line_freeze import check_line_freeze_for_match, detect_line_freeze, LineFreezeDetector
    from core.volume_shift import check_volume_shift_for_match, detect_volume_shift, VolumeShiftDetector
    from core.alarm_config import (
        get_sharp_config, get_dropping_config, get_reversal_config,
        get_momentum_config, get_line_freeze_config, get_volume_shift_config,
        get_big_money_config, get_public_surge_config
    )
except ImportError:
    try:
        from config.alarm_thresholds import ALARM_CONFIG, get_threshold, WINDOW_MINUTES, LOOKBACK_MINUTES
        from real_sharp import detect_sharp, SharpDetector
        from dropping_alert import detect_dropping_alerts, DroppingAlertDetector, DROP_THRESHOLD_PERCENT
        from reversal_move import detect_reversal_move, apply_reversal_effects, ReversalMoveDetector
        from momentum_spike import check_momentum_spike_for_match, detect_momentum_spike
        from line_freeze import check_line_freeze_for_match, detect_line_freeze, LineFreezeDetector
        from volume_shift import check_volume_shift_for_match, detect_volume_shift, VolumeShiftDetector
        from alarm_config import (
            get_sharp_config, get_dropping_config, get_reversal_config,
            get_momentum_config, get_line_freeze_config, get_volume_shift_config,
            get_big_money_config, get_public_surge_config
        )
    except ImportError:
        detect_sharp = None
        SharpDetector = None
        detect_dropping_alerts = None
        DroppingAlertDetector = None
        detect_reversal_move = None
        apply_reversal_effects = None
        ReversalMoveDetector = None
        check_momentum_spike_for_match = None
        detect_momentum_spike = None
        check_line_freeze_for_match = None
        detect_line_freeze = None
        LineFreezeDetector = None
        check_volume_shift_for_match = None
        detect_volume_shift = None
        VolumeShiftDetector = None
        DROP_THRESHOLD_PERCENT = 7.0
        
        class _DummyConfig:
            enabled = True
        def get_sharp_config(): return _DummyConfig()
        def get_dropping_config(): return _DummyConfig()
        def get_reversal_config(): return _DummyConfig()
        def get_momentum_config(): return _DummyConfig()
        def get_line_freeze_config(): return _DummyConfig()
        def get_volume_shift_config(): return _DummyConfig()
        def get_big_money_config(): return _DummyConfig()
        def get_public_surge_config(): return _DummyConfig()
        
    import pytz
    TURKEY_TZ = pytz.timezone('Europe/Istanbul')
    def now_turkey():
        return datetime.now(TURKEY_TZ)
    def now_turkey_iso():
        return now_turkey().isoformat()
    def format_time_only(ts):
        return ts[-5:] if ts else ''
    def should_fire_alarm(*args, **kwargs):
        return True, "no_state_module"
    def record_alarm_fired(*args, **kwargs):
        pass
    def cleanup_old_alarm_states(*args, **kwargs):
        pass

ALARM_TYPES = {
    'reversal_move': {
        'name': 'Reversal Move',
        'icon': '🔄',
        'color': '#ef4444',
        'priority': 1,
        'description': 'Trend tersine döndü. Drop sonrası fiyat geri dönüşü + momentum değişimi.',
        'critical': True
    },
    'sharp': {
        'name': 'Sharp',
        'icon': '🟢',
        'color': '#22c55e',
        'priority': 2,
        'description': 'Sharp: 4 kriter + market hacmi filtresi sağlandı. Skor 70+.',
        'critical': True
    },
    'medium_movement': {
        'name': 'Orta Hareket',
        'icon': '🔶',
        'color': '#f97316',
        'priority': 9,
        'description': 'Orta Seviye Hareket: Sharp skor 40-69 arası. Kriterlerin bir kısmı sağlandı.',
        'critical': False
    },
    'big_money': {
        'name': 'Big Money Move',
        'icon': '💰',
        'color': '#f59e0b',
        'priority': 3,
        'description': 'Çok kısa sürede yüksek para akışı.',
        'critical': True
    },
    'dropping': {
        'name': 'Dropping Alert',
        'icon': '📉',
        'color': '#ef4444',
        'priority': 4,
        'description': 'Açılıştan bu yana 30dk+ kalıcı oran düşüşü.',
        'critical': True
    },
    'dropping_l1': {
        'name': 'Dropping L1',
        'icon': '📉',
        'color': '#f59e0b',
        'priority': 4,
        'description': 'Dropping Level 1: 7-10% drop, 30dk+ kalıcı.',
        'critical': True
    },
    'dropping_l2': {
        'name': 'Dropping L2',
        'icon': '📉',
        'color': '#ef4444',
        'priority': 4,
        'description': 'Dropping Level 2: 10-15% drop, 30dk+ kalıcı.',
        'critical': True
    },
    'dropping_l3': {
        'name': 'Dropping L3',
        'icon': '📉',
        'color': '#dc2626',
        'priority': 4,
        'description': 'Dropping Level 3: 15%+ drop, 30dk+ kalıcı.',
        'critical': True
    },
    'dropping_preview': {
        'name': 'Dropping Preview',
        'icon': '📊',
        'color': '#6b7280',
        'priority': 20,
        'description': 'Oran düşüşü başladı, 30dk dolmadı (preview).',
        'critical': False
    },
    'line_freeze': {
        'name': 'Line Freeze',
        'icon': '🔵',
        'color': '#3b82f6',
        'priority': 5,
        'description': 'Şirket risk yönetimi. Para gelmesine rağmen oran donuk.',
        'critical': False
    },
    'line_freeze_l1': {
        'name': 'Freeze L1',
        'icon': '🔵',
        'color': '#60a5fa',
        'priority': 6,
        'description': 'Soft Freeze: 20dk+ donuk + (£1.5k+ veya %6+ share).',
        'critical': False
    },
    'line_freeze_l2': {
        'name': 'Freeze L2',
        'icon': '🔵',
        'color': '#3b82f6',
        'priority': 5,
        'description': 'Hard Freeze: 20dk+ donuk + %4+ share + market hareketli.',
        'critical': True
    },
    'line_freeze_l3': {
        'name': 'Freeze L3',
        'icon': '🔵',
        'color': '#1d4ed8',
        'priority': 4,
        'description': 'Critical Freeze: 40dk+ donuk + %8+ share + £3k+.',
        'critical': True
    },
    'public_surge': {
        'name': 'Public Money Surge',
        'icon': '🟡',
        'color': '#eab308',
        'priority': 6,
        'description': 'Halk yüklenmesi. Para artıyor, oran sabit.',
        'critical': False
    },
    'momentum': {
        'name': 'Momentum Spike',
        'icon': '🟣',
        'color': '#a855f7',
        'priority': 7,
        'description': 'Trend oluşumu. Sürekli aynı yöne para akışı.',
        'critical': False
    },
    'volume_shift': {
        'name': 'Volume Shift',
        'icon': '📊',
        'color': '#0ea5e9',
        'priority': 2,
        'description': 'Lider değişimi. %50+ dominant seçenek değişti + hacim eşiği karşılandı.',
        'critical': True
    },
    'momentum_spike': {
        'name': 'Momentum Spike',
        'icon': '🚀',
        'color': '#a855f7',
        'priority': 2,
        'description': 'Hacim spike: Son 10dk hacmi, önceki 30dk ortalamasının 3+ katı.',
        'critical': True
    },
    'momentum_spike_l1': {
        'name': 'Spike L1',
        'icon': '🚀',
        'color': '#a855f7',
        'priority': 3,
        'description': 'Momentum Spike L1: £1.5k-3k new money (2/4 kriter).',
        'critical': False
    },
    'momentum_spike_l2': {
        'name': 'Spike L2',
        'icon': '🚀',
        'color': '#7c3aed',
        'priority': 2,
        'description': 'Momentum Spike L2: £3k-5k new money (2/4 kriter).',
        'critical': True
    },
    'momentum_spike_l3': {
        'name': 'Spike L3',
        'icon': '🚀',
        'color': '#5b21b6',
        'priority': 1,
        'description': 'Momentum Spike L3: £5k+ new money (2/4 kriter).',
        'critical': True
    }
}

def parse_money(val: Any) -> float:
    if not val:
        return 0.0
    try:
        return float(str(val).replace(',', '').replace('£', '').replace(' ', ''))
    except:
        return 0.0

def parse_odds(val: Any) -> float:
    if not val or val == '-':
        return 0.0
    try:
        s = str(val).split('\n')[0].replace(',', '.')
        return float(s)
    except:
        return 0.0

def parse_pct(val: Any) -> float:
    if not val:
        return 0.0
    try:
        return float(str(val).replace('%', '').replace(',', '.').strip())
    except:
        return 0.0

def calculate_smart_score(money_diff: float, odds_drop: float, pct: float) -> int:
    score = 0
    if money_diff >= 5000:
        score += 40
    elif money_diff >= 3000:
        score += 30
    elif money_diff >= 1500:
        score += 20
    elif money_diff >= 500:
        score += 10
    
    if odds_drop >= 0.30:
        score += 35
    elif odds_drop >= 0.20:
        score += 25
    elif odds_drop >= 0.15:
        score += 20
    elif odds_drop >= 0.10:
        score += 15
    elif odds_drop >= 0.05:
        score += 10
    
    if pct >= 90:
        score += 25
    elif pct >= 80:
        score += 20
    elif pct >= 70:
        score += 15
    elif pct >= 60:
        score += 10
    
    return min(100, score)

def parse_timestamp(ts: str) -> Optional[datetime]:
    """Parse timestamp string to datetime object"""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace('Z', '+00:00').split('+')[0])
    except:
        return None

def find_window_pairs(history: List[Dict], window_minutes: int = 10) -> List[tuple]:
    """
    Find all valid base-target pairs where target is ~window_minutes after base.
    Returns list of (base_index, target_index) tuples.
    """
    pairs = []
    if len(history) < 2:
        return pairs
    
    for i in range(len(history)):
        base_ts = parse_timestamp(history[i].get('ScrapedAt', ''))
        if not base_ts:
            continue
        
        for j in range(i + 1, len(history)):
            target_ts = parse_timestamp(history[j].get('ScrapedAt', ''))
            if not target_ts:
                continue
            
            diff_minutes = (target_ts - base_ts).total_seconds() / 60
            if diff_minutes >= window_minutes:
                pairs.append((i, j))
                break
    
    return pairs

def filter_history_before_kickoff(history: List[Dict], match_date_str: str) -> List[Dict]:
    """
    Filter history records to only include data BEFORE match kickoff.
    
    CRITICAL: Scraper doesn't collect live data, so any data after kickoff
    is stale/invalid and should not be used for alarm detection.
    
    Uses proper datetime comparison to avoid string comparison issues.
    
    Args:
        history: List of history records with ScrapedAt field
        match_date_str: Match date in format "DD.Mon HH:MM:SS" or "DD.MonHH:MM:SS" (Turkey time)
    
    Returns:
        Filtered history with only pre-kickoff data
    """
    try:
        from core.timezone import parse_match_datetime, parse_to_turkey
        import pytz
        
        kickoff_tr = parse_match_datetime(match_date_str)
        if not kickoff_tr:
            return history
        
        kickoff_utc = kickoff_tr.astimezone(pytz.UTC)
        
        filtered = []
        for record in history:
            scraped_at = record.get('ScrapedAt', '')
            if not scraped_at:
                continue
            
            try:
                scraped_dt = parse_to_turkey(scraped_at)
                scraped_utc = scraped_dt.astimezone(pytz.UTC)
                
                if scraped_utc < kickoff_utc:
                    filtered.append(record)
            except Exception:
                filtered.append(record)
        
        return filtered if filtered else history[:1]
        
    except Exception as e:
        print(f"[Alarm] Error filtering history: {e}")
        return history


def analyze_match_alarms(history: List[Dict], market: str, match_id: str = None, match_date: str = None) -> List[Dict]:
    """
    Analyze all 10-minute windows in match history for alarms.
    Scans entire history (up to LOOKBACK_MINUTES) looking for alarm conditions
    in every 10-minute window, not just the most recent one.
    
    CRITICAL: Only analyzes data BEFORE match kickoff time.
    
    Includes deduplication: Same movement won't trigger multiple alarms.
    
    Args:
        history: Match history records
        market: Market type (moneyway_1x2, etc.)
        match_id: Optional match identifier
        match_date: Match kickoff date/time string (Turkey time) for filtering
    """
    if len(history) < 2:
        return []
    
    if match_date:
        original_count = len(history)
        history = filter_history_before_kickoff(history, match_date)
        if len(history) != original_count:
            print(f"[Alarm] Filtered history: {original_count} -> {len(history)} (removed post-kickoff data)")
    
    if len(history) < 2:
        return []
    
    if market in ['moneyway_1x2', 'dropping_1x2']:
        sides = [
            {'key': '1', 'amt': 'Amt1', 'odds': 'Odds1', 'pct': 'Pct1'},
            {'key': 'X', 'amt': 'AmtX', 'odds': 'OddsX', 'pct': 'PctX'},
            {'key': '2', 'amt': 'Amt2', 'odds': 'Odds2', 'pct': 'Pct2'}
        ]
    elif market in ['moneyway_ou25', 'dropping_ou25']:
        sides = [
            {'key': 'Under', 'amt': 'AmtUnder', 'odds': 'Under', 'pct': 'PctUnder'},
            {'key': 'Over', 'amt': 'AmtOver', 'odds': 'Over', 'pct': 'PctOver'}
        ]
    elif market in ['moneyway_btts', 'dropping_btts']:
        sides = [
            {'key': 'Yes', 'amt': 'AmtYes', 'odds': 'OddsYes', 'pct': 'PctYes'},
            {'key': 'No', 'amt': 'AmtNo', 'odds': 'OddsNo', 'pct': 'PctNo'}
        ]
    else:
        return []
    
    detected_alarms = []
    seen_alarms = set()
    first = history[0] if history else None
    current = history[-1]
    
    if not match_id:
        home = current.get('Home', '')
        away = current.get('Away', '')
        league = current.get('League', '')
        date = current.get('Date', '')
        match_id = f"{home}|{away}|{league}|{date}"
    
    drop_config = ALARM_CONFIG.get('dropping', {})
    surge_config = ALARM_CONFIG.get('public_surge', {})
    
    surge_min_money = surge_config.get('min_money_diff', 500)
    surge_max_odds = surge_config.get('max_odds_change', 0.02)
    
    sharp_results_raw = []
    dropping_alerts_raw = []
    reversal_alerts = []
    
    reversal_cfg = get_reversal_config()
    if detect_reversal_move is not None and reversal_cfg and reversal_cfg.enabled:
        try:
            reversal_alerts = detect_reversal_move(
                history=history,
                market=market,
                match_id=match_id,
                home=current.get('Home', ''),
                away=current.get('Away', '')
            )
            
            for rev in reversal_alerts:
                if not rev.get('is_alarm', False):
                    continue
                
                alarm_key = ('reversal_move', rev['side'], f"{rev['opening_odds']:.2f}")
                if alarm_key not in seen_alarms:
                    seen_alarms.add(alarm_key)
                    detected_alarms.append({
                        'type': 'reversal_move',
                        'side': rev['side'],
                        'opening_odds': rev['opening_odds'],
                        'lowest_odds': rev['lowest_odds'],
                        'current_odds': rev['current_odds'],
                        'odds_from': rev['lowest_odds'],
                        'odds_to': rev['current_odds'],
                        'drop_percent': rev['drop_percent'],
                        'reversal_percent': rev['reversal_percent'],
                        'conditions_met': rev['conditions_met'],
                        'is_alarm': True,
                        'criteria': rev['criteria'],
                        'criteria_text': rev['criteria_text'],
                        'timestamp': rev['timestamp']
                    })
        except Exception as e:
            print(f"[Reversal] Error in detection: {e}")
    
    sharp_cfg = get_sharp_config()
    if detect_sharp is not None and sharp_cfg and sharp_cfg.enabled:
        try:
            sharp_results = detect_sharp(history, market, match_id)
            for sharp in sharp_results:
                if sharp.get('is_sharp', False):
                    alarm_key = ('sharp', sharp['side'], f"{sharp['odds_from']:.2f}-{sharp['odds_to']:.2f}")
                    if alarm_key not in seen_alarms:
                        seen_alarms.add(alarm_key)
                        detected_alarms.append({
                            'type': 'sharp',
                            'side': sharp['side'],
                            'money_diff': sharp['money_diff'],
                            'odds_from': sharp['odds_from'],
                            'odds_to': sharp['odds_to'],
                            'window_start': sharp['window_start'],
                            'window_end': sharp['window_end'],
                            'timestamp': sharp['timestamp'],
                            'is_sharp': True,
                            'sharp_score': sharp['sharp_score'],
                            'volume_shock': sharp['volume_shock'],
                            'market_share': sharp['market_share'],
                            'odds_drop_percent': sharp['odds_drop_percent'],
                            'share_shift_points': sharp['share_shift_points'],
                            'criteria': sharp['criteria'],
                            'raw_data': sharp['raw_data'],
                            'market_volume': sharp.get('market_volume', 0)
                        })
        except Exception as e:
            print(f"[Sharp] Error in detection: {e}")
    
    window_pairs = find_window_pairs(history, WINDOW_MINUTES)
    
    public_surge_cfg = get_public_surge_config()
    for base_idx, target_idx in window_pairs:
        base = history[base_idx]
        target = history[target_idx]
        base_ts = base.get('ScrapedAt', '')
        target_ts = target.get('ScrapedAt', '')
        
        for side in sides:
            base_amt = parse_money(base.get(side['amt'], 0))
            target_amt = parse_money(target.get(side['amt'], 0))
            base_odds = parse_odds(base.get(side['odds'], 0))
            target_odds = parse_odds(target.get(side['odds'], 0))
            target_pct = parse_pct(target.get(side['pct'], 0))
            
            money_diff = target_amt - base_amt
            odds_diff = target_odds - base_odds
            
            odds_flat = abs(odds_diff) <= surge_max_odds
            if public_surge_cfg and public_surge_cfg.enabled and money_diff >= surge_min_money and odds_flat:
                odds_bucket = f"{base_odds:.2f}-{target_odds:.2f}"
                alarm_key_surge = ('public_surge', side['key'], odds_bucket)
                if alarm_key_surge not in seen_alarms:
                    seen_alarms.add(alarm_key_surge)
                    detected_alarms.append({
                        'type': 'public_surge',
                        'side': side['key'],
                        'money_diff': money_diff,
                        'odds_from': base_odds,
                        'odds_to': target_odds,
                        'window_start': base_ts,
                        'window_end': target_ts,
                        'timestamp': target_ts
                    })
    
    dropping_cfg = get_dropping_config()
    if detect_dropping_alerts and first and dropping_cfg and dropping_cfg.enabled:
        real_alerts, preview_alerts = detect_dropping_alerts(
            history=history,
            market=market,
            match_id=match_id,
            home=home,
            away=away
        )
        
        for drop_alert in real_alerts:
            first_ts = first.get('ScrapedAt', '') if first else ''
            curr_ts = current.get('ScrapedAt', now_turkey_iso())
            level = drop_alert.get('dropping_level', 1)
            alarm_type = f"dropping_l{level}" if level > 0 else 'dropping'
            alarm_key = (alarm_type, drop_alert['side'], first_ts[:13] if first_ts else '')
            
            if alarm_key not in seen_alarms:
                seen_alarms.add(alarm_key)
                detected_alarms.append({
                    'type': alarm_type,
                    'side': drop_alert['side'],
                    'money_diff': drop_alert['selection_volume'],
                    'selection_volume': drop_alert['selection_volume'],
                    'odds_from': drop_alert['opening_odds'],
                    'odds_to': drop_alert['current_odds'],
                    'total_drop': drop_alert['drop_value'],
                    'drop_percent': drop_alert['drop_percent'],
                    'dropping_sides_count': drop_alert['dropping_sides_count'],
                    'dropping_level': level,
                    'persisted_minutes': drop_alert.get('persisted_minutes', 30),
                    'window_start': first_ts,
                    'window_end': curr_ts,
                    'timestamp': curr_ts
                })
    
    big_money_cfg = get_big_money_config()
    big_money_result = check_big_money_all_windows(history, sides, WINDOW_MINUTES) if big_money_cfg and big_money_cfg.enabled else []
    for result in big_money_result:
        alarm_key = ('big_money', result['key'], result.get('window_start', '')[:16])
        if alarm_key not in seen_alarms:
            window_start = result.get('window_start', '')
            window_end = result.get('window_end', '')
            total_inflow = result['total_inflow']
            seen_alarms.add(alarm_key)
            detected_alarms.append({
                'type': 'big_money',
                'side': result['key'],
                'money_diff': total_inflow,
                'total_diff': total_inflow,
                'time_window': f'{WINDOW_MINUTES} dakika',
                'window_start': window_start,
                'window_end': window_end,
                'timestamp': window_end or current.get('ScrapedAt', now_turkey_iso())
            })
    
    if len(history) >= 4:
        for side in sides:
            momentum_result = check_momentum(history[-6:] if len(history) >= 6 else history, [side])
            if momentum_result:
                alarm_key = ('momentum', side['key'])
                if alarm_key not in seen_alarms:
                    seen_alarms.add(alarm_key)
                    detected_alarms.append({
                        'type': 'momentum',
                        'side': momentum_result['key'],
                        'money_diff': momentum_result['total_diff'],
                        'timestamp': current.get('ScrapedAt', now_turkey_iso())
                    })
    
    line_freeze_cfg = get_line_freeze_config()
    if len(history) >= 3 and check_line_freeze_for_match is not None and line_freeze_cfg and line_freeze_cfg.enabled:
        home = current.get('Home', '')
        away = current.get('Away', '')
        side_keys = [s['key'] for s in sides]
        line_freezes = check_line_freeze_for_match(history, market, home, away, side_keys)
        for freeze in line_freezes:
            level = freeze.get('freeze_level', 1)
            alarm_key = ('line_freeze', freeze.get('side', ''), level)
            if alarm_key not in seen_alarms:
                seen_alarms.add(alarm_key)
                alarm_type = f"line_freeze_l{level}" if level in [1, 2, 3] else 'line_freeze'
                detected_alarms.append({
                    'type': alarm_type,
                    'side': freeze.get('side', ''),
                    'freeze_level': level,
                    'freeze_duration': freeze.get('freeze_duration', 0),
                    'new_money': freeze.get('new_money', 0),
                    'share_now': freeze.get('share_now', 0),
                    'detail': freeze.get('detail', ''),
                    'timestamp': current.get('ScrapedAt', now_turkey_iso())
                })
    
    
    momentum_cfg = get_momentum_config()
    if len(history) >= 4 and check_momentum_spike_for_match is not None and momentum_cfg and momentum_cfg.enabled:
        home = current.get('Home', '')
        away = current.get('Away', '')
        side_keys = [s['key'] for s in sides]
        momentum_spikes = check_momentum_spike_for_match(history, market, home, away, side_keys)
        for spike in momentum_spikes:
            level = spike.get('momentum_level', 1)
            alarm_key = ('momentum_spike', spike.get('side', ''), level)
            if alarm_key not in seen_alarms:
                seen_alarms.add(alarm_key)
                alarm_type = f"momentum_spike_l{level}" if level in [1, 2, 3] else 'momentum_spike'
                detected_alarms.append({
                    'type': alarm_type,
                    'side': spike.get('side', ''),
                    'momentum_level': level,
                    'spike_ratio': spike.get('spike_ratio', 0),
                    'share_shift': spike.get('share_shift', 0),
                    'd4_volume': spike.get('d4_volume', 0),
                    'baseline_10': spike.get('baseline_10', 0),
                    'detail': spike.get('detail', ''),
                    'timestamp': current.get('ScrapedAt', now_turkey_iso())
                })
    
    volume_shift_cfg = get_volume_shift_config()
    if len(history) >= 2 and check_volume_shift_for_match is not None and volume_shift_cfg and volume_shift_cfg.enabled:
        home = current.get('Home', '')
        away = current.get('Away', '')
        volume_shifts = check_volume_shift_for_match(history, market, home, away)
        for vs in volume_shifts:
            alarm_key = ('volume_shift', vs.get('current_leader', ''), market)
            if alarm_key not in seen_alarms:
                seen_alarms.add(alarm_key)
                detected_alarms.append({
                    'type': 'volume_shift',
                    'side': vs.get('current_leader', ''),
                    'previous_leader': vs.get('previous_leader', ''),
                    'current_leader': vs.get('current_leader', ''),
                    'previous_share': vs.get('previous_share', 0),
                    'current_share': vs.get('current_share', 0),
                    'new_money_market': vs.get('new_money_market', 0),
                    'detail': vs.get('detail', ''),
                    'timestamp': current.get('ScrapedAt', now_turkey_iso())
                })
    
    detected_alarms.sort(key=lambda x: (ALARM_TYPES[x['type']]['priority'], x.get('timestamp', '')), reverse=False)
    
    return detected_alarms

def check_big_money_all_windows(history: List[Dict], sides: List[Dict], window_minutes: int = 10) -> List[Dict]:
    """
    Big Money: Tum 10 dakikalik pencerelerde 15.000 £+ para girisini kontrol et.
    Her pencere icin ayri alarm uretir.
    """
    config = ALARM_CONFIG.get('big_money', {})
    min_inflow = config.get('min_money_inflow', 15000)
    
    if len(history) < 2:
        return []
    
    results = []
    window_pairs = find_window_pairs(history, window_minutes)
    
    for base_idx, target_idx in window_pairs:
        base = history[base_idx]
        target = history[target_idx]
        base_ts = base.get('ScrapedAt', '')
        target_ts = target.get('ScrapedAt', '')
        
        for side in sides:
            total_inflow = 0
            for i in range(base_idx, target_idx + 1):
                if i == 0:
                    continue
                curr_amt = parse_money(history[i].get(side['amt'], 0))
                prev_amt = parse_money(history[i-1].get(side['amt'], 0))
                diff = curr_amt - prev_amt
                if diff > 0:
                    total_inflow += diff
            
            if total_inflow >= min_inflow:
                results.append({
                    'key': side['key'],
                    'total_inflow': total_inflow,
                    'time_window': window_minutes,
                    'window_start': base_ts,
                    'window_end': target_ts
                })
    
    return results

def check_big_money_10min(history: List[Dict], sides: List[Dict]) -> Optional[Dict]:
    """
    Big Money: 10 dakika icinde 15.000 £+ para girisi
    Oran sarti yok, sadece hacim onemli
    (Geriye uyumluluk icin korundu)
    """
    config = ALARM_CONFIG.get('big_money', {})
    min_inflow = config.get('min_money_inflow', 15000)
    time_window = config.get('time_window_minutes', 10)
    
    if len(history) < 2:
        return None
    
    current_time = None
    try:
        current_ts = history[-1].get('ScrapedAt', '')
        if current_ts:
            current_time = datetime.fromisoformat(current_ts.replace('Z', '+00:00').split('+')[0])
    except:
        pass
    
    for side in sides:
        total_inflow = 0
        
        for i in range(len(history) - 1, 0, -1):
            try:
                record_ts = history[i].get('ScrapedAt', '')
                if record_ts and current_time:
                    record_time = datetime.fromisoformat(record_ts.replace('Z', '+00:00').split('+')[0])
                    diff_minutes = (current_time - record_time).total_seconds() / 60
                    if diff_minutes > time_window:
                        break
            except:
                pass
            
            curr_amt = parse_money(history[i].get(side['amt'], 0))
            prev_amt = parse_money(history[i-1].get(side['amt'], 0))
            diff = curr_amt - prev_amt
            if diff > 0:
                total_inflow += diff
        
        if total_inflow >= min_inflow:
            return {
                'key': side['key'],
                'total_inflow': total_inflow,
                'time_window': time_window
            }
    
    return None

def check_momentum(history: List[Dict], sides: List[Dict]) -> Optional[Dict]:
    config = ALARM_CONFIG.get('momentum', {})
    consecutive_needed = config.get('consecutive_count', 3)
    min_diff = config.get('min_total_diff', 1000)
    
    for side in sides:
        consecutive_increase = 0
        total_diff = 0
        for i in range(1, len(history)):
            curr_amt = parse_money(history[i].get(side['amt'], 0))
            prev_amt = parse_money(history[i-1].get(side['amt'], 0))
            if curr_amt > prev_amt:
                consecutive_increase += 1
                total_diff += (curr_amt - prev_amt)
            else:
                consecutive_increase = 0
                total_diff = 0
        
        if consecutive_increase >= consecutive_needed and total_diff >= min_diff:
            return {'key': side['key'], 'total_diff': total_diff}
    
    return None


def group_alarms_by_match(alarms: List[Dict]) -> List[Dict]:
    grouped = defaultdict(lambda: defaultdict(list))
    match_info = {}
    
    for alarm in alarms:
        home = alarm.get('home', '')
        away = alarm.get('away', '')
        key = (home, away)
        alarm_type = alarm.get('type', '')
        grouped[key][alarm_type].append(alarm)
        if key not in match_info:
            match_info[key] = {
                'league': alarm.get('league', ''),
                'date': alarm.get('date', '')
            }
    
    result = []
    for (home, away), type_alarms in grouped.items():
        info = match_info.get((home, away), {})
        league = info.get('league', '')
        date = info.get('date', '')
        match_id = f"{home}|{away}|{league}|{date}"
        
        for alarm_type, events in type_alarms.items():
            events.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            
            is_dropping_type = alarm_type.startswith('dropping')
            
            if is_dropping_type:
                max_money = max((e.get('selection_volume', e.get('money_diff', 0)) for e in events), default=0)
                max_drop = max((e.get('total_drop', 0) for e in events), default=0)
                max_drop_percent = max((e.get('drop_percent', 0) for e in events), default=0)
                unique_sides = set(e.get('side', '') for e in events if e.get('drop_percent', 0) >= 7)
                dropping_sides_count = len(unique_sides) if unique_sides else 1
                dropping_level = max((e.get('dropping_level', 0) for e in events), default=0)
                persisted_minutes = max((e.get('persisted_minutes', 0) for e in events), default=0)
                sharp_score = 0
            elif alarm_type in ['sharp', 'medium_movement']:
                max_money = max((e.get('money_diff', 0) for e in events), default=0)
                max_drop = max((e.get('total_drop', 0) for e in events), default=0)
                max_drop_percent = 0
                dropping_sides_count = 0
                dropping_level = 0
                persisted_minutes = 0
                sharp_score = max((e.get('sharp_score', 0) for e in events), default=0)
            else:
                max_money = max((e.get('money_diff', 0) for e in events), default=0)
                max_drop = max((e.get('total_drop', 0) for e in events), default=0)
                max_drop_percent = 0
                dropping_sides_count = 0
                dropping_level = 0
                persisted_minutes = 0
                sharp_score = 0
            
            result.append({
                'home': home,
                'away': away,
                'league': league,
                'date': date,
                'match_id': match_id,
                'type': alarm_type,
                'count': len(events),
                'latest': events[0],
                'events': events,
                'max_money': max_money,
                'max_drop': max_drop,
                'max_drop_percent': max_drop_percent,
                'dropping_sides_count': dropping_sides_count,
                'dropping_level': dropping_level,
                'persisted_minutes': persisted_minutes,
                'sharp_score': sharp_score,
                'priority': ALARM_TYPES.get(alarm_type, {}).get('priority', 99)
            })
    
    result.sort(key=lambda x: (x['priority'], -x['count']))
    return result

def get_critical_alarms(alarms: List[Dict], limit: int = 4) -> List[Dict]:
    if not alarms:
        return []
    
    sorted_alarms = sorted(alarms, key=lambda x: (
        ALARM_TYPES.get(x.get('type', ''), {}).get('priority', 99),
        -x.get('money_diff', 0)
    ))
    return sorted_alarms[:limit]

def format_alarm_for_ticker(alarm: Dict, home: str, away: str) -> Dict:
    alarm_info = ALARM_TYPES.get(alarm['type'], {})
    money_diff = alarm.get('money_diff', 0)
    
    return {
        'type': alarm['type'],
        'icon': alarm_info.get('icon', ''),
        'name': alarm_info.get('name', ''),
        'color': alarm_info.get('color', '#fff'),
        'home': home,
        'away': away,
        'side': alarm.get('side', ''),
        'money_text': f"+£{int(money_diff):,}" if money_diff > 0 else '',
        'odds_from': alarm.get('odds_from'),
        'odds_to': alarm.get('odds_to'),
        'priority': alarm_info.get('priority', 99),
        'critical': alarm_info.get('critical', False),
        'timestamp': alarm.get('timestamp', '')
    }

def format_alarm_for_modal(alarm: Dict) -> Dict:
    alarm_info = ALARM_TYPES.get(alarm['type'], {})
    money_diff = alarm.get('money_diff', 0)
    
    detail_text = ''
    if alarm['type'] == 'sharp':
        if alarm.get('odds_from') and alarm.get('odds_to'):
            detail_text = f"+£{int(money_diff):,} — Oran {alarm['odds_from']:.2f} → {alarm['odds_to']:.2f}"
        else:
            detail_text = f"+£{int(money_diff):,}"
    elif alarm['type'] == 'reversal_move':
        reversal_pct = alarm.get('reversal_percent', 0)
        conditions = alarm.get('conditions_met', 0)
        criteria_text = alarm.get('criteria_text', '')
        detail_text = f"Trend tersine döndü — {conditions}/3 kriter | {criteria_text}"
    elif alarm['type'] == 'big_money':
        detail_text = f"+£{int(money_diff):,} (son scrape)"
    elif alarm['type'].startswith('dropping'):
        drop_value = alarm.get('total_drop', 0)
        drop_percent = alarm.get('drop_percent', 0)
        selection_volume = alarm.get('selection_volume', alarm.get('money_diff', 0))
        dropping_count = alarm.get('dropping_sides_count', 1)
        dropping_level = alarm.get('dropping_level', 0)
        persisted_minutes = alarm.get('persisted_minutes', 0)
        xn_text = f"x{dropping_count}" if dropping_count > 1 else ""
        level_text = f"L{dropping_level}" if dropping_level > 0 else ""
        persistence_text = "(30dk+ kalıcı)" if persisted_minutes >= 30 else f"({int(persisted_minutes)}dk)"
        detail_text = f"{xn_text} {level_text} {drop_value:.2f} drop (-{drop_percent:.1f}%) {persistence_text} — £{int(selection_volume):,}".strip()
    elif alarm['type'] == 'public_surge':
        detail_text = f"Para artıyor (+£{int(money_diff):,}), oran sabit."
    elif alarm['type'] == 'momentum':
        detail_text = f"+£{int(money_diff):,} sürekli akış."
    elif alarm['type'].startswith('line_freeze'):
        freeze_duration = alarm.get('freeze_duration', 0)
        new_money = alarm.get('new_money', 0)
        share_now = alarm.get('share_now', 0)
        freeze_level = alarm.get('freeze_level', 0)
        if alarm.get('detail'):
            detail_text = alarm.get('detail')
        else:
            level_names = {1: 'Soft', 2: 'Hard', 3: 'Critical'}
            level_name = level_names.get(freeze_level, '')
            detail_text = f"L{freeze_level} {level_name} Freeze ({freeze_duration}dk, £{int(new_money):,}, {share_now:.1f}%)"
    
    return {
        'type': alarm['type'],
        'icon': alarm_info.get('icon', ''),
        'name': alarm_info.get('name', ''),
        'color': alarm_info.get('color', '#fff'),
        'side': alarm.get('side', ''),
        'detail': detail_text,
        'description': alarm_info.get('description', ''),
        'priority': alarm_info.get('priority', 99),
        'timestamp': alarm.get('timestamp', ''),
        'money_diff': money_diff,
        'total_drop': alarm.get('total_drop', 0),
        'money_pct': alarm.get('money_pct', 0),
        'sharp_score': alarm.get('sharp_score', 0),
        'odds_from': alarm.get('odds_from'),
        'odds_to': alarm.get('odds_to')
    }

def format_grouped_alarm(group: Dict) -> Dict:
    alarm_info = ALARM_TYPES.get(group['type'], {})
    latest = group['latest']
    
    formatted_events = [format_alarm_for_modal(e) for e in group['events']]
    latest_detail = formatted_events[0].get('detail', '') if formatted_events else ''
    
    latest_timestamp = latest.get('timestamp', '')
    
    dropping_sides_count = group.get('dropping_sides_count', latest.get('dropping_sides_count', 1))
    drop_percent = group.get('max_drop_percent', latest.get('drop_percent', 0))
    selection_volume = latest.get('selection_volume', latest.get('money_diff', 0))
    sharp_score = group.get('sharp_score', latest.get('sharp_score', 0))
    dropping_level = group.get('dropping_level', latest.get('dropping_level', 0))
    persisted_minutes = group.get('persisted_minutes', latest.get('persisted_minutes', 0))
    
    return {
        'type': group['type'],
        'icon': alarm_info.get('icon', ''),
        'name': alarm_info.get('name', ''),
        'color': alarm_info.get('color', '#fff'),
        'home': group['home'],
        'away': group['away'],
        'league': group.get('league', ''),
        'date': group.get('date', ''),
        'match_id': group.get('match_id', ''),
        'side': latest.get('side', ''),
        'count': group['count'],
        'latest_time': latest_timestamp,
        'timestamp': latest_timestamp,
        'max_money': group['max_money'],
        'max_drop': group['max_drop'],
        'events': formatted_events,
        'priority': group['priority'],
        'critical': alarm_info.get('critical', False),
        'detail': latest_detail,
        'description': alarm_info.get('description', ''),
        'total_drop': latest.get('total_drop', 0),
        'money_diff': latest.get('money_diff', 0),
        'selection_volume': selection_volume,
        'dropping_sides_count': dropping_sides_count,
        'drop_percent': drop_percent,
        'dropping_level': dropping_level,
        'persisted_minutes': persisted_minutes,
        'sharp_score': sharp_score,
        'odds_from': latest.get('odds_from'),
        'odds_to': latest.get('odds_to')
    }


def generate_demo_alarms() -> List[Dict]:
    """Generate demo alarms for ticker when no real alarms exist"""
    demo_matches = [
        {'home': 'Liverpool', 'away': 'Sunderland', 'league': 'English Premier League', 'date': now_turkey().strftime('%d.%m %H:%M')},
        {'home': 'Arsenal', 'away': 'Brentford', 'league': 'English Premier League', 'date': now_turkey().strftime('%d.%m %H:%M')},
        {'home': 'Man Utd', 'away': 'West Ham', 'league': 'English Premier League', 'date': now_turkey().strftime('%d.%m %H:%M')},
        {'home': 'Lazio', 'away': 'AC Milan', 'league': 'Italian Cup', 'date': now_turkey().strftime('%d.%m %H:%M')},
        {'home': 'Leeds', 'away': 'Chelsea', 'league': 'English Premier League', 'date': now_turkey().strftime('%d.%m %H:%M')},
    ]
    
    demo_alarms = [
        {'type': 'sharp', 'side': '1', 'money_diff': 3500, 'odds_from': 1.45, 'odds_to': 1.39, 'sharp_score': 78},
        {'type': 'big_money', 'side': '2', 'money_diff': 18000, 'total_diff': 18000},
        {'type': 'reversal_move', 'side': 'X', 'money_diff': 4200, 'odds_from': 3.80, 'odds_to': 4.10, 'reversal_percent': 65, 'conditions_met': 2, 'criteria_text': 'Retracement: 65% | Momentum: ↓→↑'},
        {'type': 'public_surge', 'side': '1', 'money_diff': 2800, 'odds_from': 1.31, 'odds_to': 1.31},
        {'type': 'momentum', 'side': '2', 'money_diff': 1500},
    ]
    
    result = []
    for i, alarm in enumerate(demo_alarms):
        match = demo_matches[i % len(demo_matches)]
        formatted = format_alarm_for_ticker(alarm, match['home'], match['away'])
        formatted['market'] = 'moneyway_1x2'
        formatted['match_id'] = f"{match['home']}|{match['away']}|{match['league']}|{match['date']}"
        formatted['league'] = match['league']
        formatted['date'] = match['date']
        formatted['timestamp'] = now_turkey_iso()
        result.append(formatted)
    
    return result
