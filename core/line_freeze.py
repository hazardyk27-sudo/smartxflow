"""
Line Freeze Detection Algorithm V2
===================================

Oran donukluğu tespiti - Hacim artmasına rağmen oran değişmiyorsa alarm tetiklenir.
Tüm eşikler alarm_config.json üzerinden yönetilir.

Ana Kriterler:
1. Oran ardışık güncellemelerde HİÇ değişmeyecek
2. Bu sırada hacim artacak veya share_now yeterli olacak
3. Market ortalaması değişiyorsa freeze daha güçlü sayılır

Level Sistemi (config'den):
- LEVEL 1 (Soft Freeze): min_freeze_duration + l1_min_money/share
- LEVEL 2 (Hard Freeze): level2_duration + l2_min_money/share
- LEVEL 3 (Critical Freeze): level3_duration + l3_min_money/share

Önemli: Ardışık güncellemeler arasında hesaplama yapılır.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta


def get_line_freeze_config():
    """Get line freeze config from central config"""
    try:
        from core.alarm_config import load_alarm_config
        return load_alarm_config().line_freeze
    except ImportError:
        return None


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
    Freeze suresini dakika olarak hesapla.
    Oranin degismedigi ardisik guncelleme sayisini bul.
    Her guncelleme = 10dk
    
    use_max_odds_change kapaliysa, tam esitlik yerine kucuk degisimler de kabul edilir
    """
    if len(history) < 2:
        return 0
    
    cfg = get_line_freeze_config()
    max_odds_change = cfg.max_odds_change if cfg else 0.02
    use_max_odds_change = cfg.use_max_odds_change if cfg else True
    
    sorted_history = sorted(history, key=lambda x: x.get('ScrapedAt', ''), reverse=True)
    
    current_odds = parse_odds(sorted_history[0].get(keys['odds'], 0))
    if current_odds <= 0:
        return 0
    
    freeze_updates = 0
    
    for i in range(1, len(sorted_history)):
        prev_odds = parse_odds(sorted_history[i].get(keys['odds'], 0))
        
        if prev_odds <= 0:
            break
        
        if use_max_odds_change:
            odds_diff = abs(current_odds - prev_odds)
            if odds_diff <= max_odds_change:
                freeze_updates += 1
            else:
                break
        else:
            freeze_updates += 1
    
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
    Freeze level belirleme (config'den):
    
    LEVEL 3 (Critical Freeze): level3_duration + l3_min_share + l3_min_money
    LEVEL 2 (Hard Freeze): level2_duration + l2_min_share + (market hareketli veya l2_min_money)
    LEVEL 1 (Soft Freeze): min_freeze_duration + (l1_min_money veya l1_min_share)
    
    Market movement bonus: Diger secenekler hareket ediyorsa freeze daha anlamli
    use_* parametreleri ile kriterler devre disi birakilabilir
    """
    cfg = get_line_freeze_config()
    
    if cfg:
        l1_duration = cfg.min_freeze_duration
        l2_duration = cfg.level2_duration
        l3_duration = cfg.level3_duration
        l1_money = cfg.l1_min_money
        l2_money = cfg.l2_min_money
        l3_money = cfg.l3_min_money
        l1_share = cfg.l1_min_share
        l2_share = cfg.l2_min_share
        l3_share = cfg.l3_min_share
        use_money = cfg.use_money_thresholds
        use_share = cfg.use_share_thresholds
    else:
        l1_duration, l2_duration, l3_duration = 20, 20, 40
        l1_money, l2_money, l3_money = 1500, 2000, 3000
        l1_share, l2_share, l3_share = 4.0, 4.0, 8.0
        use_money, use_share = True, True
    
    money_ok = new_money >= l1_money if use_money else True
    share_ok = share_now >= l1_share if use_share else True
    has_volume_inflow = money_ok or share_ok
    
    if not has_volume_inflow:
        return 0
    
    l3_money_ok = new_money >= l3_money if use_money else True
    l3_share_ok = share_now >= l3_share if use_share else True
    if freeze_duration >= l3_duration and l3_share_ok and l3_money_ok:
        return 3
    
    l2_money_ok = new_money >= l2_money if use_money else True
    l2_share_ok = share_now >= l2_share if use_share else True
    if freeze_duration >= l2_duration:
        has_market_activity = market_movement >= 2.0 or l2_money_ok
        if l2_share_ok and has_market_activity:
            return 2
    
    if freeze_duration >= l1_duration:
        if money_ok or share_ok:
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
    1. Oran ardışık güncellemelerde değişmemeli (config'den süre)
    2. Hacim veya share eşiği sağlanmalı (config'den)
    
    Args:
        history: Maç geçmişi
        market: Market tipi
        side: Seçenek
        home: Ev sahibi
        away: Deplasman
    
    Returns:
        Line Freeze alarm objesi veya None
    """
    cfg = get_line_freeze_config()
    if cfg and not cfg.enabled:
        return None
    
    if len(history) < 3:
        return None
    
    sorted_history = sorted(history, key=lambda x: x.get('ScrapedAt', ''), reverse=True)
    
    current = sorted_history[0]
    previous = sorted_history[1]
    
    latest_ts = current.get('ScrapedAt', '')
    if not latest_ts:
        return None
    
    keys = get_side_keys(market, side)
    
    min_duration = cfg.min_freeze_duration if cfg else 20
    freeze_duration = calculate_freeze_duration(history, side, keys)
    
    if freeze_duration < min_duration:
        return None
    
    curr_amt = parse_volume(current.get(keys['amt'], 0))
    prev_amt = parse_volume(previous.get(keys['amt'], 0))
    new_money = curr_amt - prev_amt
    
    share_now = parse_share(current.get(keys['pct'], 0))
    
    min_money = cfg.l1_min_money if cfg else 1500
    min_share = cfg.l1_min_share if cfg else 4.0
    use_money = cfg.use_money_thresholds if cfg else True
    use_share = cfg.use_share_thresholds if cfg else True
    
    money_ok = new_money >= min_money if use_money else True
    share_ok = share_now >= min_share if use_share else True
    has_volume_inflow = money_ok or share_ok
    
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
    
    Kriterler (config'den dinamik olarak okunur):
    1. min_freeze_duration+ oran değişmemiş
    2. Hacim artışı var
    3. Market hareketliyse bonus
    """
    
    @property
    def MIN_FREEZE_DURATION(self) -> int:
        """Dinamik config'den freeze duration oku"""
        cfg = get_line_freeze_config()
        return cfg.min_freeze_duration if cfg else 20
    
    @property
    def MIN_MONEY_INFLOW(self) -> float:
        """Dinamik config'den min money oku"""
        cfg = get_line_freeze_config()
        return cfg.l1_min_money if cfg else 1500.0
    
    @property
    def MIN_SHARE(self) -> float:
        """Dinamik config'den min share oku"""
        cfg = get_line_freeze_config()
        return cfg.l1_min_share if cfg else 4.0
    
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
    cfg = get_line_freeze_config()
    min_duration = cfg.min_freeze_duration if cfg else 20
    min_money = cfg.l1_min_money if cfg else 1500
    min_share = cfg.l1_min_share if cfg else 4.0
    
    print("Line Freeze Detection Module V2")
    print("=" * 50)
    print(f"Minimum Freeze Duration: {min_duration}dk")
    print(f"Minimum Money Inflow: £{int(min_money):,}")
    print(f"Minimum Share: {min_share}%")
    print("\nLevel System (from config):")
    print("  L1 (Soft): min_freeze_duration + l1_min_money/share")
    print("  L2 (Hard): level2_duration + l2_min_money/share + market hareketli")
    print("  L3 (Critical): level3_duration + l3_min_money/share")
