"""
Momentum Spike Detection Algorithm
==================================

10 dakikalık veri sistemi için Momentum Spike tespiti.
4 kriterin tamamı sağlandığında alarm tetiklenir.

Kriterler:
1. baseline_10 > 0 (son 30 dk ortalaması)
2. spike_ratio >= 3.0 (d4 / baseline_10)
3. d4 >= market_volume_threshold (mutlak hacim)
4. share_shift >= +3 puan (pay değişimi)

Level Sistemi:
- L1: spike_ratio 3.0 - 4.0
- L2: spike_ratio 4.0 - 6.0
- L3: spike_ratio > 6.0
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta


MARKET_VOLUME_THRESHOLDS = {
    '1x2': 2000,
    'ou25': 1000,
    'btts': 800,
    'moneyway_1x2': 2000,
    'moneyway_ou25': 1000,
    'moneyway_btts': 800,
    'dropping_1x2': 2000,
    'dropping_ou25': 1000,
    'dropping_btts': 800,
}

SPIKE_RATIO_THRESHOLD = 3.0
SHARE_SHIFT_THRESHOLD = 3.0


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


def get_volume_threshold(market: str) -> int:
    """Market için minimum hacim eşiğini döndür"""
    market_lower = market.lower()
    if market_lower in MARKET_VOLUME_THRESHOLDS:
        return MARKET_VOLUME_THRESHOLDS[market_lower]
    market_type = get_market_type(market)
    return MARKET_VOLUME_THRESHOLDS.get(market_type, 2000)


def get_momentum_level(spike_ratio: float) -> int:
    """Spike ratio'ya göre level döndür (1, 2, 3)"""
    if spike_ratio >= 6.0:
        return 3
    elif spike_ratio >= 4.0:
        return 2
    elif spike_ratio >= 3.0:
        return 1
    return 0


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


def extract_volume_windows(history: List[Dict], side: str, market: str) -> Dict[str, float]:
    """
    Son 40 dk'lık history'den 4 pencere çıkar (her biri 10 dk).
    
    d1: 40-30 dk önce
    d2: 30-20 dk önce
    d3: 20-10 dk önce
    d4: 10-0 dk (şu an)
    
    IMPORTANT: Uses latest ScrapedAt timestamp as reference, not datetime.now()
    This ensures historical/backfilled data is correctly analyzed.
    
    Returns:
        {'d1': float, 'd2': float, 'd3': float, 'd4': float}
    """
    if len(history) < 2:
        return {'d1': 0, 'd2': 0, 'd3': 0, 'd4': 0}
    
    sorted_history = sorted(history, key=lambda x: x.get('ScrapedAt', ''), reverse=True)
    
    latest_ts = sorted_history[0].get('ScrapedAt', '')
    if not latest_ts:
        return {'d1': 0, 'd2': 0, 'd3': 0, 'd4': 0}
    
    try:
        if 'T' in latest_ts:
            reference_time = datetime.fromisoformat(latest_ts.replace('Z', '+00:00').split('+')[0])
        else:
            reference_time = datetime.strptime(latest_ts[:19], '%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        return {'d1': 0, 'd2': 0, 'd3': 0, 'd4': 0}
    
    windows = {'d1': 0.0, 'd2': 0.0, 'd3': 0.0, 'd4': 0.0}
    
    side_amt_key = f'Amt{side}' if side in ['1', 'X', '2'] else f'Amt{side}'
    side_stake_key = f'{side}Stake'
    side_volume_key = f'{side}Volume'
    
    prev_volumes = {}
    
    for i, record in enumerate(reversed(sorted_history)):
        scraped_at = record.get('ScrapedAt', '')
        if not scraped_at:
            continue
        
        try:
            if 'T' in scraped_at:
                record_time = datetime.fromisoformat(scraped_at.replace('Z', '+00:00').split('+')[0])
            else:
                record_time = datetime.strptime(scraped_at[:19], '%Y-%m-%d %H:%M:%S')
        except (ValueError, TypeError):
            continue
        
        minutes_before = (reference_time - record_time).total_seconds() / 60
        
        current_vol = parse_volume(
            record.get(side_amt_key) or 
            record.get(side_stake_key) or 
            record.get(side_volume_key, 0)
        )
        
        prev_vol = prev_volumes.get(side, 0)
        volume_diff = max(0, current_vol - prev_vol)
        prev_volumes[side] = current_vol
        
        if 0 <= minutes_before < 10:
            windows['d4'] += volume_diff
        elif 10 <= minutes_before < 20:
            windows['d3'] += volume_diff
        elif 20 <= minutes_before < 30:
            windows['d2'] += volume_diff
        elif 30 <= minutes_before < 40:
            windows['d1'] += volume_diff
    
    return windows


def extract_share_shift(history: List[Dict], side: str) -> float:
    """
    Son 30 dk'daki share değişimini hesapla.
    
    share_shift = share_now - share_30min_ago
    
    IMPORTANT: Uses latest ScrapedAt as reference, not datetime.now()
    
    Returns:
        float: Pay değişimi (puan olarak)
    """
    if len(history) < 2:
        return 0.0
    
    sorted_history = sorted(history, key=lambda x: x.get('ScrapedAt', ''), reverse=True)
    
    latest_ts = sorted_history[0].get('ScrapedAt', '')
    if not latest_ts:
        return 0.0
    
    try:
        if 'T' in latest_ts:
            reference_time = datetime.fromisoformat(latest_ts.replace('Z', '+00:00').split('+')[0])
        else:
            reference_time = datetime.strptime(latest_ts[:19], '%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        return 0.0
    
    side_share_key = f'Pct{side}' if side in ['1', 'X', '2'] else f'Pct{side}'
    
    share_now = parse_share(sorted_history[0].get(side_share_key, 0))
    share_30min_ago = None
    
    for record in sorted_history:
        scraped_at = record.get('ScrapedAt', '')
        if not scraped_at:
            continue
        
        try:
            if 'T' in scraped_at:
                record_time = datetime.fromisoformat(scraped_at.replace('Z', '+00:00').split('+')[0])
            else:
                record_time = datetime.strptime(scraped_at[:19], '%Y-%m-%d %H:%M:%S')
        except (ValueError, TypeError):
            continue
        
        minutes_before = (reference_time - record_time).total_seconds() / 60
        
        if 25 <= minutes_before <= 35:
            share_30min_ago = parse_share(record.get(side_share_key, 0))
            break
    
    if share_30min_ago is None:
        if len(sorted_history) >= 3:
            share_30min_ago = parse_share(sorted_history[-1].get(side_share_key, share_now))
        else:
            return 0.0
    
    return share_now - share_30min_ago


def detect_momentum_spike(
    history: List[Dict],
    market: str,
    side: str,
    home: str = '',
    away: str = ''
) -> Optional[Dict[str, Any]]:
    """
    Momentum Spike tespiti yapar.
    
    4 kriterin tamamı sağlanmalı:
    1. baseline_10 > 0
    2. spike_ratio >= 3.0
    3. d4 >= market_volume_threshold
    4. share_shift >= +3 puan
    
    IMPORTANT: Uses latest ScrapedAt for timestamp, not datetime.now()
    
    Args:
        history: Maç geçmişi (son 40+ dk'lık veriler)
        market: Market tipi (moneyway_1x2, dropping_ou25, vb.)
        side: Seçenek (1, X, 2, Over, Under, Yes, No)
        home: Ev sahibi takım
        away: Deplasman takımı
    
    Returns:
        Momentum Spike alarm objesi veya None
    """
    if len(history) < 2:
        return None
    
    sorted_history = sorted(history, key=lambda x: x.get('ScrapedAt', ''), reverse=True)
    latest_ts = sorted_history[0].get('ScrapedAt', '')
    if not latest_ts:
        return None
    
    windows = extract_volume_windows(history, side, market)
    
    d1, d2, d3, d4 = windows['d1'], windows['d2'], windows['d3'], windows['d4']
    
    baseline_10 = (d1 + d2 + d3) / 3 if (d1 + d2 + d3) > 0 else 0
    
    if baseline_10 <= 0:
        return None
    
    spike_ratio = d4 / baseline_10 if baseline_10 > 0 else 0
    
    volume_threshold = get_volume_threshold(market)
    
    share_shift = extract_share_shift(history, side)
    
    is_spike = (
        baseline_10 > 0 and
        spike_ratio >= SPIKE_RATIO_THRESHOLD and
        d4 >= volume_threshold and
        share_shift >= SHARE_SHIFT_THRESHOLD
    )
    
    if not is_spike:
        return None
    
    momentum_level = get_momentum_level(spike_ratio)
    
    market_type = get_market_type(market)
    
    alarm = {
        'type': 'momentum_spike',
        'market': market,
        'market_type': market_type,
        'side': side,
        'momentum_level': momentum_level,
        'spike_ratio': round(spike_ratio, 2),
        'share_shift': round(share_shift, 1),
        'd4_volume': round(d4, 0),
        'd1_volume': round(d1, 0),
        'd2_volume': round(d2, 0),
        'd3_volume': round(d3, 0),
        'baseline_10': round(baseline_10, 0),
        'volume_threshold': volume_threshold,
        'is_alarm': True,
        'home': home,
        'away': away,
        'detail': f"L{momentum_level} ({spike_ratio:.1f}x, +{share_shift:.0f}pts, £{int(d4):,}/10dk)",
        'timestamp': latest_ts
    }
    
    print(f"[MomentumSpike] {home} vs {away} ({side}): L{momentum_level} | "
          f"Spike={spike_ratio:.1f}x, Share=+{share_shift:.0f}pts, d4=£{int(d4):,}")
    
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
        sides: Kontrol edilecek side'lar (varsayılan: market'e göre belirlenir)
    
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
    print("Momentum Spike Detection Module")
    print("=" * 50)
    print(f"Spike Ratio Threshold: >= {SPIKE_RATIO_THRESHOLD}x")
    print(f"Share Shift Threshold: >= +{SHARE_SHIFT_THRESHOLD} puan")
    print("\nMarket Volume Thresholds:")
    for market, threshold in MARKET_VOLUME_THRESHOLDS.items():
        if '_' not in market:
            print(f"  {market.upper()}: >= £{threshold:,}")
    print("\nLevel System:")
    print("  L1: 3.0x - 4.0x")
    print("  L2: 4.0x - 6.0x")
    print("  L3: > 6.0x")
