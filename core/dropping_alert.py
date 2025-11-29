"""
Dropping Alert - V3 with Tiered Levels & 30-Minute Persistence

Seviye Sistemi:
  7% ≤ drop < 10%  → Level 1 (L1)
  10% ≤ drop < 15% → Level 2 (L2)
  drop ≥ 15%       → Level 3 (L3)

Kalıcılık Kuralı:
  - Drop en az %7 olmalı (Level 1+)
  - Bu seviye kesintisiz en az 30 dakika korunmalı
  - Ancak o zaman gerçek Dropping Alert üretilir

30dk dolmadan:
  - Alarm listesinde GÖSTERİLMEZ
  - Maç detayında "dropping movement started" preview gösterilebilir

30dk+ sonra:
  - Alarm listesine "Dropping L2 – 11% (30dk+ kalıcı)" şeklinde eklenir
"""

from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta
from core.alarm_state import (
    get_dropping_level,
    update_dropping_state,
    mark_dropping_alarm_fired,
    DROPPING_PERSISTENCE_MINUTES
)


DROP_THRESHOLD_PERCENT = 7.0


def parse_odds(val) -> float:
    """Parse odds value to float"""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        val = val.strip()
        if not val or val == '-':
            return 0.0
        try:
            return float(val.replace(',', '.'))
        except:
            return 0.0
    return 0.0


def parse_money(val) -> float:
    """Parse money value to float"""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        val = val.replace('£', '').replace(',', '').replace(' ', '').strip()
        try:
            return float(val)
        except:
            return 0.0
    return 0.0


def get_sides_for_market(market: str) -> List[Dict[str, str]]:
    """Get side configurations for a market"""
    if '1x2' in market:
        return [
            {'key': '1', 'amt': 'Amt1', 'odds': 'Odds1'},
            {'key': 'X', 'amt': 'AmtX', 'odds': 'OddsX'},
            {'key': '2', 'amt': 'Amt2', 'odds': 'Odds2'}
        ]
    elif 'ou25' in market:
        return [
            {'key': 'Over', 'amt': 'AmtOver', 'odds': 'Over'},
            {'key': 'Under', 'amt': 'AmtUnder', 'odds': 'Under'}
        ]
    elif 'btts' in market:
        return [
            {'key': 'Yes', 'amt': 'AmtYes', 'odds': 'OddsYes'},
            {'key': 'No', 'amt': 'AmtNo', 'odds': 'OddsNo'}
        ]
    return []


def calculate_drop_percent(opening_odds: float, current_odds: float) -> float:
    """
    Calculate drop percentage from opening to current odds.
    
    Formula: drop_percent = (opening_odds - current_odds) / opening_odds * 100
    """
    if opening_odds <= 0:
        return 0.0
    
    drop_percent = (opening_odds - current_odds) / opening_odds * 100
    return drop_percent


def detect_dropping_alerts(
    history: List[Dict],
    market: str,
    match_id: str = None,
    home: str = None,
    away: str = None
) -> Tuple[List[Dict], List[Dict]]:
    """
    Detect dropping alerts with tiered levels and 30-minute persistence.
    
    Returns:
        Tuple of (real_alerts, preview_alerts)
        - real_alerts: 30dk+ kalıcı droplar → alarm listesine gider
        - preview_alerts: 30dk'dan az → sadece maç detayında preview
    """
    if not history or len(history) < 2:
        return [], []
    
    sides = get_sides_for_market(market)
    if not sides:
        return [], []
    
    first = history[0]
    current = history[-1]
    
    real_alerts = []
    preview_alerts = []
    dropping_sides_count = 0
    real_dropping_count = 0
    
    for side in sides:
        opening_odds = parse_odds(first.get(side['odds'], 0))
        current_odds = parse_odds(current.get(side['odds'], 0))
        selection_volume = parse_money(current.get(side['amt'], 0))
        
        if opening_odds <= 1.01 or current_odds <= 0:
            continue
        
        drop_percent = calculate_drop_percent(opening_odds, current_odds)
        level = get_dropping_level(drop_percent)
        
        state = update_dropping_state(
            match_id=match_id,
            market=market,
            side=side['key'],
            drop_pct=drop_percent,
            level=level
        )
        
        if level == 0:
            continue
        
        dropping_sides_count += 1
        drop_value = opening_odds - current_odds
        
        alert_data = {
            'type': 'dropping',
            'side': side['key'],
            'opening_odds': opening_odds,
            'current_odds': current_odds,
            'drop_percent': round(drop_percent, 1),
            'drop_value': round(drop_value, 2),
            'selection_volume': selection_volume,
            'market': market,
            'match_id': match_id,
            'home': home,
            'away': away,
            'dropping_level': level,
            'persisted_minutes': state['persisted_minutes'],
            'is_real_alert': state['is_real_alert'],
            'drop_start_time': state['drop_start_time']
        }
        
        if state['is_real_alert']:
            if not state['alarm_fired']:
                real_alerts.append(alert_data)
                real_dropping_count += 1
                mark_dropping_alarm_fired(match_id, market, side['key'])
        else:
            preview_alerts.append(alert_data)
    
    for alert in real_alerts:
        alert['dropping_sides_count'] = real_dropping_count
    
    for alert in preview_alerts:
        alert['dropping_sides_count'] = dropping_sides_count
    
    return real_alerts, preview_alerts


def detect_dropping_alerts_legacy(
    history: List[Dict],
    market: str,
    match_id: str = None,
    home: str = None,
    away: str = None
) -> List[Dict]:
    """
    Legacy function for backward compatibility.
    Returns only real alerts (30dk+ kalıcı).
    """
    real_alerts, _ = detect_dropping_alerts(
        history=history,
        market=market,
        match_id=match_id,
        home=home,
        away=away
    )
    return real_alerts


def format_dropping_alert(alarm: Dict) -> Dict:
    """
    Format dropping alert for display.
    
    New format: "Dropping L2 – 11% (30dk+ kalıcı)"
    
    Returns:
    - xN: Number of selections with 7%+ drop
    - level: 1, 2, or 3
    - drop_text: "Dropping L2 – 11.2% (30dk+ kalıcı)" format
    - money_text: "£12,345" format (selection volume only)
    """
    drop_value = alarm.get('drop_value', 0)
    drop_percent = alarm.get('drop_percent', 0)
    selection_volume = alarm.get('selection_volume', 0)
    dropping_count = alarm.get('dropping_sides_count', 1)
    level = alarm.get('dropping_level', get_dropping_level(drop_percent))
    persisted_minutes = alarm.get('persisted_minutes', 0)
    is_real = alarm.get('is_real_alert', persisted_minutes >= DROPPING_PERSISTENCE_MINUTES)
    
    level_text = f"L{level}" if level > 0 else ""
    
    if is_real:
        persistence_text = "(30dk+ kalıcı)"
    else:
        remaining = DROPPING_PERSISTENCE_MINUTES - persisted_minutes
        persistence_text = f"({int(persisted_minutes)}dk / {int(remaining)}dk kaldı)"
    
    drop_text = f"{level_text} – {drop_percent:.1f}% {persistence_text}"
    
    return {
        'xN': dropping_count,
        'level': level,
        'level_text': level_text,
        'drop_text': drop_text.strip(),
        'money_text': f"£{int(selection_volume):,}",
        'drop_value': drop_value,
        'drop_percent': drop_percent,
        'selection_volume': selection_volume,
        'persisted_minutes': persisted_minutes,
        'is_real_alert': is_real
    }


def get_level_color(level: int) -> str:
    """Get color for dropping level"""
    colors = {
        1: '#f59e0b',
        2: '#ef4444',
        3: '#dc2626'
    }
    return colors.get(level, '#f59e0b')


def get_level_name(level: int) -> str:
    """Get display name for dropping level"""
    names = {
        1: 'Dropping L1',
        2: 'Dropping L2',
        3: 'Dropping L3'
    }
    return names.get(level, 'Dropping')


class DroppingAlertDetector:
    """
    Dropping Alert detector with tiered levels and 30-minute persistence.
    
    Levels:
      7% ≤ drop < 10%  → Level 1
      10% ≤ drop < 15% → Level 2
      drop ≥ 15%       → Level 3
    
    Persistence:
      Alert only fires after 30+ continuous minutes at Level 1+
    """
    
    THRESHOLD = DROP_THRESHOLD_PERCENT
    PERSISTENCE_MINUTES = DROPPING_PERSISTENCE_MINUTES
    
    def __init__(self):
        self.threshold = self.THRESHOLD
    
    def detect(self, history: List[Dict], market: str, **kwargs) -> List[Dict]:
        """
        Detect dropping alerts for a match history.
        Returns only REAL alerts (30dk+ kalıcı).
        """
        real_alerts, _ = detect_dropping_alerts(
            history=history,
            market=market,
            match_id=kwargs.get('match_id'),
            home=kwargs.get('home'),
            away=kwargs.get('away')
        )
        return real_alerts
    
    def detect_with_previews(self, history: List[Dict], market: str, **kwargs) -> Tuple[List[Dict], List[Dict]]:
        """
        Detect dropping alerts with both real and preview alerts.
        
        Returns:
            (real_alerts, preview_alerts)
        """
        return detect_dropping_alerts(
            history=history,
            market=market,
            match_id=kwargs.get('match_id'),
            home=kwargs.get('home'),
            away=kwargs.get('away')
        )
    
    def format_alert(self, alarm: Dict) -> Dict:
        """Format alarm for display"""
        return format_dropping_alert(alarm)
    
    def get_level(self, drop_pct: float) -> int:
        """Get dropping level for a given drop percentage"""
        return get_dropping_level(drop_pct)
