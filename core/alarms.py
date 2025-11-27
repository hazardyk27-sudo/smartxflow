"""
Smart Money Alarm System
6 alarm types with priority ordering
Configurable thresholds from config/alarm_thresholds.py
"""

from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from collections import defaultdict

try:
    from core.config.alarm_thresholds import ALARM_CONFIG, get_threshold
except ImportError:
    from config.alarm_thresholds import ALARM_CONFIG, get_threshold

ALARM_TYPES = {
    'rlm': {
        'name': 'Reverse Line Move',
        'icon': '🔴',
        'color': '#ef4444',
        'priority': 1,
        'description': 'Para arttı, oran yükseldi. Ters yönde piyasa hareketi.',
        'critical': True
    },
    'sharp': {
        'name': 'Sharp Move',
        'icon': '🟢',
        'color': '#22c55e',
        'priority': 2,
        'description': 'Profesyonel yatırımcı girişi.',
        'critical': True
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
        'description': 'Açılıştan bu yana ciddi oran düşüşü.',
        'critical': True
    },
    'line_freeze': {
        'name': 'Line Freeze',
        'icon': '🔵',
        'color': '#3b82f6',
        'priority': 5,
        'description': 'Şirket risk yönetimi. Para gelmesine rağmen oran donuk.',
        'critical': False
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
    'momentum_change': {
        'name': 'Momentum Change',
        'icon': '🔄',
        'color': '#06b6d4',
        'priority': 8,
        'description': 'Dominasyon değişimi. %50+ paya sahip seçenek değişti.',
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

def analyze_match_alarms(history: List[Dict], market: str) -> List[Dict]:
    if len(history) < 2:
        return []
    
    current = history[-1]
    previous = history[-2]
    first = history[0] if history else current
    
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
    
    total_diff = 0
    max_side_diff = 0
    max_side_key = None
    side_changes = []
    
    for side in sides:
        curr_amt = parse_money(current.get(side['amt'], 0))
        prev_amt = parse_money(previous.get(side['amt'], 0))
        curr_odds = parse_odds(current.get(side['odds'], 0))
        prev_odds = parse_odds(previous.get(side['odds'], 0))
        first_odds = parse_odds(first.get(side['odds'], 0))
        curr_pct = parse_pct(current.get(side['pct'], 0))
        
        diff = curr_amt - prev_amt
        odds_change = curr_odds - prev_odds
        total_drop = first_odds - curr_odds if first_odds > 0 else 0
        smart_score = calculate_smart_score(diff, abs(odds_change), curr_pct)
        
        total_diff += max(0, diff)
        if diff > max_side_diff:
            max_side_diff = diff
            max_side_key = side['key']
        
        side_changes.append({
            'key': side['key'],
            'amt_key': side['amt'],
            'odds_key': side['odds'],
            'money_diff': diff,
            'odds_diff': odds_change,
            'curr_odds': curr_odds,
            'prev_odds': prev_odds,
            'first_odds': first_odds,
            'total_drop': total_drop,
            'curr_pct': curr_pct,
            'smart_score': smart_score
        })
    
    detected_alarms = []
    seen_type_side = set()
    timestamp = current.get('ScrapedAt', datetime.now().isoformat())
    
    sharp_config = ALARM_CONFIG.get('sharp_money', {})
    big_config = ALARM_CONFIG.get('big_money', {})
    rlm_config = ALARM_CONFIG.get('rlm', {})
    drop_config = ALARM_CONFIG.get('dropping', {})
    
    sharp_min_money = sharp_config.get('min_money_inflow', 3000)
    sharp_min_drop = sharp_config.get('min_odds_drop', 0.03)
    rlm_min_money = rlm_config.get('min_money_inflow', 3000)
    rlm_min_up = rlm_config.get('min_odds_up', 0.03)
    
    for sc in side_changes:
        money_diff = sc['money_diff']
        odds_diff = sc['odds_diff']
        
        if money_diff >= sharp_min_money and odds_diff < -sharp_min_drop:
            if ('sharp', sc['key']) not in seen_type_side:
                seen_type_side.add(('sharp', sc['key']))
                detected_alarms.append({
                    'type': 'sharp',
                    'side': sc['key'],
                    'money_diff': money_diff,
                    'odds_from': sc['prev_odds'],
                    'odds_to': sc['curr_odds'],
                    'timestamp': timestamp
                })
        
        if money_diff >= rlm_min_money and odds_diff > rlm_min_up:
            if ('rlm', sc['key']) not in seen_type_side:
                seen_type_side.add(('rlm', sc['key']))
                detected_alarms.append({
                    'type': 'rlm',
                    'side': sc['key'],
                    'money_diff': money_diff,
                    'odds_from': sc['prev_odds'],
                    'odds_to': sc['curr_odds'],
                    'timestamp': timestamp
                })
        
        if sc['total_drop'] >= drop_config.get('min_total_drop', 0.30):
            if sc['curr_pct'] >= drop_config.get('min_money_pct', 60):
                if ('dropping', sc['key']) not in seen_type_side:
                    seen_type_side.add(('dropping', sc['key']))
                    detected_alarms.append({
                        'type': 'dropping',
                        'side': sc['key'],
                        'money_diff': money_diff,
                        'odds_from': sc['first_odds'],
                        'odds_to': sc['curr_odds'],
                        'total_drop': sc['total_drop'],
                        'money_pct': sc['curr_pct'],
                        'timestamp': timestamp
                    })
        
        odds_flat = abs(odds_diff) <= 0.02
        if money_diff > 100 and odds_flat:
            if ('public_surge', sc['key']) not in seen_type_side:
                seen_type_side.add(('public_surge', sc['key']))
                detected_alarms.append({
                    'type': 'public_surge',
                    'side': sc['key'],
                    'money_diff': money_diff,
                    'odds_from': sc['prev_odds'],
                    'odds_to': sc['curr_odds'],
                    'timestamp': timestamp
                })
    
    big_money_result = check_big_money_10min(history, sides)
    if big_money_result:
        side_key = big_money_result['key']
        if ('big_money', side_key) not in seen_type_side:
            seen_type_side.add(('big_money', side_key))
            detected_alarms.append({
                'type': 'big_money',
                'side': side_key,
                'money_diff': big_money_result['total_inflow'],
                'total_diff': big_money_result['total_inflow'],
                'time_window': '10 dakika',
                'timestamp': timestamp
            })
    
    if len(history) >= 4:
        for side in sides:
            momentum_result = check_momentum(history[-6:] if len(history) >= 6 else history, [side])
            if momentum_result and ('momentum', side['key']) not in seen_type_side:
                seen_type_side.add(('momentum', side['key']))
                detected_alarms.append({
                    'type': 'momentum',
                    'side': momentum_result['key'],
                    'money_diff': momentum_result['total_diff'],
                    'timestamp': timestamp
                })
    
    if len(history) >= 3:
        for side in sides:
            freeze_result = check_line_freeze(history[-5:] if len(history) >= 5 else history, [side])
            if freeze_result and ('line_freeze', side['key']) not in seen_type_side:
                seen_type_side.add(('line_freeze', side['key']))
                detected_alarms.append({
                    'type': 'line_freeze',
                    'side': freeze_result['key'],
                    'money_diff': freeze_result['total_money'],
                    'timestamp': timestamp
                })
    
    if len(history) >= 2:
        momentum_change_result = check_momentum_change(history, sides)
        if momentum_change_result:
            to_option = momentum_change_result['to_option']
            from_option = momentum_change_result['from_option']
            if ('momentum_change', to_option) not in seen_type_side:
                seen_type_side.add(('momentum_change', to_option))
                detected_alarms.append({
                    'type': 'momentum_change',
                    'side': to_option,
                    'from_option': from_option,
                    'from_pct': momentum_change_result['from_pct'],
                    'to_pct': momentum_change_result['to_pct'],
                    'detail': f"{from_option}→{to_option} ({momentum_change_result['from_pct']:.0f}%→{momentum_change_result['to_pct']:.0f}%)",
                    'timestamp': timestamp
                })
    
    detected_alarms.sort(key=lambda x: ALARM_TYPES[x['type']]['priority'])
    
    return detected_alarms

def check_big_money_10min(history: List[Dict], sides: List[Dict]) -> Optional[Dict]:
    """
    Big Money: 10 dakika icinde 15.000 £+ para girisi
    Oran sarti yok, sadece hacim onemli
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

def check_line_freeze(history: List[Dict], sides: List[Dict]) -> Optional[Dict]:
    config = ALARM_CONFIG.get('line_freeze', {})
    max_change = config.get('max_odds_change', 0.02)
    min_money = config.get('min_money_inflow', 1500)
    
    for side in sides:
        total_money = 0
        odds_stable = True
        first_odds = parse_odds(history[0].get(side.get('odds', ''), 0))
        
        for i in range(1, len(history)):
            curr_amt = parse_money(history[i].get(side['amt'], 0))
            prev_amt = parse_money(history[i-1].get(side['amt'], 0))
            curr_odds = parse_odds(history[i].get(side.get('odds', ''), 0))
            
            total_money += max(0, curr_amt - prev_amt)
            
            if first_odds > 0 and abs(curr_odds - first_odds) > max_change:
                odds_stable = False
                break
        
        if odds_stable and total_money >= min_money:
            return {'key': side['key'], 'total_money': total_money}
    
    return None

def check_momentum_change(history: List[Dict], sides: List[Dict]) -> Optional[Dict]:
    """
    Momentum Change Alarm - Dominasyon Değişimi
    
    Koşullar:
    1. Şu anda bir seçenek %50+ paya sahip olmalı
    2. En yakın önceki %50+ dominant farklı bir seçenek olmalı
    3. Süre sınırı yok - herhangi bir zaman diliminde olabilir
    
    Mantık:
    - Tarihçeyi sondan başa doğru tara
    - Şu anki dominant'ı bul
    - En yakın önceki %50+ dominant'ı bul
    - Sadece bunlar farklıysa alarm tetikle (böylece tekrar tetiklenmez)
    
    Örnek: Saat 13:00'te 1=%63, Saat 22:00'de X=%54 → Alarm!
    """
    config = ALARM_CONFIG.get('momentum_change', {})
    dominance_threshold = config.get('dominance_threshold', 50)
    
    if len(history) < 2:
        return None
    
    def get_dominant(record):
        """Bir kayıttaki %50+ dominant seçeneği bul"""
        best_option = None
        best_pct = 0
        for side in sides:
            pct = parse_pct(record.get(side['pct'], 0))
            if pct > dominance_threshold and pct > best_pct:
                best_option = side['key']
                best_pct = pct
        return best_option, best_pct
    
    current = history[-1]
    current_dominant, current_pct = get_dominant(current)
    
    if not current_dominant:
        return None
    
    previous_dominant = None
    previous_pct = 0
    previous_timestamp = ''
    
    for i in range(len(history) - 2, -1, -1):
        record = history[i]
        dominant, pct = get_dominant(record)
        if dominant:
            previous_dominant = dominant
            previous_pct = pct
            previous_timestamp = record.get('ScrapedAt', '')
            break
    
    if previous_dominant and previous_dominant != current_dominant:
        return {
            'key': current_dominant,
            'from_option': previous_dominant,
            'from_pct': previous_pct,
            'to_option': current_dominant,
            'to_pct': current_pct,
            'previous_timestamp': previous_timestamp,
            'current_timestamp': current.get('ScrapedAt', '')
        }
    
    return None

def group_alarms_by_match(alarms: List[Dict]) -> List[Dict]:
    grouped = defaultdict(lambda: defaultdict(list))
    
    for alarm in alarms:
        key = (alarm.get('home', ''), alarm.get('away', ''))
        alarm_type = alarm.get('type', '')
        grouped[key][alarm_type].append(alarm)
    
    result = []
    for (home, away), type_alarms in grouped.items():
        for alarm_type, events in type_alarms.items():
            events.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            
            max_money = max((e.get('money_diff', 0) for e in events), default=0)
            max_drop = max((e.get('total_drop', 0) for e in events), default=0)
            
            result.append({
                'home': home,
                'away': away,
                'type': alarm_type,
                'count': len(events),
                'latest': events[0],
                'events': events,
                'max_money': max_money,
                'max_drop': max_drop,
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
            detail_text = f"+£{int(money_diff):,} — Oran {alarm['odds_from']:.2f} → {alarm['odds_to']:.2f} (Score: {alarm.get('smart_score', 0)})"
        else:
            detail_text = f"+£{int(money_diff):,}"
    elif alarm['type'] == 'rlm':
        detail_text = f"Para arttı (+£{int(money_diff):,}), oran yükseldi."
    elif alarm['type'] == 'big_money':
        detail_text = f"+£{int(money_diff):,} (son scrape)"
    elif alarm['type'] == 'dropping':
        drop = alarm.get('total_drop', 0)
        pct = alarm.get('money_pct', 0)
        detail_text = f"Toplam düşüş: {drop:.2f} — Para: {pct:.0f}%"
    elif alarm['type'] == 'public_surge':
        detail_text = f"Para artıyor (+£{int(money_diff):,}), oran sabit."
    elif alarm['type'] == 'momentum':
        detail_text = f"+£{int(money_diff):,} sürekli akış."
    elif alarm['type'] == 'line_freeze':
        detail_text = f"Para gelmesine rağmen oran donuk."
    
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
        'money_diff': money_diff
    }

def format_grouped_alarm(group: Dict) -> Dict:
    alarm_info = ALARM_TYPES.get(group['type'], {})
    latest = group['latest']
    
    return {
        'type': group['type'],
        'icon': alarm_info.get('icon', ''),
        'name': alarm_info.get('name', ''),
        'color': alarm_info.get('color', '#fff'),
        'home': group['home'],
        'away': group['away'],
        'side': latest.get('side', ''),
        'count': group['count'],
        'latest_time': latest.get('timestamp', ''),
        'max_money': group['max_money'],
        'max_drop': group['max_drop'],
        'events': [format_alarm_for_modal(e) for e in group['events']],
        'priority': group['priority'],
        'critical': alarm_info.get('critical', False)
    }
