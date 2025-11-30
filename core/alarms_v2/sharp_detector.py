"""
V2 Sharp Alarm Detector

SharpScore hesaplama algoritması ve alarm tespiti.
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime

from .base import AlarmDetectorV2, AlarmResult
from .sharp_config import SharpConfig, get_sharp_config


@dataclass
class SharpEvaluationResult:
    """Sharp alarm değerlendirme sonucu"""
    alarm: bool
    sharp_score: float
    level: str
    reason: Optional[str]
    details: Dict[str, Any]


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


def calculate_shock_x(current_stake: float, avg_stake: float) -> float:
    """Hacim şoku hesapla (yeni bahis / son N ortalama)"""
    if avg_stake <= 0:
        return 0.0
    return current_stake / avg_stake


def evaluate_sharp_alarm(
    config: SharpConfig,
    market_type: str,
    total_market_volume: float,
    current_share_pct: float,
    shock_x: float,
    drop_pct: float,
    share_shift: float,
    momentum_score: float
) -> SharpEvaluationResult:
    """
    Sharp alarm değerlendirmesi.
    
    Args:
        config: SharpConfig ayarları
        market_type: '1x2' | 'ou25' | 'btts'
        total_market_volume: Toplam piyasa hacmi
        current_share_pct: Seçeneğin mevcut pazar payı (%)
        shock_x: Hacim şoku (yeni bahis / son 10 ortalama)
        drop_pct: Oran düşüş yüzdesi (%)
        share_shift: Pazar payı değişimi (eski pay - yeni pay)
        momentum_score: Momentum skoru (0-10)
    
    Returns:
        SharpEvaluationResult
    """
    
    details = {
        "market_type": market_type,
        "total_market_volume": total_market_volume,
        "current_share_pct": current_share_pct,
        "shock_x": shock_x,
        "drop_pct": drop_pct,
        "share_shift": share_shift,
        "momentum_score": momentum_score
    }
    
    min_volume = config.get_min_volume(market_type)
    if total_market_volume < min_volume:
        return SharpEvaluationResult(
            alarm=False,
            sharp_score=0.0,
            level="none",
            reason="LOW_MARKET_VOLUME",
            details={**details, "min_volume": min_volume}
        )
    
    if current_share_pct < config.min_share_pct_threshold:
        return SharpEvaluationResult(
            alarm=False,
            sharp_score=0.0,
            level="none",
            reason="LOW_SHARE_PCT",
            details={**details, "min_share_pct": config.min_share_pct_threshold}
        )
    
    volume_base_score = shock_x * config.volume_multiplier
    
    sharp_score_raw = (
        volume_base_score * config.weight_volume +
        drop_pct * config.weight_odds +
        share_shift * config.weight_share +
        momentum_score * config.weight_momentum
    )
    
    sharp_score = sharp_score_raw / config.normalization_factor if config.normalization_factor else sharp_score_raw
    
    details["volume_base_score"] = volume_base_score
    details["sharp_score_raw"] = sharp_score_raw
    details["sharp_score"] = sharp_score
    
    if sharp_score < config.sharp_score_threshold:
        return SharpEvaluationResult(
            alarm=False,
            sharp_score=sharp_score,
            level="none",
            reason="LOW_SHARP_SCORE",
            details=details
        )
    
    if sharp_score >= config.threshold_real_sharp:
        level = "Real Sharp"
    elif sharp_score >= config.threshold_very_sharp:
        level = "Very Sharp"
    elif sharp_score >= config.threshold_strong_sharp:
        level = "Strong Sharp"
    else:
        level = "Sharp"
    
    return SharpEvaluationResult(
        alarm=True,
        sharp_score=sharp_score,
        level=level,
        reason=None,
        details=details
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
        
        total_volume = parse_volume(current.get('Volume', '0'))
        
        current_pct = self._get_percentage(current, side, market_type)
        prev_pct = self._get_percentage(previous, side, market_type) if previous else current_pct
        
        current_odds = self._get_odds(current, side, market_type)
        prev_odds = self._get_odds(previous, side, market_type) if previous else current_odds
        
        current_stake = parse_volume(self._get_amount(current, side, market_type))
        
        lookback = min(10, len(history))
        stake_sum = 0.0
        for i in range(lookback):
            stake_sum += parse_volume(self._get_amount(history[-(i+1)], side, market_type))
        avg_stake = stake_sum / lookback if lookback > 0 else 0
        
        shock_x = calculate_shock_x(current_stake, avg_stake)
        
        drop_pct = 0.0
        if prev_odds > 0 and current_odds > 0 and current_odds < prev_odds:
            drop_pct = ((prev_odds - current_odds) / prev_odds) * 100
        
        share_shift = current_pct - prev_pct
        
        momentum_score = self._calculate_momentum(history, side, market_type)
        
        result = evaluate_sharp_alarm(
            config=config,
            market_type=market_type,
            total_market_volume=total_volume,
            current_share_pct=current_pct,
            shock_x=shock_x,
            drop_pct=drop_pct,
            share_shift=share_shift,
            momentum_score=momentum_score
        )
        
        if not result.alarm:
            return None
        
        return AlarmResult(
            alarm_type="sharp",
            score=int(result.sharp_score),
            level=result.level.lower().replace(" ", "_"),
            is_triggered=True,
            side=side,
            odds_from=prev_odds,
            odds_to=current_odds,
            money_diff=current_stake - avg_stake if avg_stake > 0 else 0,
            timestamp=datetime.utcnow(),
            details={
                **result.details,
                "match_id": match_id,
                "market": market,
                "sharp_level": result.level
            },
            reason=None
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
        return parse_percentage(data.get(key, '0'))
    
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
        val = data.get(key, 0)
        
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
        return data.get(key, '0')
    
    def _calculate_momentum(self, history: List[Dict], side: str, market_type: str) -> float:
        """Momentum skoru hesapla (0-10)"""
        if len(history) < 3:
            return 0.0
        
        recent = history[-3:]
        pcts = [self._get_percentage(h, side, market_type) for h in recent]
        
        if len(pcts) < 3:
            return 0.0
        
        trend = (pcts[-1] - pcts[0])
        momentum = min(10, max(0, abs(trend) / 2))
        
        return momentum
