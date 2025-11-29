"""
Line Freeze Detection Algorithm V2
===================================

Oran donukluğu tespiti - Hacim artmasına rağmen oran değişmiyorsa alarm tetiklenir.

Ana Kriterler:
1. Oran 2 ardışık güncellemede (20 dakika) HİÇ değişmeyecek
2. Bu sırada hacim artacak: new_money >= 1500 VEYA share_now >= 6%
3. Market ortalaması değişiyorsa freeze daha güçlü sayılır

Level Sistemi:
- LEVEL 1 (Soft Freeze): 20dk freeze + düşük hacim (1500-3000)
- LEVEL 2 (Hard Freeze): 20-40dk freeze + share_now %4-%8 + market hareketli
- LEVEL 3 (Critical Freeze): 40dk+ freeze + share_now >= 8% + new_money >= 3000

Önemli: Ardışık güncellemeler arasında hesaplama yapılır.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta


FREEZE_MIN_MONEY = 1500
FREEZE_MIN_SHARE = 6.0
FREEZE_MAX_ODDS_CHANGE = 0.02

L1_MIN_DURATION = 20
L2_MIN_DURATION = 20
L3_MIN_DURATION = 40

L1_MIN_MONEY = 1500
L2_MIN_MONEY = 2000
L3_MIN_MONEY = 3000

L1_MIN_SHARE = 4.0
L2_MIN_SHARE = 4.0
L3_MIN_SHARE = 8.0


def get_market_type(market: str) -> str:
    """Market string'inden market tipini çıkar"""
    market_lower = market.lower()
    if '1x2' in market_lower:
        return '1x2'
    elif 'ou25' in market_lower or 'ou2.5' in market_lower:
        return 'ou25'
    elif 'btts' in market_lower:
        return 'btts'
    return '1x2'


def parse_volume(volume_str: Any) -> float:
    """Volume string'ini float'a çevir"""
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
    """Share string'ini float'a çevir"""
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


def parse_timestamp(ts: str) -> Optional[datetime]:
    """Parse timestamp string to datetime"""
    if not ts:
        return None
    try:
        if 'T' in ts:
            return datetime.fromisoformat(ts.replace('Z', '+00:00').split('+')[0])
        else:
            return datetime.strptime(ts[:19], '%Y-%m-%d %H:%M:%S')
    except:
        return None


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


def calculate_freeze_duration(history: List[Dict], side: str, keys: Dict[str, str]) -> int:
    """
    Freeze süresini dakika olarak hesapla.
    Oranın değişmediği ardışık güncelleme sayısını bul.
    Her güncelleme = 10dk
    """
    if len(history) < 2:
        return 0
    
    sorted_history = sorted(history, key=lambda x: x.get('ScrapedAt', ''), reverse=True)
    
    current_odds = parse_odds(sorted_history[0].get(keys['odds'], 0))
    if current_odds <= 0:
        return 0
    
    freeze_updates = 0
    
    for i in range(1, len(sorted_history)):
        prev_odds = parse_odds(sorted_history[i].get(keys['odds'], 0))
        
        if prev_odds <= 0:
            break
        
        odds_diff = abs(current_odds - prev_odds)
        
        if odds_diff <= FREEZE_MAX_ODDS_CHANGE:
            freeze_updates += 1
        else:
            break
    
    return freeze_updates * 10


def calculate_market_movement(history: List[Dict], sides: List[str], current_side: str) -> float:
    """
    Diğer seçeneklerdeki oran hareketini hesapla.
    Global market hareketliyse freeze daha anlamlı.
    """
    if len(history) < 2:
        return 0.0
    
    sorted_history = sorted(history, key=lambda x: x.get('ScrapedAt', ''), reverse=True)
    current = sorted_history[0]
    previous = sorted_history[1]
    
    total_movement = 0.0
    other_sides = [s for s in sides if s != current_side]
    
    for side in other_sides:
        if side in ['1', 'X', '2']:
            odds_key = f'Odds{side}'
        elif side in ['Over', 'Under']:
            odds_key = side
        else:
            odds_key = f'Odds{side}'
        
        curr_odds = parse_odds(current.get(odds_key, 0))
        prev_odds = parse_odds(previous.get(odds_key, 0))
        
        if prev_odds > 0:
            movement = abs(curr_odds - prev_odds) / prev_odds * 100
            total_movement += movement
    
    return total_movement


def get_freeze_level(
    freeze_duration: int,
    new_money: float,
    share_now: float,
    market_movement: float
) -> int:
    """
    Freeze level belirleme:
    
    LEVEL 3 (Critical Freeze): 40dk+ freeze + share_now >= 8% + new_money >= 3000
    LEVEL 2 (Hard Freeze): 20-40dk freeze + share_now >= 4% + (market hareketli veya money >= 2000)
    LEVEL 1 (Soft Freeze): 20dk freeze + (new_money >= 1500 veya share_now >= 6%)
    
    Market movement bonus: Diğer seçenekler hareket ediyorsa freeze daha anlamlı
    """
    has_volume_inflow = new_money >= FREEZE_MIN_MONEY or share_now >= FREEZE_MIN_SHARE
    
    if not has_volume_inflow:
        return 0
    
    if freeze_duration >= L3_MIN_DURATION and share_now >= L3_MIN_SHARE and new_money >= L3_MIN_MONEY:
        return 3
    
    if freeze_duration >= L2_MIN_DURATION:
        has_market_activity = market_movement >= 2.0 or new_money >= L2_MIN_MONEY
        if share_now >= L2_MIN_SHARE and has_market_activity:
            return 2
    
    if freeze_duration >= L1_MIN_DURATION:
        if new_money >= L1_MIN_MONEY or share_now >= FREEZE_MIN_SHARE:
            return 1
    
    return 0


def detect_line_freeze(
    history: List[Dict],
    market: str,
    side: str,
    home: str = '',
    away: str = ''
) -> Optional[Dict[str, Any]]:
    """
    Line Freeze tespiti yapar.
    
    Kriterler:
    1. Oran 2+ ardışık güncellemede (20dk+) değişmemeli
    2. Hacim artmalı: new_money >= 1500 VEYA share_now >= 6%
    
    Args:
        history: Maç geçmişi (en az 3 kayıt gerekli - 20dk freeze için)
        market: Market tipi
        side: Seçenek
        home: Ev sahibi
        away: Deplasman
    
    Returns:
        Line Freeze alarm objesi veya None
    """
    if len(history) < 3:
        return None
    
    sorted_history = sorted(history, key=lambda x: x.get('ScrapedAt', ''), reverse=True)
    
    current = sorted_history[0]
    previous = sorted_history[1]
    
    latest_ts = current.get('ScrapedAt', '')
    if not latest_ts:
        return None
    
    keys = get_side_keys(market, side)
    
    freeze_duration = calculate_freeze_duration(history, side, keys)
    
    if freeze_duration < 20:
        return None
    
    curr_amt = parse_volume(current.get(keys['amt'], 0))
    prev_amt = parse_volume(previous.get(keys['amt'], 0))
    new_money = curr_amt - prev_amt
    
    share_now = parse_share(current.get(keys['pct'], 0))
    
    has_volume_inflow = new_money >= FREEZE_MIN_MONEY or share_now >= FREEZE_MIN_SHARE
    
    if not has_volume_inflow:
        return None
    
    market_type = get_market_type(market)
    if market_type == '1x2':
        all_sides = ['1', 'X', '2']
    elif market_type == 'ou25':
        all_sides = ['Over', 'Under']
    elif market_type == 'btts':
        all_sides = ['Yes', 'No']
    else:
        all_sides = ['1', 'X', '2']
    
    market_movement = calculate_market_movement(history, all_sides, side)
    
    freeze_level = get_freeze_level(freeze_duration, new_money, share_now, market_movement)
    
    if freeze_level == 0:
        return None
    
    current_odds = parse_odds(current.get(keys['odds'], 0))
    
    level_names = {1: 'Soft Freeze', 2: 'Hard Freeze', 3: 'Critical Freeze'}
    level_name = level_names.get(freeze_level, 'Freeze')
    
    alarm_type = f'line_freeze_l{freeze_level}'
    
    alarm = {
        'type': alarm_type,
        'market': market,
        'market_type': market_type,
        'side': side,
        'freeze_level': freeze_level,
        'freeze_duration': freeze_duration,
        'new_money': round(new_money, 0),
        'share_now': round(share_now, 1),
        'current_odds': current_odds,
        'market_movement': round(market_movement, 2),
        'is_alarm': True,
        'home': home,
        'away': away,
        'detail': f"L{freeze_level} {level_name} ({freeze_duration}dk, £{int(new_money):,}, {share_now:.1f}%)",
        'timestamp': latest_ts
    }
    
    print(f"[LineFreeze] {home} vs {away} ({side}): L{freeze_level} {level_name} | "
          f"Duration={freeze_duration}dk, Money=£{int(new_money):,}, Share={share_now:.1f}%")
    
    return alarm


def check_line_freeze_for_match(
    history: List[Dict],
    market: str,
    home: str,
    away: str,
    sides: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Bir maç için tüm side'larda line freeze kontrolü yapar.
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
        alarm = detect_line_freeze(history, market, side, home, away)
        if alarm:
            alarms.append(alarm)
    
    return alarms


class LineFreezeDetector:
    """
    Line Freeze Detector - Oran Donukluğu Tespit Sistemi
    
    Kriterler:
    1. 20dk+ oran değişmemiş
    2. Hacim artışı var
    3. Market hareketliyse bonus
    """
    
    MIN_FREEZE_DURATION = 20
    MIN_MONEY_INFLOW = FREEZE_MIN_MONEY
    MIN_SHARE = FREEZE_MIN_SHARE
    
    def __init__(self):
        pass
    
    def detect(self, history: List[Dict], market: str, **kwargs) -> List[Dict]:
        """Line Freeze tespiti yap"""
        return check_line_freeze_for_match(
            history=history,
            market=market,
            home=kwargs.get('home', ''),
            away=kwargs.get('away', ''),
            sides=kwargs.get('sides')
        )


line_freeze_detector = LineFreezeDetector()


if __name__ == '__main__':
    print("Line Freeze Detection Module V2")
    print("=" * 50)
    print(f"Minimum Freeze Duration: {20}dk (2 güncelleme)")
    print(f"Minimum Money Inflow: £{FREEZE_MIN_MONEY:,}")
    print(f"Minimum Share: {FREEZE_MIN_SHARE}%")
    print("\nLevel System:")
    print("  L1 (Soft): 20dk freeze + hacim 1500-3000")
    print("  L2 (Hard): 20-40dk + share %4-8 + market hareketli")
    print("  L3 (Critical): 40dk+ + share >= 8% + money >= 3000")
