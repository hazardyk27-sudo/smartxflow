"""
Reversal Move Detection System

3 Kriter ile Trend Dönüşü Tespiti:
1. Fiyat Geri Dönüşü (Retracement): ≥50% geri alınmış
2. Momentum/Trend Değişimi: Yön değiştirmiş
3. Hacim Taraf Değiştirmesi (Volume Switch): Para karşı tarafa geçmiş

3 kriterin TAMAMI sağlanınca reversal_move_detected = True
2/3 kriter: Sadece log kaydı (alarm tetiklenmez)

Reversal tespit edilince:
- Sharp sinyali iptal edilir
- Dropping Alert sıfırlanır
- Sharp skorundan 20 puan düşülür
"""

from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime


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
            {'key': '1', 'amt': 'Amt1', 'odds': 'Odds1', 'pct': 'Pct1'},
            {'key': 'X', 'amt': 'AmtX', 'odds': 'OddsX', 'pct': 'PctX'},
            {'key': '2', 'amt': 'Amt2', 'odds': 'Odds2', 'pct': 'Pct2'}
        ]
    elif 'ou25' in market:
        return [
            {'key': 'Over', 'amt': 'AmtOver', 'odds': 'Over', 'pct': 'PctOver'},
            {'key': 'Under', 'amt': 'AmtUnder', 'odds': 'Under', 'pct': 'PctUnder'}
        ]
    elif 'btts' in market:
        return [
            {'key': 'Yes', 'amt': 'AmtYes', 'odds': 'OddsYes', 'pct': 'PctYes'},
            {'key': 'No', 'amt': 'AmtNo', 'odds': 'OddsNo', 'pct': 'PctNo'}
        ]
    return []


def sign(val: float) -> int:
    """Return sign of value: -1, 0, or 1"""
    if val > 0:
        return 1
    elif val < 0:
        return -1
    return 0


def calculate_drop_percent(opening_odds: float, lowest_odds: float) -> float:
    """
    Drop yüzdesi hesapla.
    drop_pct = (opening_odds - lowest_odds) / opening_odds * 100
    """
    if opening_odds <= 0:
        return 0.0
    return (opening_odds - lowest_odds) / opening_odds * 100


def calculate_reversal_percent(opening_odds: float, lowest_odds: float, current_odds: float) -> float:
    """
    Reversal yüzdesi hesapla (drop'un ne kadarı geri alınmış).
    reversal_pct = (current_odds - lowest_odds) / (opening_odds - lowest_odds) * 100
    
    Örnek: Açılış 2.00, En düşük 1.80, Şimdi 1.90
    Drop = 0.20, Geri alınan = 0.10
    Reversal = 0.10 / 0.20 * 100 = 50%
    """
    drop_amount = opening_odds - lowest_odds
    if drop_amount <= 0:
        return 0.0
    
    reversal_amount = current_odds - lowest_odds
    return (reversal_amount / drop_amount) * 100


def check_momentum_change(history: List[Dict], side: Dict[str, str]) -> Tuple[bool, int, int]:
    """
    Momentum/Trend değişimi kontrolü.
    Son 3 fiyat noktasından trend çıkarılır.
    
    Returns:
        (momentum_changed, previous_trend, current_trend)
    """
    if len(history) < 3:
        return False, 0, 0
    
    odds_key = side['odds']
    
    prev_prev_odds = parse_odds(history[-3].get(odds_key, 0))
    prev_odds = parse_odds(history[-2].get(odds_key, 0))
    current_odds = parse_odds(history[-1].get(odds_key, 0))
    
    if prev_prev_odds <= 0 or prev_odds <= 0 or current_odds <= 0:
        return False, 0, 0
    
    previous_trend = sign(prev_odds - prev_prev_odds)
    current_trend = sign(current_odds - prev_odds)
    
    momentum_changed = current_trend != previous_trend and current_trend != 0 and previous_trend != 0
    
    return momentum_changed, previous_trend, current_trend


def check_volume_switch(
    history: List[Dict],
    sides: List[Dict[str, str]],
    drop_side_key: str
) -> Tuple[bool, float, float]:
    """
    Hacmin taraf değiştirmesi kontrolü.
    Drop sırasında baskın olan tarafa karşı, reversal sırasında karşı tarafa
    daha fazla para gelmiş mi?
    
    Returns:
        (volume_switched, volume_on_drop_side, new_volume_on_opposite)
    """
    if len(history) < 3:
        return False, 0, 0
    
    mid_point = len(history) // 2
    drop_period = history[:mid_point + 1]
    reversal_period = history[mid_point:]
    
    if not drop_period or not reversal_period:
        return False, 0, 0
    
    drop_side = None
    opposite_sides = []
    
    for side in sides:
        if side['key'] == drop_side_key:
            drop_side = side
        else:
            opposite_sides.append(side)
    
    if not drop_side or not opposite_sides:
        return False, 0, 0
    
    drop_start_amt = parse_money(drop_period[0].get(drop_side['amt'], 0))
    drop_end_amt = parse_money(drop_period[-1].get(drop_side['amt'], 0))
    volume_on_drop_side = drop_end_amt - drop_start_amt
    
    new_volume_on_opposite = 0
    for opp_side in opposite_sides:
        rev_start_amt = parse_money(reversal_period[0].get(opp_side['amt'], 0))
        rev_end_amt = parse_money(reversal_period[-1].get(opp_side['amt'], 0))
        new_volume_on_opposite += max(0, rev_end_amt - rev_start_amt)
    
    volume_switched = new_volume_on_opposite > volume_on_drop_side and volume_on_drop_side > 0
    
    return volume_switched, volume_on_drop_side, new_volume_on_opposite


def find_lowest_odds_in_history(history: List[Dict], side: Dict[str, str]) -> Tuple[float, int]:
    """
    History'de en düşük oranı ve indexini bul.
    Returns: (lowest_odds, index)
    """
    if not history:
        return 0.0, -1
    
    odds_key = side['odds']
    lowest = float('inf')
    lowest_idx = -1
    
    for i, row in enumerate(history):
        odds = parse_odds(row.get(odds_key, 0))
        if odds > 0 and odds < lowest:
            lowest = odds
            lowest_idx = i
    
    return (lowest if lowest != float('inf') else 0.0), lowest_idx


def detect_reversal_move(
    history: List[Dict],
    market: str,
    match_id: str = None,
    home: str = None,
    away: str = None
) -> List[Dict[str, Any]]:
    """
    Reversal Move tespiti - 3 kriter sistemi.
    
    Kriterler:
    1. Fiyat Geri Dönüşü (Retracement): ≥50%
    2. Momentum/Trend Değişimi
    3. Hacim Taraf Değiştirmesi (Volume Switch)
    
    3 kriterin TAMAMI sağlanınca reversal_move_detected = True
    2/3 kriter: Sadece log kaydı (alarm tetiklenmez)
    
    Returns:
        List of reversal move alerts with details
    """
    if not history or len(history) < 4:
        return []
    
    sides = get_sides_for_market(market)
    if not sides:
        return []
    
    first = history[0]
    current = history[-1]
    
    reversal_alerts = []
    
    for side in sides:
        odds_key = side['odds']
        
        opening_odds = parse_odds(first.get(odds_key, 0))
        current_odds = parse_odds(current.get(odds_key, 0))
        
        if opening_odds <= 1.01 or current_odds <= 0:
            continue
        
        lowest_odds, lowest_idx = find_lowest_odds_in_history(history, side)
        
        if lowest_odds <= 0 or lowest_idx < 0:
            continue
        
        drop_pct = calculate_drop_percent(opening_odds, lowest_odds)
        
        if drop_pct < 3.0:
            continue
        
        reversal_pct = calculate_reversal_percent(opening_odds, lowest_odds, current_odds)
        
        momentum_changed, prev_trend, curr_trend = check_momentum_change(history, side)
        
        volume_switched, vol_on_drop, vol_on_opposite = check_volume_switch(
            history, sides, side['key']
        )
        
        conditions_met = 0
        criteria_details = []
        
        if reversal_pct >= 50:
            conditions_met += 1
            criteria_details.append(f"Retracement: {reversal_pct:.1f}%")
        
        if momentum_changed:
            conditions_met += 1
            trend_text = "↓→↑" if curr_trend > 0 else "↑→↓"
            criteria_details.append(f"Momentum: {trend_text}")
        
        if volume_switched:
            conditions_met += 1
            criteria_details.append(f"Volume Switch: £{int(vol_on_opposite):,} > £{int(vol_on_drop):,}")
        
        if conditions_met >= 2:
            print(f"[Reversal] {side['key']}: {conditions_met}/3 kriter | "
                  f"Drop={drop_pct:.1f}% → Reversal={reversal_pct:.1f}% | "
                  f"{' | '.join(criteria_details)}")
        
        is_alarm = conditions_met == 3
        
        if is_alarm:
            alert_data = {
                'type': 'reversal_move',
                'side': side['key'],
                'match_id': match_id,
                'home': home,
                'away': away,
                'market': market,
                'opening_odds': opening_odds,
                'lowest_odds': lowest_odds,
                'current_odds': current_odds,
                'drop_percent': round(drop_pct, 1),
                'reversal_percent': round(reversal_pct, 1),
                'conditions_met': conditions_met,
                'is_alarm': True,
                'criteria': {
                    'retracement_ok': reversal_pct >= 50,
                    'momentum_changed': momentum_changed,
                    'volume_switched': volume_switched,
                    'retracement_pct': round(reversal_pct, 1),
                    'prev_trend': prev_trend,
                    'curr_trend': curr_trend,
                    'volume_on_drop': vol_on_drop,
                    'volume_on_opposite': vol_on_opposite
                },
                'criteria_text': ' | '.join(criteria_details),
                'timestamp': current.get('ScrapedAt', '')
            }
            
            reversal_alerts.append(alert_data)
            print(f"[Reversal ALARM] {side['key']}: 3/3 kriter met! Alarm triggered")
    
    return reversal_alerts


def apply_reversal_effects(
    reversal_alerts: List[Dict],
    sharp_results: List[Dict],
    dropping_alerts: List[Dict]
) -> Tuple[List[Dict], List[Dict], List[str]]:
    """
    Reversal tespit edilince Sharp ve Dropping üzerine etkileri uygula.
    
    Etkiler:
    - Sharp sinyali iptal edilir (is_sharp = False)
    - Dropping Alert sıfırlanır
    - Sharp skorundan 20 puan düşülür
    
    Returns:
        (modified_sharp_results, modified_dropping_alerts, affected_sides)
    """
    if not reversal_alerts:
        return sharp_results, dropping_alerts, []
    
    reversal_sides = {r['side'] for r in reversal_alerts}
    affected_sides = list(reversal_sides)
    
    modified_sharp = []
    for sharp in sharp_results:
        if sharp.get('side') in reversal_sides:
            modified = sharp.copy()
            modified['is_sharp'] = False
            modified['sharp_score'] = max(sharp.get('sharp_score', 0) - 20, 0)
            modified['reversal_applied'] = True
            modified['tags'] = modified.get('tags', []) + ['reversal_move']
            print(f"[Reversal] Sharp iptal: {sharp.get('side')} | "
                  f"Skor: {sharp.get('sharp_score', 0)} → {modified['sharp_score']}")
            modified_sharp.append(modified)
        else:
            modified_sharp.append(sharp)
    
    modified_dropping = []
    for dropping in dropping_alerts:
        if dropping.get('side') in reversal_sides:
            modified = dropping.copy()
            modified['reversal_applied'] = True
            modified['is_real_alert'] = False
            modified['tags'] = modified.get('tags', []) + ['reversal_move']
            print(f"[Reversal] Dropping iptal: {dropping.get('side')}")
            modified_dropping.append(modified)
        else:
            modified_dropping.append(dropping)
    
    return modified_sharp, modified_dropping, affected_sides


class ReversalMoveDetector:
    """
    Reversal Move Detector - 3 Kriter Sistemi
    
    Kriterler:
    1. Fiyat Geri Dönüşü ≥50%
    2. Momentum/Trend Değişimi
    3. Hacim Taraf Değiştirmesi
    
    2/3 kriter sağlanınca Reversal Move tespit edilir.
    """
    
    RETRACEMENT_THRESHOLD = 50.0
    MIN_DROP_PERCENT = 3.0
    
    def __init__(self):
        pass
    
    def detect(self, history: List[Dict], market: str, **kwargs) -> List[Dict]:
        """
        Reversal Move tespiti yap.
        """
        return detect_reversal_move(
            history=history,
            market=market,
            match_id=kwargs.get('match_id'),
            home=kwargs.get('home'),
            away=kwargs.get('away')
        )
    
    def apply_effects(
        self,
        reversal_alerts: List[Dict],
        sharp_results: List[Dict],
        dropping_alerts: List[Dict]
    ) -> Tuple[List[Dict], List[Dict], List[str]]:
        """
        Reversal etkilerini uygula.
        """
        return apply_reversal_effects(reversal_alerts, sharp_results, dropping_alerts)


reversal_detector = ReversalMoveDetector()
