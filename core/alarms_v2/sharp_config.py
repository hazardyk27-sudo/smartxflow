"""
V2 Sharp Alarm Configuration Manager

Supabase'den config okuma/yazma ve cache yönetimi.
"""

from dataclasses import dataclass, asdict, field
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
import json


@dataclass
class SharpConfig:
    """Sharp Alarm Sistemi Konfigürasyonu"""
    
    weight_volume: float = 1.0
    weight_odds: float = 1.0
    weight_share: float = 0.5
    weight_momentum: float = 0.5
    
    volume_multiplier: float = 10.0
    normalization_factor: float = 1.0
    
    min_volume_1x2: int = 3000
    min_volume_ou25: int = 2000
    min_volume_btts: int = 1500
    
    sharp_score_threshold: int = 50
    min_share_pct_threshold: int = 15
    
    shock_ranges: Dict[str, Tuple[float, float]] = field(default_factory=lambda: {
        "normal": (0, 2),
        "light": (2, 4),
        "strong": (4, 6),
        "very_strong": (6, 8),
        "extreme": (8, 999)
    })
    
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Config'i dictionary olarak döndür"""
        d = asdict(self)
        if isinstance(d.get('shock_ranges'), dict):
            d['shock_ranges'] = {k: list(v) for k, v in d['shock_ranges'].items()}
        return d
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SharpConfig':
        """Dictionary'den SharpConfig oluştur"""
        shock_ranges = data.get('shock_ranges', {})
        if isinstance(shock_ranges, str):
            shock_ranges = json.loads(shock_ranges)
        if isinstance(shock_ranges, dict):
            shock_ranges = {k: tuple(v) if isinstance(v, list) else v for k, v in shock_ranges.items()}
        
        return cls(
            weight_volume=float(data.get('weight_volume', 1.0)),
            weight_odds=float(data.get('weight_odds', 1.0)),
            weight_share=float(data.get('weight_share', 0.5)),
            weight_momentum=float(data.get('weight_momentum', 0.5)),
            volume_multiplier=float(data.get('volume_multiplier', 10.0)),
            normalization_factor=float(data.get('normalization_factor', 1.0)),
            min_volume_1x2=int(data.get('min_volume_1x2', 3000)),
            min_volume_ou25=int(data.get('min_volume_ou25', 2000)),
            min_volume_btts=int(data.get('min_volume_btts', 1500)),
            sharp_score_threshold=int(data.get('sharp_score_threshold', 50)),
            min_share_pct_threshold=int(data.get('min_share_pct_threshold', 15)),
            shock_ranges=shock_ranges,
            updated_at=data.get('updated_at'),
            updated_by=data.get('updated_by')
        )
    
    def get_min_volume(self, market_type: str) -> int:
        """Market tipine göre minimum hacim eşiğini döndür"""
        if '1x2' in market_type.lower():
            return self.min_volume_1x2
        elif 'ou25' in market_type.lower() or 'o/u' in market_type.lower():
            return self.min_volume_ou25
        elif 'btts' in market_type.lower():
            return self.min_volume_btts
        return self.min_volume_1x2
    
    def get_shock_level(self, shock_x: float) -> str:
        """shockX değerine göre şok seviyesini döndür"""
        for level, (min_val, max_val) in self.shock_ranges.items():
            if min_val <= shock_x < max_val:
                return level
        return "extreme"


class SharpConfigManager:
    """Sharp Config yönetimi ve cache"""
    
    _instance = None
    _config: Optional[SharpConfig] = None
    _last_fetch: Optional[datetime] = None
    _cache_ttl_seconds: int = 60
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def get_config(self, force_refresh: bool = False) -> SharpConfig:
        """Config'i getir (cache'li)"""
        from services.supabase_client import get_supabase_client
        
        now = datetime.utcnow()
        
        if not force_refresh and self._config and self._last_fetch:
            elapsed = (now - self._last_fetch).total_seconds()
            if elapsed < self._cache_ttl_seconds:
                return self._config
        
        supabase = get_supabase_client()
        if not supabase or not supabase.is_available:
            print("[SharpConfig] Supabase not available, using defaults")
            return SharpConfig()
        
        try:
            config_data = supabase.get_sharp_config()
            if config_data:
                self._config = SharpConfig.from_dict(config_data)
                self._last_fetch = now
                print(f"[SharpConfig] Loaded from Supabase: score_threshold={self._config.sharp_score_threshold}")
                return self._config
        except Exception as e:
            print(f"[SharpConfig] Error loading: {e}")
        
        return SharpConfig()
    
    def save_config(self, config: SharpConfig, updated_by: str = "admin") -> bool:
        """Config'i Supabase'e kaydet"""
        from services.supabase_client import get_supabase_client
        
        supabase = get_supabase_client()
        if not supabase or not supabase.is_available:
            print("[SharpConfig] Supabase not available")
            return False
        
        try:
            config.updated_by = updated_by
            config.updated_at = datetime.utcnow().isoformat()
            
            success = supabase.save_sharp_config(config.to_dict())
            if success:
                self._config = config
                self._last_fetch = datetime.utcnow()
                print(f"[SharpConfig] Saved to Supabase by {updated_by}")
            return success
        except Exception as e:
            print(f"[SharpConfig] Error saving: {e}")
            return False
    
    def invalidate_cache(self):
        """Cache'i geçersiz kıl"""
        self._last_fetch = None


def get_sharp_config(force_refresh: bool = False) -> SharpConfig:
    """Global config getter"""
    manager = SharpConfigManager()
    return manager.get_config(force_refresh)


def save_sharp_config(config: SharpConfig, updated_by: str = "admin") -> bool:
    """Global config saver"""
    manager = SharpConfigManager()
    return manager.save_config(config, updated_by)
