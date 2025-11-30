"""
V2 Sharp Alarm Configuration Manager

Yeni Sharp Money Algoritması - Basit ve Net Formül
"""

from dataclasses import dataclass, asdict, field
from typing import Dict, Any, Optional, Union
from datetime import datetime
import json
import os


def parse_decimal(value: Union[str, int, float], default: float = 0.0) -> float:
    """
    Parse decimal value with comma or dot support.
    Handles: "0,8" -> 0.8, "1.2" -> 1.2, 0.8 -> 0.8
    """
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(',', '.')
        try:
            return float(cleaned)
        except ValueError:
            return default
    return default


def clamp(x: float, min_val: float, max_val: float) -> float:
    """Değeri min-max aralığına sınırla"""
    if x < min_val:
        return min_val
    if x > max_val:
        return max_val
    return x


@dataclass
class SharpConfig:
    """
    Sharp Alarm Sistemi Konfigürasyonu
    
    Yeni Algoritma:
    - Çarpanlar (k_): Ham değeri skor bileşenine çevirir
    - Ağırlıklar (w_): Toplam %100 olmalı
    - Her kriter skoru 0-100 arasında clamp edilir
    - Final skor = (vol*w_vol + odds*w_odds + share*w_share) / 100
    """
    
    k_odds: float = 10.0
    k_volume: float = 20.0
    k_share: float = 5.0
    
    w_odds: float = 30.0
    w_volume: float = 40.0
    w_share: float = 30.0
    
    min_volume_1x2: int = 3000
    min_volume_ou25: int = 2000
    min_volume_btts: int = 1500
    
    sharp_score_threshold: int = 40
    min_market_share: float = 5.0
    
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Config'i dictionary olarak döndür"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SharpConfig':
        """Dictionary'den SharpConfig oluştur - virgül/nokta dönüşümü destekli"""
        
        w_odds = parse_decimal(data.get('w_odds'), 30.0)
        w_volume = parse_decimal(data.get('w_volume'), 40.0)
        w_share = parse_decimal(data.get('w_share'), 30.0)
        
        total_weight = w_odds + w_volume + w_share
        if total_weight != 100:
            scale = 100 / total_weight if total_weight > 0 else 1
            w_odds *= scale
            w_volume *= scale
            w_share *= scale
        
        return cls(
            k_odds=parse_decimal(data.get('k_odds'), 10.0),
            k_volume=parse_decimal(data.get('k_volume'), 20.0),
            k_share=parse_decimal(data.get('k_share'), 5.0),
            w_odds=w_odds,
            w_volume=w_volume,
            w_share=w_share,
            min_volume_1x2=int(parse_decimal(data.get('min_volume_1x2'), 3000)),
            min_volume_ou25=int(parse_decimal(data.get('min_volume_ou25'), 2000)),
            min_volume_btts=int(parse_decimal(data.get('min_volume_btts'), 1500)),
            sharp_score_threshold=int(parse_decimal(data.get('sharp_score_threshold'), 40)),
            min_market_share=parse_decimal(data.get('min_market_share'), 5.0),
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
            print(f"[SharpConfig] Loaded: threshold={self._config.sharp_score_threshold}, k_odds={self._config.k_odds}, k_vol={self._config.k_volume}, k_share={self._config.k_share}")
            return self._config
        
        supabase = get_supabase_client()
        if supabase and supabase.is_available:
            try:
                config_data = supabase.get_sharp_config()
                if config_data:
                    self._config = SharpConfig.from_dict(config_data)
                    self._last_fetch = now
                    self._save_to_file(config_data)
                    print(f"[SharpConfig] Loaded from Supabase: threshold={self._config.sharp_score_threshold}")
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
