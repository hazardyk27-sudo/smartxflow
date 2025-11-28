"""
Real Sharp Detection System
4 Ana Kriter ile Profesyonel Sharp Money Tespiti

Kriter 1: Hacim Şoku (Volume Shock) - 2x+ normal hacim
Kriter 2: Pazar Payı (Market Concentration) - %35+ tek seçeneğe
Kriter 3: Oran Düşüşü (Price Impact) - %2+ düşüş
Kriter 4: Market Payı Artışı (Share Shift) - +5 puan artış

Tüm kriterler eş zamanlı sağlanmalı.
Sharp Skor: 0-100 arası hesaplanır.
70+ = Gerçek Sharp alarmı
40-69 = Orta Seviye Hareket (alarm yok, UI'da göster)
<40 = Yok say
"""

from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from statistics import median

def parse_money(val: Any) -> float:
    """Parse money value from string"""
    if not val:
        return 0.0
    try:
        return float(str(val).replace(',', '').replace('£', '').replace(' ', ''))
    except:
        return 0.0

def parse_odds(val: Any) -> float:
    """Parse odds value from string"""
    if not val or val == '-':
        return 0.0
    try:
        s = str(val).split('\n')[0].replace(',', '.')
        return float(s)
    except:
        return 0.0

def parse_pct(val: Any) -> float:
    """Parse percentage value from string"""
    if not val:
        return 0.0
    try:
        return float(str(val).replace('%', '').replace(',', '.').strip())
    except:
        return 0.0


class RealSharpDetector:
    """
    Gerçek Sharp Tespit Sistemi
    4 ana kriter ile profesyonel sharp money tespiti yapar.
    """
    
    WINDOW_MINUTES = 10
    LOOKBACK_MINUTES = 60
    
    VOLUME_SHOCK_MULTIPLIER = 2.0
    MARKET_SHARE_THRESHOLD = 35.0
    ODDS_DROP_THRESHOLD = 2.0
    SHARE_SHIFT_THRESHOLD = 5.0
    
    SCORE_THRESHOLDS = {
        'real_sharp': 70,
        'medium_movement': 40
    }
    
    def __init__(self):
        pass
    
    def get_sides_for_market(self, market: str) -> List[Dict[str, str]]:
        """Get side definitions for market type"""
        if market in ['moneyway_1x2', 'dropping_1x2']:
            return [
                {'key': '1', 'amt': 'Amt1', 'odds': 'Odds1', 'pct': 'Pct1'},
                {'key': 'X', 'amt': 'AmtX', 'odds': 'OddsX', 'pct': 'PctX'},
                {'key': '2', 'amt': 'Amt2', 'odds': 'Odds2', 'pct': 'Pct2'}
            ]
        elif market in ['moneyway_ou25', 'dropping_ou25']:
            return [
                {'key': 'Under', 'amt': 'AmtUnder', 'odds': 'Under', 'pct': 'PctUnder'},
                {'key': 'Over', 'amt': 'AmtOver', 'odds': 'Over', 'pct': 'PctOver'}
            ]
        elif market in ['moneyway_btts', 'dropping_btts']:
            return [
                {'key': 'Yes', 'amt': 'AmtYes', 'odds': 'OddsYes', 'pct': 'PctYes'},
                {'key': 'No', 'amt': 'AmtNo', 'odds': 'OddsNo', 'pct': 'PctNo'}
            ]
        return []
    
    def calculate_normal_volume(self, history: List[Dict], side: Dict[str, str]) -> float:
        """
        Son 1 saat içindeki 10 dakikalık hacim pencerelerinin medyanını hesapla.
        Bu "normal" hacmi temsil eder.
        """
        if len(history) < 2:
            return 0.0
        
        try:
            now_ts = history[-1].get('ScrapedAt', '')
            if not now_ts:
                return 0.0
            
            if 'T' in now_ts:
                now_dt = datetime.fromisoformat(now_ts.replace('Z', '+00:00').split('+')[0])
            else:
                now_dt = datetime.strptime(now_ts[:19], '%Y-%m-%d %H:%M:%S')
            
            one_hour_ago = now_dt - timedelta(minutes=self.LOOKBACK_MINUTES)
            
            ten_min_volumes = []
            for i in range(len(history) - 1):
                row = history[i]
                next_row = history[i + 1]
                
                row_ts = row.get('ScrapedAt', '')
                if not row_ts:
                    continue
                
                if 'T' in row_ts:
                    row_dt = datetime.fromisoformat(row_ts.replace('Z', '+00:00').split('+')[0])
                else:
                    row_dt = datetime.strptime(row_ts[:19], '%Y-%m-%d %H:%M:%S')
                
                if row_dt < one_hour_ago:
                    continue
                
                next_ts = next_row.get('ScrapedAt', '')
                if not next_ts:
                    continue
                
                if 'T' in next_ts:
                    next_dt = datetime.fromisoformat(next_ts.replace('Z', '+00:00').split('+')[0])
                else:
                    next_dt = datetime.strptime(next_ts[:19], '%Y-%m-%d %H:%M:%S')
                
                time_diff = (next_dt - row_dt).total_seconds() / 60
                if 8 <= time_diff <= 12:
                    amt_diff = parse_money(next_row.get(side['amt'], 0)) - parse_money(row.get(side['amt'], 0))
                    if amt_diff > 0:
                        ten_min_volumes.append(amt_diff)
            
            if len(ten_min_volumes) >= 2:
                return median(ten_min_volumes)
            elif len(ten_min_volumes) == 1:
                return ten_min_volumes[0]
            else:
                return 0.0
                
        except Exception as e:
            print(f"[RealSharp] Error calculating normal volume: {e}")
            return 0.0
    
    def calculate_volume_shock(self, current_volume: float, normal_volume: float) -> Tuple[bool, float]:
        """
        Kriter 1: Hacim Şoku
        Son 10 dk'da gelen para, normal 10 dk hacminin 2+ katı mı?
        """
        if normal_volume <= 0:
            return False, 0.0
        
        multiplier = current_volume / normal_volume
        is_shock = multiplier >= self.VOLUME_SHOCK_MULTIPLIER
        
        return is_shock, multiplier
    
    def calculate_market_share(self, selection_volume: float, total_market_volume: float) -> Tuple[bool, float]:
        """
        Kriter 2: Pazar Payı (Market Concentration)
        Son 10 dk'da toplam paranın %35+'ı tek seçeneğe mi gitti?
        """
        if total_market_volume <= 0:
            return False, 0.0
        
        share_pct = (selection_volume / total_market_volume) * 100
        is_concentrated = share_pct >= self.MARKET_SHARE_THRESHOLD
        
        return is_concentrated, share_pct
    
    def calculate_odds_drop(self, odds_from: float, odds_to: float) -> Tuple[bool, float]:
        """
        Kriter 3: Oran Düşüşü (Price Impact)
        Son 10 dk'da oran %2+ düştü mü?
        """
        if odds_from <= 0:
            return False, 0.0
        
        drop_pct = ((odds_from - odds_to) / odds_from) * 100
        is_significant_drop = drop_pct >= self.ODDS_DROP_THRESHOLD
        
        return is_significant_drop, drop_pct
    
    def calculate_share_shift(self, share_before: float, share_after: float) -> Tuple[bool, float]:
        """
        Kriter 4: Market Payı Artışı (Share Shift)
        Seçeneğin market payı +5 puan+ arttı mı?
        """
        shift_points = share_after - share_before
        is_significant_shift = shift_points >= self.SHARE_SHIFT_THRESHOLD
        
        return is_significant_shift, shift_points
    
    def calculate_sharp_score(
        self,
        volume_shock_multiplier: float,
        market_share_pct: float,
        odds_drop_pct: float,
        share_shift_points: float
    ) -> int:
        """
        Sharp Skoru Hesaplama (0-100)
        
        Hacim şoku (max 30 puan):
            2 kat = 20, 3+ kat = 30
        
        Pazar payı (max 25 puan):
            %35-50 = 18, %50+ = 25
        
        Oran düşüşü (max 25 puan):
            %2-4 = 12, %4-7 = 18, %7+ = 25
        
        Pay artışı (max 20 puan):
            +5-8 puan = 10, +8-12 puan = 15, +12+ puan = 20
        """
        score = 0
        
        if volume_shock_multiplier >= 3.0:
            score += 30
        elif volume_shock_multiplier >= 2.0:
            score += 20
        elif volume_shock_multiplier >= 1.5:
            score += 10
        
        if market_share_pct >= 50.0:
            score += 25
        elif market_share_pct >= 35.0:
            score += 18
        elif market_share_pct >= 25.0:
            score += 10
        
        if odds_drop_pct >= 7.0:
            score += 25
        elif odds_drop_pct >= 4.0:
            score += 18
        elif odds_drop_pct >= 2.0:
            score += 12
        elif odds_drop_pct >= 1.0:
            score += 5
        
        if share_shift_points >= 12.0:
            score += 20
        elif share_shift_points >= 8.0:
            score += 15
        elif share_shift_points >= 5.0:
            score += 10
        elif share_shift_points >= 3.0:
            score += 5
        
        return min(score, 100)
    
    def detect_real_sharp(
        self,
        history: List[Dict],
        market: str,
        match_id: str = ''
    ) -> List[Dict[str, Any]]:
        """
        Ana Tespit Fonksiyonu
        History verisini analiz eder ve Real Sharp tespiti yapar.
        
        Returns: List of detected sharp movements with full details
        """
        if len(history) < 3:
            return []
        
        sides = self.get_sides_for_market(market)
        if not sides:
            return []
        
        detected = []
        current = history[-1]
        
        try:
            now_ts = current.get('ScrapedAt', '')
            if not now_ts:
                return []
            
            if 'T' in now_ts:
                now_dt = datetime.fromisoformat(now_ts.replace('Z', '+00:00').split('+')[0])
            else:
                now_dt = datetime.strptime(now_ts[:19], '%Y-%m-%d %H:%M:%S')
            
            window_start = now_dt - timedelta(minutes=self.WINDOW_MINUTES)
            
        except Exception as e:
            print(f"[RealSharp] Error parsing timestamp: {e}")
            return []
        
        base_row = None
        for row in reversed(history[:-1]):
            try:
                row_ts = row.get('ScrapedAt', '')
                if not row_ts:
                    continue
                
                if 'T' in row_ts:
                    row_dt = datetime.fromisoformat(row_ts.replace('Z', '+00:00').split('+')[0])
                else:
                    row_dt = datetime.strptime(row_ts[:19], '%Y-%m-%d %H:%M:%S')
                
                if row_dt <= window_start:
                    base_row = row
                    break
            except:
                continue
        
        if not base_row:
            if len(history) >= 2:
                base_row = history[-2]
            else:
                return []
        
        total_volume_before = 0.0
        total_volume_after = 0.0
        
        for side in sides:
            total_volume_before += parse_money(base_row.get(side['amt'], 0))
            total_volume_after += parse_money(current.get(side['amt'], 0))
        
        total_market_volume = total_volume_after - total_volume_before
        if total_market_volume <= 0:
            total_market_volume = 1.0
        
        for side in sides:
            base_amt = parse_money(base_row.get(side['amt'], 0))
            current_amt = parse_money(current.get(side['amt'], 0))
            base_odds = parse_odds(base_row.get(side['odds'], 0))
            current_odds = parse_odds(current.get(side['odds'], 0))
            base_pct = parse_pct(base_row.get(side['pct'], 0))
            current_pct = parse_pct(current.get(side['pct'], 0))
            
            selection_volume = current_amt - base_amt
            if selection_volume <= 0:
                continue
            
            normal_volume = self.calculate_normal_volume(history, side)
            
            vol_shock_ok, vol_shock_mult = self.calculate_volume_shock(selection_volume, normal_volume)
            
            mkt_share_ok, mkt_share_pct = self.calculate_market_share(selection_volume, total_market_volume)
            
            odds_drop_ok, odds_drop_pct = self.calculate_odds_drop(base_odds, current_odds)
            
            share_shift_ok, share_shift_pts = self.calculate_share_shift(base_pct, current_pct)
            
            sharp_score = self.calculate_sharp_score(
                vol_shock_mult,
                mkt_share_pct,
                odds_drop_pct,
                share_shift_pts
            )
            
            all_criteria_met = vol_shock_ok and mkt_share_ok and odds_drop_ok and share_shift_ok
            
            is_real_sharp = all_criteria_met and sharp_score >= self.SCORE_THRESHOLDS['real_sharp']
            
            is_medium_movement = (
                not is_real_sharp and 
                sharp_score >= self.SCORE_THRESHOLDS['medium_movement']
            )
            
            if sharp_score >= self.SCORE_THRESHOLDS['medium_movement']:
                base_ts = base_row.get('ScrapedAt', '')
                current_ts = current.get('ScrapedAt', '')
                
                result = {
                    'type': 'sharp' if is_real_sharp else 'medium_movement',
                    'is_real_sharp': is_real_sharp,
                    'is_medium_movement': is_medium_movement,
                    'sharp_score': sharp_score,
                    'side': side['key'],
                    'money_diff': selection_volume,
                    'odds_from': base_odds,
                    'odds_to': current_odds,
                    'window_start': base_ts,
                    'window_end': current_ts,
                    'timestamp': current_ts,
                    
                    'criteria': {
                        'volume_shock_ok': vol_shock_ok,
                        'market_share_ok': mkt_share_ok,
                        'odds_drop_ok': odds_drop_ok,
                        'share_shift_ok': share_shift_ok,
                        'all_met': all_criteria_met
                    },
                    
                    'volume_shock': round(vol_shock_mult, 2),
                    'market_share': round(mkt_share_pct, 1),
                    'odds_drop_percent': round(odds_drop_pct, 2),
                    'share_shift_points': round(share_shift_pts, 1),
                    
                    'raw_data': {
                        'selection_volume': selection_volume,
                        'normal_volume': normal_volume,
                        'total_market_volume': total_market_volume,
                        'base_pct': base_pct,
                        'current_pct': current_pct,
                        'base_odds': base_odds,
                        'current_odds': current_odds
                    }
                }
                
                detected.append(result)
                
                print(f"[RealSharp] {side['key']}: Score={sharp_score}, "
                      f"VolShock={vol_shock_mult:.1f}x, MktShare={mkt_share_pct:.0f}%, "
                      f"OddsDrop={odds_drop_pct:.1f}%, ShareShift={share_shift_pts:+.0f}pts, "
                      f"RealSharp={is_real_sharp}")
        
        detected.sort(key=lambda x: x['sharp_score'], reverse=True)
        
        return detected


real_sharp_detector = RealSharpDetector()


def detect_real_sharp(history: List[Dict], market: str, match_id: str = '') -> List[Dict[str, Any]]:
    """Convenience function for Real Sharp detection"""
    return real_sharp_detector.detect_real_sharp(history, market, match_id)
