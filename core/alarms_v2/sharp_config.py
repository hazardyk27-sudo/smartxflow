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


import json
import os

CONFIG_FILE_PATH = os.path.join(os.path.dirname(__file__), 'sharp_config.json')


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
    
    def _load_from_file(self) -> Optional[dict]:
        """Yerel JSON dosyasından config oku"""
        try:
            if os.path.exists(CONFIG_FILE_PATH):
                with open(CONFIG_FILE_PATH, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"[SharpConfig] Error loading from file: {e}")
        return None
    
    def _save_to_file(self, config_data: dict) -> bool:
        """Yerel JSON dosyasına config kaydet"""
        try:
            with open(CONFIG_FILE_PATH, 'w') as f:
                json.dump(config_data, f, indent=2)
            return True
        except Exception as e:
            print(f"[SharpConfig] Error saving to file: {e}")
            return False
    
    def get_config(self, force_refresh: bool = False) -> SharpConfig:
        """Config'i getir (cache'li)"""
        from services.supabase_client import get_supabase_client
        
        now = datetime.utcnow()
        
        if not force_refresh and self._config and self._last_fetch:
            elapsed = (now - self._last_fetch).total_seconds()
            if elapsed < self._cache_ttl_seconds:
                return self._config
        
        file_config = self._load_from_file()
        if file_config:
            self._config = SharpConfig.from_dict(file_config)
            self._last_fetch = now
            print(f"[SharpConfig] Loaded from file: score_threshold={self._config.sharp_score_threshold}")
            return self._config
        
        supabase = get_supabase_client()
        if supabase and supabase.is_available:
            try:
                config_data = supabase.get_sharp_config()
                if config_data:
                    self._config = SharpConfig.from_dict(config_data)
                    self._last_fetch = now
                    self._save_to_file(config_data)
                    print(f"[SharpConfig] Loaded from Supabase: score_threshold={self._config.sharp_score_threshold}")
                    return self._config
            except Exception as e:
                print(f"[SharpConfig] Error loading from Supabase: {e}")
        
        return SharpConfig()
    
    def save_config(self, config: SharpConfig, updated_by: str = "admin") -> bool:
        """Config'i kaydet (yerel dosya + Supabase)"""
        from services.supabase_client import get_supabase_client
        
        try:
            config.updated_by = updated_by
            config.updated_at = datetime.utcnow().isoformat()
            config_data = config.to_dict()
            
            file_saved = self._save_to_file(config_data)
            if file_saved:
                self._config = config
                self._last_fetch = datetime.utcnow()
                print(f"[SharpConfig] Saved to file by {updated_by}")
            
            supabase = get_supabase_client()
            if supabase and supabase.is_available:
                try:
                    supabase.save_sharp_config(config_data)
                    print(f"[SharpConfig] Also saved to Supabase")
                except Exception as e:
                    print(f"[SharpConfig] Supabase save failed (non-critical): {e}")
            
            return file_saved
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
