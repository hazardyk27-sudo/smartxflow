"""
V2 Sharp Alarm Detector

Yeni Sharp Money Algoritması:
- drop_pct = ((prev_odds - curr_odds) / prev_odds) * 100  (negatif ise 0)
- shockX = current_volume / avg_previous_volume  (min 1, üst limit yok)
- share_diff = current_share - previous_share  (negatif ise 0)

- odds_score = clamp(drop_pct * k_odds, 0, 100)
- volume_score = clamp(shockX * k_volume, 0, 100)
- share_score = clamp(share_diff * k_share, 0, 100)

- SharpScore = (volume_score * w_volume + odds_score * w_odds + share_score * w_share) / 100
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional, List
from datetime import datetime

from .base import AlarmDetectorV2, AlarmResult
from .sharp_config import SharpConfig, get_sharp_config, clamp


@dataclass
class SharpEvaluationResult:
    """Sharp alarm değerlendirme sonucu"""
    alarm: bool
    sharp_score: float
    reason: Optional[str]
    details: Dict[str, Any]
    new_bet_amount: float = 0.0
    odd_old: float = 0.0
    odd_new: float = 0.0
    drop_pct: float = 0.0


def parse_volume(volume_str: str) -> float:
    """Volume string'ini sayıya çevir (örn: '£1,234' -> 1234.0)"""
    if not volume_str:
        return 0.0
    try:
        clean = str(volume_str).replace('£', '').replace(',', '').replace(' ', '').strip()
        return float(clean) if clean else 0.0
    except (ValueError, TypeError):
        return 0.0


def parse_percentage(pct_str: str) -> float:
    """Percentage string'ini sayıya çevir (örn: '45%' -> 45.0)"""
    if not pct_str:
        return 0.0
    try:
        clean = str(pct_str).replace('%', '').strip()
        return float(clean) if clean else 0.0
    except (ValueError, TypeError):
        return 0.0


def get_value(data: Dict, key: str, default: Any = None) -> Any:
    """Case-insensitive dict value getter - both 'Volume' and 'volume' work"""
    if not data:
        return default
    if key in data:
        return data[key]
    key_lower = key.lower()
    if key_lower in data:
        return data[key_lower]
    key_upper = key[0].upper() + key[1:] if key else key
    if key_upper in data:
        return data[key_upper]
    return default


def evaluate_sharp_alarm(
    config: SharpConfig,
    market_type: str,
    total_market_volume: float,
    current_share_pct: float,
    shock_x: float,
    drop_pct: float,
    share_diff: float,
    new_bet_amount: float = 0.0,
    odd_old: float = 0.0,
    odd_new: float = 0.0
) -> SharpEvaluationResult:
    """
    Sharp alarm değerlendirmesi - YENİ ALGORİTMA
    
    Args:
        config: SharpConfig ayarları
        market_type: '1x2' | 'ou25' | 'btts'
        total_market_volume: Toplam piyasa hacmi
        current_share_pct: Seçeneğin mevcut pazar payı (%)
        shock_x: Hacim şoku (current_vol / avg_prev_vol, min 1)
        drop_pct: Oran düşüş yüzdesi (%, negatif ise 0)
        share_diff: Pazar payı değişimi (%, negatif ise 0)
        new_bet_amount: Gelen yeni bahis miktarı
        odd_old: Eski oran
        odd_new: Yeni oran
    
    Returns:
        SharpEvaluationResult
    """
    
    details = {
        "market_type": market_type,
        "total_market_volume": total_market_volume,
        "current_share_pct": current_share_pct,
        "shock_x": shock_x,
        "drop_pct": drop_pct,
        "share_diff": share_diff
    }
    
    min_volume = config.get_min_volume(market_type)
    if total_market_volume < min_volume:
        return SharpEvaluationResult(
            alarm=False,
            sharp_score=0.0,
            reason="LOW_MARKET_VOLUME",
            details={**details, "min_volume": min_volume}
        )
    
    if current_share_pct < config.min_market_share:
        return SharpEvaluationResult(
            alarm=False,
            sharp_score=0.0,
            reason="LOW_MARKET_SHARE",
            details={**details, "min_market_share": config.min_market_share}
        )
    
    odds_score_raw = drop_pct * config.k_odds
    odds_score = clamp(odds_score_raw, 0, 100)
    
    volume_score_raw = shock_x * config.k_volume
    volume_score = clamp(volume_score_raw, 0, 100)
    
    share_score_raw = share_diff * config.k_share
    share_score = clamp(share_score_raw, 0, 100)
    
    sharp_score = (volume_score * config.w_volume + 
                   odds_score * config.w_odds + 
                   share_score * config.w_share) / 100
    
    print(f"[SharpScore] market={market_type} shockX={shock_x:.2f} drop={drop_pct:.1f}% share_diff={share_diff:+.1f}%")
    print(f"[SharpScore] raw: vol={volume_score_raw:.1f} odds={odds_score_raw:.1f} share={share_score_raw:.1f}")
    print(f"[SharpScore] clamped: vol={volume_score:.1f} odds={odds_score:.1f} share={share_score:.1f}")
    print(f"[SharpScore] final = ({volume_score:.1f}*{config.w_volume} + {odds_score:.1f}*{config.w_odds} + {share_score:.1f}*{config.w_share}) / 100 = {sharp_score:.1f}")
    
    details["odds_score"] = odds_score
    details["volume_score"] = volume_score
    details["share_score"] = share_score
    details["sharp_score"] = sharp_score
    
    if sharp_score < config.sharp_score_threshold:
        return SharpEvaluationResult(
            alarm=False,
            sharp_score=sharp_score,
            reason="LOW_SHARP_SCORE",
            details=details
        )
    
    return SharpEvaluationResult(
        alarm=True,
        sharp_score=sharp_score,
        reason=None,
        details=details,
        new_bet_amount=new_bet_amount,
        odd_old=odd_old,
        odd_new=odd_new,
        drop_pct=drop_pct
    )


class SharpDetectorV2(AlarmDetectorV2):
    """V2 Sharp Alarm Detector"""
    
    @property
    def alarm_type(self) -> str:
        return "sharp"
    
    def __init__(self):
        self._config: Optional[SharpConfig] = None
    
    def get_config(self) -> SharpConfig:
        """Güncel config'i al"""
        if self._config is None:
            self._config = get_sharp_config()
        return self._config
    
    def refresh_config(self):
        """Config'i yenile"""
        self._config = get_sharp_config(force_refresh=True)
    
    def detect(self, history: List[Dict], market: str, match_id: str) -> List[AlarmResult]:
        """
        Maç geçmişinden Sharp alarm tespit et.
        
        Args:
            history: Maç için odds/volume geçmişi
            market: Market tipi (moneyway_1x2, dropping_ou25, etc.)
            match_id: Maç ID
        
        Returns:
            Tespit edilen alarmlar listesi
        """
        if len(history) < 2:
            return []
        
        config = self.get_config()
        results = []
        
        market_type = self._extract_market_type(market)
        
        sides = self._get_sides_for_market(market)
        
        for side in sides:
            try:
                alarm_result = self._detect_for_side(history, market, market_type, match_id, side, config)
                if alarm_result:
                    results.append(alarm_result)
            except Exception as e:
                print(f"[SharpDetectorV2] Error for {match_id}/{side}: {e}")
        
        return results
    
    def compute_score(self, **kwargs) -> int:
        """Alarm skoru hesapla"""
        config = self.get_config()
        result = evaluate_sharp_alarm(config, **kwargs)
        return int(result.sharp_score)
    
    def _extract_market_type(self, market: str) -> str:
        """Market string'inden tip çıkar"""
        market_lower = market.lower()
        if '1x2' in market_lower:
            return '1x2'
        elif 'ou25' in market_lower:
            return 'ou25'
        elif 'btts' in market_lower:
            return 'btts'
        return '1x2'
    
    def _get_sides_for_market(self, market: str) -> List[str]:
        """Market için kontrol edilecek seçenekleri döndür"""
        market_lower = market.lower()
        if '1x2' in market_lower:
            return ['1', 'X', '2']
        elif 'ou25' in market_lower:
            return ['Over', 'Under']
        elif 'btts' in market_lower:
            return ['Yes', 'No']
        return ['1', 'X', '2']
    
    def _detect_for_side(
        self, 
        history: List[Dict], 
        market: str, 
        market_type: str,
        match_id: str, 
        side: str,
        config: SharpConfig
    ) -> Optional[AlarmResult]:
        """Belirli bir seçenek için alarm tespit et"""
        
        current = history[-1]
        previous = history[-2] if len(history) >= 2 else None
        
        total_volume = parse_volume(get_value(current, 'Volume', '0'))
        
        current_pct = self._get_percentage(current, side, market_type)
        prev_pct = self._get_percentage(previous, side, market_type) if previous else current_pct
        
        current_odds = self._get_odds(current, side, market_type)
        prev_odds = self._get_odds(previous, side, market_type) if previous else current_odds
        
        current_stake = parse_volume(self._get_amount(current, side, market_type))
        
        # Volume Kriteri: Minimum hacim kontrolü
        min_volume = config.get_min_volume(market_type)
        if total_volume < min_volume:
            return None  # Minimum hacim karşılanmadı
        
        # V2 Shock Hesaplama: Uzun vadeli karşılaştırma
        # Son 10 snapshot ortalaması vs önceki 20-40 snapshot ortalaması
        history_len = len(history)
        
        # Recent: Son 10 snapshot (100 dakika ~ 1.5 saat)
        recent_count = min(10, history_len)
        recent_sum = 0.0
        for i in range(recent_count):
            recent_sum += parse_volume(self._get_amount(history[-(i+1)], side, market_type))
        recent_avg = recent_sum / recent_count if recent_count > 0 else current_stake
        
        # Older: 11. snapshot'tan geriye doğru (1.5 saat - 6 saat öncesi arası)
        older_start = 10  # 11. snapshot'tan başla
        older_count = min(30, history_len - older_start)  # En fazla 30 snapshot (5 saat)
        
        if older_count > 0:
            older_sum = 0.0
            for i in range(older_count):
                idx = -(older_start + i + 1)
                if abs(idx) <= history_len:
                    older_sum += parse_volume(self._get_amount(history[idx], side, market_type))
            older_avg = older_sum / older_count
        else:
            older_avg = recent_avg
        
        # Shock X hesapla
        if older_avg > 0:
            shock_x = recent_avg / older_avg
            if shock_x < 1:
                shock_x = 1.0
        else:
            shock_x = 1.0
        
        # Debug: Yüksek shock varsa logla
        if shock_x >= 1.5:
            print(f"[ShockDebug] {match_id}/{side}: recent_avg=£{recent_avg:,.0f} older_avg=£{older_avg:,.0f} shock={shock_x:.2f}x (history={history_len})")
        
        drop_pct = 0.0
        if prev_odds > 0 and current_odds > 0 and current_odds < prev_odds:
            drop_pct = ((prev_odds - current_odds) / prev_odds) * 100
        
        share_diff = current_pct - prev_pct
        if share_diff < 0:
            share_diff = 0.0
        
        prev_stake = parse_volume(self._get_amount(previous, side, market_type)) if previous else 0
        new_bet_amount = current_stake - prev_stake if prev_stake > 0 else current_stake
        
        result = evaluate_sharp_alarm(
            config=config,
            market_type=market_type,
            total_market_volume=total_volume,
            current_share_pct=current_pct,
            shock_x=shock_x,
            drop_pct=drop_pct,
            share_diff=share_diff,
            new_bet_amount=new_bet_amount,
            odd_old=prev_odds,
            odd_new=current_odds
        )
        
        if not result.alarm:
            return None
        
        return AlarmResult(
            alarm_type="sharp",
            score=int(result.sharp_score),
            is_triggered=True,
            side=side,
            odds_from=prev_odds,
            odds_to=current_odds,
            money_diff=new_bet_amount,
            timestamp=datetime.utcnow(),
            details={
                **result.details,
                "match_id": match_id,
                "market": market
            },
            reason=None,
            sharp_score=result.sharp_score,
            new_bet_amount=new_bet_amount,
            drop_pct=drop_pct
        )
    
    def _get_percentage(self, data: Dict, side: str, market_type: str) -> float:
        """Seçenek için yüzde değerini al"""
        if not data:
            return 0.0
        
        key_map = {
            '1x2': {'1': 'Pct1', 'X': 'PctX', '2': 'Pct2'},
            'ou25': {'Over': 'PctOver', 'Under': 'PctUnder'},
            'btts': {'Yes': 'PctYes', 'No': 'PctNo'}
        }
        
        key = key_map.get(market_type, {}).get(side, f'Pct{side}')
        return parse_percentage(get_value(data, key, '0'))
    
    def _get_odds(self, data: Dict, side: str, market_type: str) -> float:
        """Seçenek için oran değerini al"""
        if not data:
            return 0.0
        
        key_map = {
            '1x2': {'1': 'Odds1', 'X': 'OddsX', '2': 'Odds2'},
            'ou25': {'Over': 'Over', 'Under': 'Under'},
            'btts': {'Yes': 'OddsYes', 'No': 'OddsNo'}
        }
        
        key = key_map.get(market_type, {}).get(side, f'Odds{side}')
        val = get_value(data, key, 0)
        
        try:
            return float(str(val).split('\n')[0]) if val else 0.0
        except (ValueError, TypeError):
            return 0.0
    
    def _get_amount(self, data: Dict, side: str, market_type: str) -> str:
        """Seçenek için miktar değerini al"""
        if not data:
            return '0'
        
        key_map = {
            '1x2': {'1': 'Amt1', 'X': 'AmtX', '2': 'Amt2'},
            'ou25': {'Over': 'AmtOver', 'Under': 'AmtUnder'},
            'btts': {'Yes': 'AmtYes', 'No': 'AmtNo'}
        }
        
        key = key_map.get(market_type, {}).get(side, f'Amt{side}')
        return get_value(data, key, '0')
