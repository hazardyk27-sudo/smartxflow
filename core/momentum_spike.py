"""
Momentum Spike Detection Algorithm V2
======================================

10 dakikalık ardışık güncelleme aralığında Momentum Spike tespiti.

Market Bazlı Hacim Eşikleri:
- 1X2: £1,000
- O/U 2.5: £750
- BTTS: £500

Spike tetiklenmesi için aşağıdaki 4 kriterden EN AZ 2'si aynı anda sağlanmalı:
1. new_money >= market eşiği
2. share_now >= 6%
3. percentage_change >= 7%
4. odds_drop >= 4%

Level Sistemi (new_money bandlarına göre):
- LEVEL 1: new_money 1500-3000
- LEVEL 2: new_money 3000-5000
- LEVEL 3: new_money >5000

Önemli: Tüm hesaplamalar ardışık iki güncelleme (previous vs current) arasında yapılır.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime


MOMENTUM_VOLUME_THRESHOLDS = {
    '1x2': 1000,
    'ou25': 750,
    'btts': 500,
}

SHARE_NOW_THRESHOLD = 6.0
PERCENTAGE_CHANGE_THRESHOLD = 7.0
ODDS_DROP_THRESHOLD = 4.0

MIN_CRITERIA_COUNT = 2


def get_market_type(market: str) -> str:
    """Market string'inden market tipini çıkar (1x2, ou25, btts)"""
    market_lower = market.lower()
    if '1x2' in market_lower:
        return '1x2'
    elif 'ou25' in market_lower or 'ou2.5' in market_lower or 'o/u' in market_lower:
        return 'ou25'
    elif 'btts' in market_lower:
        return 'btts'
    return '1x2'


def parse_volume(volume_str: Any) -> float:
    """Volume string'ini float'a çevir (£1,234 -> 1234.0)"""
    if volume_str is None:
        return 0.0
    if isinstance(volume_str, (int, float)):
        return float(volume_str)
    if isinstance(volume_str, str):
        cleaned = volume_str.replace('£', '').replace(',', '').replace(' ', '').strip()
        try:
            return float(cleaned) if cleaned else 0.0
        except ValueError:
            return 0.0
    return 0.0


def parse_share(share_str: Any) -> float:
    """Share string'ini float'a çevir (%45 -> 45.0)"""
    if share_str is None:
        return 0.0
    if isinstance(share_str, (int, float)):
        return float(share_str)
    if isinstance(share_str, str):
        cleaned = share_str.replace('%', '').replace(' ', '').strip()
        try:
            return float(cleaned) if cleaned else 0.0
        except ValueError:
            return 0.0
    return 0.0


def parse_odds(val: Any) -> float:
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


def calculate_odds_drop_percent(odds_prev: float, odds_curr: float) -> float:
    """Oran düşüş yüzdesini hesapla"""
    if odds_prev <= 0:
        return 0.0
    return ((odds_prev - odds_curr) / odds_prev) * 100


def get_momentum_level(new_money: float) -> int:
    """
    Level belirleme - SADECE new_money bandlarına göre:
    LEVEL 0: new_money < 1500 (alarm üretilmemeli)
    LEVEL 1: new_money 1500-3000
    LEVEL 2: new_money 3000-5000
    LEVEL 3: new_money >5000
    """
    if new_money > 5000:
        return 3
    elif new_money >= 3000:
        return 2
    elif new_money >= 1500:
        return 1
    return 0


def get_side_keys(market: str, side: str) -> Dict[str, str]:
    """Side için key'leri döndür"""
    if side in ['1', 'X', '2']:
        return {
            'amt': f'Amt{side}',
            'odds': f'Odds{side}',
            'pct': f'Pct{side}'
        }
    elif side in ['Over', 'Under']:
        return {
            'amt': f'Amt{side}',
            'odds': side,
            'pct': f'Pct{side}'
        }
    elif side in ['Yes', 'No']:
        return {
            'amt': f'Amt{side}',
            'odds': f'Odds{side}',
            'pct': f'Pct{side}'
        }
    return {'amt': f'Amt{side}', 'odds': f'Odds{side}', 'pct': f'Pct{side}'}


def detect_momentum_spike(
    history: List[Dict],
    market: str,
    side: str,
    home: str = '',
    away: str = ''
) -> Optional[Dict[str, Any]]:
    """
    Momentum Spike tespiti yapar.
    
    Ardışık iki güncelleme (previous vs current) arasında:
    4 kriterden EN AZ 2'si sağlanmalı:
    1. new_money >= market eşiği (1x2: £1000, ou25: £750, btts: £500)
    2. share_now >= 6%
    3. percentage_change >= 7%
    4. odds_drop >= 4%
    
    Args:
        history: Maç geçmişi (en az 2 kayıt gerekli)
        market: Market tipi
        side: Seçenek (1, X, 2, Over, Under, Yes, No)
        home: Ev sahibi takım
        away: Deplasman takımı
    
    Returns:
        Momentum Spike alarm objesi veya None
    """
    if len(history) < 2:
        return None
    
    sorted_history = sorted(history, key=lambda x: x.get('ScrapedAt', ''), reverse=True)
    
    current = sorted_history[0]
    previous = sorted_history[1]
    
    latest_ts = current.get('ScrapedAt', '')
    if not latest_ts:
        return None
    
    market_type = get_market_type(market)
    volume_threshold = MOMENTUM_VOLUME_THRESHOLDS.get(market_type, 1000)
    
    keys = get_side_keys(market, side)
    
    curr_amt = parse_volume(current.get(keys['amt'], 0))
    prev_amt = parse_volume(previous.get(keys['amt'], 0))
    new_money = curr_amt - prev_amt
    
    share_now = parse_share(current.get(keys['pct'], 0))
    share_prev = parse_share(previous.get(keys['pct'], 0))
    percentage_change = share_now - share_prev
    
    odds_curr = parse_odds(current.get(keys['odds'], 0))
    odds_prev = parse_odds(previous.get(keys['odds'], 0))
    odds_drop = calculate_odds_drop_percent(odds_prev, odds_curr)
    
    criteria_met = 0
    criteria_details = []
    
    if new_money >= volume_threshold:
        criteria_met += 1
        criteria_details.append(f"new_money=£{int(new_money):,}")
    
    if share_now >= SHARE_NOW_THRESHOLD:
        criteria_met += 1
        criteria_details.append(f"share_now={share_now:.1f}%")
    
    if percentage_change >= PERCENTAGE_CHANGE_THRESHOLD:
        criteria_met += 1
        criteria_details.append(f"pct_change=+{percentage_change:.1f}%")
    
    if odds_drop >= ODDS_DROP_THRESHOLD:
        criteria_met += 1
        criteria_details.append(f"odds_drop={odds_drop:.1f}%")
    
    if criteria_met < MIN_CRITERIA_COUNT:
        return None
    
    momentum_level = get_momentum_level(new_money)
    
    if momentum_level == 0:
        return None
    
    alarm_type = f'momentum_spike_l{momentum_level}'
    
    alarm = {
        'type': alarm_type,
        'market': market,
        'market_type': market_type,
        'side': side,
        'momentum_level': momentum_level,
        'new_money': round(new_money, 0),
        'share_now': round(share_now, 1),
        'percentage_change': round(percentage_change, 1),
        'odds_drop': round(odds_drop, 2),
        'criteria_met': criteria_met,
        'criteria_details': criteria_details,
        'is_alarm': True,
        'home': home,
        'away': away,
        'detail': f"L{momentum_level} ({criteria_met}/4 kriter: {', '.join(criteria_details)})",
        'timestamp': latest_ts
    }
    
    print(f"[MomentumSpike] {home} vs {away} ({side}): L{momentum_level} | "
          f"{criteria_met}/4 kriter: {', '.join(criteria_details)}")
    
    return alarm


def check_momentum_spike_for_match(
    history: List[Dict],
    market: str,
    home: str,
    away: str,
    sides: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Bir maç için tüm side'larda momentum spike kontrolü yapar.
    
    Args:
        history: Maç geçmişi
        market: Market tipi
        home: Ev sahibi
        away: Deplasman
        sides: Kontrol edilecek side'lar
    
    Returns:
        Tespit edilen momentum spike alarmları listesi
    """
    if sides is None:
        market_type = get_market_type(market)
        if market_type == '1x2':
            sides = ['1', 'X', '2']
        elif market_type == 'ou25':
            sides = ['Over', 'Under']
        elif market_type == 'btts':
            sides = ['Yes', 'No']
        else:
            sides = ['1', 'X', '2']
    
    alarms = []
    
    for side in sides:
        alarm = detect_momentum_spike(history, market, side, home, away)
        if alarm:
            alarms.append(alarm)
    
    return alarms


if __name__ == '__main__':
    print("Momentum Spike Detection Module V2")
    print("=" * 50)
    print(f"Minimum Criteria: {MIN_CRITERIA_COUNT}/4")
    print(f"\nKriterler:")
    print(f"  1. new_money >= £{NEW_MONEY_THRESHOLD:,}")
    print(f"  2. share_now >= {SHARE_NOW_THRESHOLD}%")
    print(f"  3. percentage_change >= {PERCENTAGE_CHANGE_THRESHOLD}%")
    print(f"  4. odds_drop >= {ODDS_DROP_THRESHOLD}%")
    print("\nLevel System:")
    print("  L1: new_money 1500-3000 veya %4-%6 change")
    print("  L2: new_money 3000-5000 veya %6-%10 + odds_drop")
    print("  L3: new_money >5000 veya %10+ change + odds_drop >= %6")
