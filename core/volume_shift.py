"""
Volume Shift Alarm (Hacim / Lider Değişimi)
==========================================

Amaç:
1-X-2, O/U 2.5 ve BTTS marketlerinde:
- Bir seçenek %50+ pay ile "lider" iken
- Bir süre sonra %50+ liderlik başka bir seçeneğe geçtiyse
- Ve bu süreçte belirli miktarda hacim girdiyse
→ Volume Shift alarmı üret.

Bu alarm, Momentum Spike'tan tamamen bağımsızdır.
"""

from typing import Dict, List, Optional, Any


VOLUME_SHIFT_THRESHOLDS = {
    '1x2': 1000,
    'ou25': 750,
    'btts': 500,
}

DOMINANCE_THRESHOLD = 50.0


def get_market_type(market: str) -> str:
    """Market string'inden market tipini çıkar"""
    market_lower = market.lower()
    if '1x2' in market_lower:
        return '1x2'
    elif 'ou25' in market_lower or 'o/u' in market_lower or 'over' in market_lower:
        return 'ou25'
    elif 'btts' in market_lower:
        return 'btts'
    return '1x2'


def parse_volume(val: Any) -> float:
    """Hacim değerini parse et"""
    if not val:
        return 0.0
    try:
        s = str(val).replace('£', '').replace(',', '').replace(' ', '').strip()
        return float(s) if s else 0.0
    except (ValueError, TypeError):
        return 0.0


def parse_share(val: Any) -> float:
    """Yüzde değerini parse et"""
    if not val:
        return 0.0
    try:
        s = str(val).replace('%', '').replace(',', '.').strip()
        return float(s) if s else 0.0
    except (ValueError, TypeError):
        return 0.0


def get_side_keys(market: str, side: str) -> Dict[str, str]:
    """Side için key'leri döndür"""
    market_type = get_market_type(market)
    
    if market_type == '1x2':
        if side == '1':
            return {'pct': 'Pct1', 'amt': 'Amt1', 'odds': 'Odds1'}
        elif side == 'X':
            return {'pct': 'PctX', 'amt': 'AmtX', 'odds': 'OddsX'}
        elif side == '2':
            return {'pct': 'Pct2', 'amt': 'Amt2', 'odds': 'Odds2'}
    elif market_type == 'ou25':
        if side in ['Over', 'O']:
            return {'pct': 'PctOver', 'amt': 'AmtOver', 'odds': 'Over'}
        elif side in ['Under', 'U']:
            return {'pct': 'PctUnder', 'amt': 'AmtUnder', 'odds': 'Under'}
    elif market_type == 'btts':
        if side in ['Yes', 'Y']:
            return {'pct': 'PctYes', 'amt': 'AmtYes', 'odds': 'OddsYes'}
        elif side in ['No', 'N']:
            return {'pct': 'PctNo', 'amt': 'AmtNo', 'odds': 'OddsNo'}
    
    return {'pct': f'Pct{side}', 'amt': f'Amt{side}', 'odds': f'Odds{side}'}


def get_all_sides(market: str) -> List[str]:
    """Market için tüm side'ları döndür"""
    market_type = get_market_type(market)
    if market_type == '1x2':
        return ['1', 'X', '2']
    elif market_type == 'ou25':
        return ['Over', 'Under']
    elif market_type == 'btts':
        return ['Yes', 'No']
    return ['1', 'X', '2']


def get_leader(record: Dict, market: str) -> tuple:
    """
    Bir kayıttaki lideri bul.
    
    Returns:
        (leader_side, leader_share) - %50+ payı olan lider, yoksa (None, 0)
    """
    sides = get_all_sides(market)
    
    best_side = None
    best_share = 0.0
    
    for side in sides:
        keys = get_side_keys(market, side)
        share = parse_share(record.get(keys['pct'], 0))
        
        if share > best_share:
            best_side = side
            best_share = share
    
    if best_share >= DOMINANCE_THRESHOLD:
        return (best_side, best_share)
    
    return (None, 0.0)


def get_total_volume(record: Dict, market: str) -> float:
    """Bir kayıttaki toplam market hacmini hesapla"""
    sides = get_all_sides(market)
    total = 0.0
    
    for side in sides:
        keys = get_side_keys(market, side)
        total += parse_volume(record.get(keys['amt'], 0))
    
    return total


def detect_volume_shift(
    history: List[Dict],
    market: str,
    home: str = '',
    away: str = ''
) -> Optional[Dict[str, Any]]:
    """
    Volume Shift (Lider Değişimi) tespiti yapar.
    
    Kriterler:
    1. Önceki kayıtta bir seçenek %50+ pay ile lider
    2. Şimdiki kayıtta farklı bir seçenek %50+ pay ile lider
    3. Bu süreçte market'e yeni hacim girmiş (threshold karşılandı)
    
    Args:
        history: Maç geçmişi (en az 2 kayıt gerekli)
        market: Market tipi
        home: Ev sahibi
        away: Deplasman
    
    Returns:
        Volume Shift alarm objesi veya None
    """
    if len(history) < 2:
        return None
    
    market_type = get_market_type(market)
    
    if market_type not in VOLUME_SHIFT_THRESHOLDS:
        return None
    
    sorted_history = sorted(history, key=lambda x: x.get('ScrapedAt', ''), reverse=True)
    
    current = sorted_history[0]
    previous = sorted_history[1]
    
    current_leader, current_share = get_leader(current, market)
    previous_leader, previous_share = get_leader(previous, market)
    
    if not current_leader or not previous_leader:
        return None
    
    if previous_leader == current_leader:
        return None
    
    current_total = get_total_volume(current, market)
    previous_total = get_total_volume(previous, market)
    new_money_market = current_total - previous_total
    
    threshold = VOLUME_SHIFT_THRESHOLDS.get(market_type, 1000)
    
    if new_money_market < threshold:
        return None
    
    latest_ts = current.get('ScrapedAt', '')
    
    alarm = {
        'type': 'volume_shift',
        'market': market,
        'market_type': market_type,
        'side': current_leader,
        'previous_leader': previous_leader,
        'current_leader': current_leader,
        'previous_share': round(previous_share, 1),
        'current_share': round(current_share, 1),
        'new_money_market': round(new_money_market, 0),
        'threshold': threshold,
        'is_alarm': True,
        'home': home,
        'away': away,
        'detail': f"{previous_leader}→{current_leader} ({previous_share:.0f}%→{current_share:.0f}%) | +£{int(new_money_market):,}",
        'timestamp': latest_ts
    }
    
    print(f"[VolumeShift] {home} vs {away} ({market_type}): "
          f"{previous_leader}→{current_leader} | "
          f"Share: {previous_share:.0f}%→{current_share:.0f}% | "
          f"New Money: £{int(new_money_market):,}")
    
    return alarm


def check_volume_shift_for_match(
    history: List[Dict],
    market: str,
    home: str,
    away: str
) -> List[Dict[str, Any]]:
    """
    Bir maç için Volume Shift kontrolü yapar.
    
    Args:
        history: Maç geçmişi
        market: Market tipi
        home: Ev sahibi
        away: Deplasman
    
    Returns:
        Tespit edilen Volume Shift alarmları listesi (en fazla 1)
    """
    alarms = []
    
    alarm = detect_volume_shift(history, market, home, away)
    if alarm:
        alarms.append(alarm)
    
    return alarms


class VolumeShiftDetector:
    """Volume Shift alarmları için detector sınıfı"""
    
    def __init__(self):
        self.thresholds = VOLUME_SHIFT_THRESHOLDS.copy()
        self.dominance_threshold = DOMINANCE_THRESHOLD
    
    def detect(
        self,
        history: List[Dict],
        market: str,
        home: str = '',
        away: str = ''
    ) -> Optional[Dict[str, Any]]:
        """Volume Shift tespiti yap"""
        return detect_volume_shift(history, market, home, away)
    
    def check_match(
        self,
        history: List[Dict],
        market: str,
        home: str,
        away: str
    ) -> List[Dict[str, Any]]:
        """Bir maç için Volume Shift kontrolü"""
        return check_volume_shift_for_match(history, market, home, away)


if __name__ == '__main__':
    print("Volume Shift Detection Module")
    print("=" * 50)
    print(f"Dominance Threshold: {DOMINANCE_THRESHOLD}%")
    print(f"\nVolume Thresholds:")
    for market, threshold in VOLUME_SHIFT_THRESHOLDS.items():
        print(f"  {market}: £{threshold:,}")
    print("\nKurallar:")
    print("  1. Önceki lider: %50+ pay")
    print("  2. Yeni lider: Farklı seçenek + %50+ pay")
    print("  3. Hacim: Market'e yeni para girişi >= threshold")
