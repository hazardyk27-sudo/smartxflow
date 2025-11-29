"""
Dropping Alert - Yeni Kural (V2)

Açılış oranından %7+ düşüş yaşayan seçenekler için alarm tetiklenir.

Hesaplama:
  drop_percent = (opening_odds - current_odds) / opening_odds * 100
  
Tetikleme:
  drop_percent >= 7 → Dropping Alert

Alarm kartı değerleri:
  - xN: O maçta %7+ düşen seçenek sayısı
  - drop: opening_odds - current_odds (oran farkı)
  - para: Sadece o seçeneğe oynanan para (selection volume)
"""

from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta


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
) -> List[Dict]:
    """
    Detect dropping alerts based on opening vs current odds.
    
    Returns list of alerts for selections that dropped >= 7% from opening.
    """
    if not history or len(history) < 2:
        return []
    
    sides = get_sides_for_market(market)
    if not sides:
        return []
    
    first = history[0]
    current = history[-1]
    
    alerts = []
    dropping_sides_count = 0
    
    for side in sides:
        opening_odds = parse_odds(first.get(side['odds'], 0))
        current_odds = parse_odds(current.get(side['odds'], 0))
        selection_volume = parse_money(current.get(side['amt'], 0))
        
        if opening_odds <= 1.01 or current_odds <= 0:
            continue
        
        drop_percent = calculate_drop_percent(opening_odds, current_odds)
        
        if drop_percent >= DROP_THRESHOLD_PERCENT:
            dropping_sides_count += 1
            
            drop_value = opening_odds - current_odds
            
            alerts.append({
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
                'away': away
            })
    
    for alert in alerts:
        alert['dropping_sides_count'] = dropping_sides_count
    
    return alerts


def format_dropping_alert(alarm: Dict) -> Dict:
    """
    Format dropping alert for display.
    
    Returns:
    - xN: Number of selections with 7%+ drop
    - drop_text: "0.45 drop (-7.2%)" format
    - money_text: "£12,345" format (selection volume only)
    """
    drop_value = alarm.get('drop_value', 0)
    drop_percent = alarm.get('drop_percent', 0)
    selection_volume = alarm.get('selection_volume', 0)
    dropping_count = alarm.get('dropping_sides_count', 1)
    
    return {
        'xN': dropping_count,
        'drop_text': f"{drop_value:.2f} drop (-{drop_percent:.1f}%)",
        'money_text': f"£{int(selection_volume):,}",
        'drop_value': drop_value,
        'drop_percent': drop_percent,
        'selection_volume': selection_volume
    }


class DroppingAlertDetector:
    """
    Dropping Alert detector using opening vs current odds comparison.
    
    Alert triggers when: drop_percent >= 7%
    Where: drop_percent = (opening_odds - current_odds) / opening_odds * 100
    """
    
    THRESHOLD = DROP_THRESHOLD_PERCENT
    
    def __init__(self):
        self.threshold = self.THRESHOLD
    
    def detect(self, history: List[Dict], market: str, **kwargs) -> List[Dict]:
        """Detect dropping alerts for a match history"""
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
