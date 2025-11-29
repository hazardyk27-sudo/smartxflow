"""
Alarm Configuration System
==========================

Tüm alarm eşiklerini ve kriterlerini merkezi olarak yönetir.
JSON dosyasına persist edilir ve Admin Panel üzerinden güncellenebilir.
"""

import json
import os
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, field, asdict
from copy import deepcopy


CONFIG_PATH = Path("alarm_config.json")

_alarm_config: Optional['AlarmConfig'] = None


@dataclass
class SharpConfig:
    """Sharp Money Alarm Configuration"""
    enabled: bool = True
    volume_1x2: float = 5000.0
    volume_ou25: float = 3000.0
    volume_btts: float = 2000.0
    volume_shock_multiplier: float = 2.0
    odds_drop_min: float = 1.0
    share_shift_min: float = 2.0
    score_threshold_sharp: int = 20
    score_threshold_medium: int = 10
    use_volume_shock: bool = True
    use_odds_drop: bool = True
    use_share_shift: bool = True


@dataclass
class DroppingConfig:
    """Dropping Alert Configuration"""
    enabled: bool = True
    drop_threshold: float = 7.0
    level2_drop: float = 10.0
    level3_drop: float = 15.0
    persistence_minutes: int = 30
    use_level2: bool = True
    use_level3: bool = True
    use_persistence: bool = True


@dataclass
class ReversalConfig:
    """Reversal Move Configuration"""
    enabled: bool = True
    min_retracement: float = 50.0
    min_drop_before_reversal: float = 5.0
    use_retracement: bool = True
    use_min_drop: bool = True


@dataclass
class MomentumConfig:
    """Momentum Spike Configuration"""
    enabled: bool = True
    volume_1x2: float = 1000.0
    volume_ou25: float = 750.0
    volume_btts: float = 500.0
    share_now_min: float = 6.0
    percentage_change_min: float = 7.0
    odds_drop_min: float = 4.0
    use_new_money: bool = True
    use_share_now: bool = True
    use_percentage_change: bool = True
    use_odds_drop: bool = True
    min_criteria_to_trigger: int = 2
    level1_money: float = 1500.0
    level2_money: float = 3000.0
    level3_money: float = 5000.0


@dataclass
class LineFreezeConfig:
    """Line Freeze Configuration"""
    enabled: bool = True
    min_freeze_duration: int = 20
    level2_duration: int = 20
    level3_duration: int = 40
    l1_min_money: float = 1500.0
    l2_min_money: float = 2000.0
    l3_min_money: float = 3000.0
    l1_min_share: float = 4.0
    l2_min_share: float = 4.0
    l3_min_share: float = 8.0
    max_odds_change: float = 0.02
    use_money_thresholds: bool = True
    use_share_thresholds: bool = True
    use_max_odds_change: bool = True


@dataclass
class VolumeShiftConfig:
    """Volume Shift Configuration"""
    enabled: bool = True
    volume_1x2: float = 1000.0
    volume_ou25: float = 750.0
    volume_btts: float = 500.0
    dominance_threshold: float = 50.0
    use_volume_thresholds: bool = True
    use_dominance: bool = True


@dataclass
class BigMoneyConfig:
    """Big Money Configuration"""
    enabled: bool = True
    min_money_10min: float = 15000.0
    one_shot_min: float = 10000.0
    use_10min_threshold: bool = True
    use_one_shot: bool = True


@dataclass
class PublicSurgeConfig:
    """Public Surge Configuration"""
    enabled: bool = True
    min_money: float = 500.0
    max_odds_change: float = 0.02
    use_min_money: bool = True
    use_max_odds_change: bool = True


@dataclass
class AlarmConfig:
    """Master Alarm Configuration"""
    config_version: int = 1
    sharp: SharpConfig = field(default_factory=SharpConfig)
    dropping: DroppingConfig = field(default_factory=DroppingConfig)
    reversal: ReversalConfig = field(default_factory=ReversalConfig)
    momentum: MomentumConfig = field(default_factory=MomentumConfig)
    line_freeze: LineFreezeConfig = field(default_factory=LineFreezeConfig)
    volume_shift: VolumeShiftConfig = field(default_factory=VolumeShiftConfig)
    big_money: BigMoneyConfig = field(default_factory=BigMoneyConfig)
    public_surge: PublicSurgeConfig = field(default_factory=PublicSurgeConfig)


def config_to_dict(cfg: AlarmConfig) -> Dict[str, Any]:
    """Convert AlarmConfig to dictionary"""
    return {
        'config_version': cfg.config_version,
        'sharp': asdict(cfg.sharp),
        'dropping': asdict(cfg.dropping),
        'reversal': asdict(cfg.reversal),
        'momentum': asdict(cfg.momentum),
        'line_freeze': asdict(cfg.line_freeze),
        'volume_shift': asdict(cfg.volume_shift),
        'big_money': asdict(cfg.big_money),
        'public_surge': asdict(cfg.public_surge),
    }


def dict_to_config(data: Dict[str, Any]) -> AlarmConfig:
    """Convert dictionary to AlarmConfig"""
    cfg = AlarmConfig()
    
    if 'config_version' in data:
        cfg.config_version = data['config_version']
    
    if 'sharp' in data:
        cfg.sharp = SharpConfig(**data['sharp'])
    if 'dropping' in data:
        cfg.dropping = DroppingConfig(**data['dropping'])
    if 'reversal' in data:
        cfg.reversal = ReversalConfig(**data['reversal'])
    if 'momentum' in data:
        cfg.momentum = MomentumConfig(**data['momentum'])
    if 'line_freeze' in data:
        cfg.line_freeze = LineFreezeConfig(**data['line_freeze'])
    if 'volume_shift' in data:
        cfg.volume_shift = VolumeShiftConfig(**data['volume_shift'])
    if 'big_money' in data:
        cfg.big_money = BigMoneyConfig(**data['big_money'])
    if 'public_surge' in data:
        cfg.public_surge = PublicSurgeConfig(**data['public_surge'])
    
    return cfg


def increment_config_version() -> int:
    """Increment config version and return new version"""
    cfg = load_alarm_config()
    cfg.config_version += 1
    save_alarm_config(cfg)
    return cfg.config_version


def get_config_version() -> int:
    """Get current config version"""
    cfg = load_alarm_config()
    return cfg.config_version


def load_alarm_config() -> AlarmConfig:
    """Load alarm config from JSON file"""
    global _alarm_config
    
    if _alarm_config is not None:
        return _alarm_config
    
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            _alarm_config = dict_to_config(data)
            print(f"[AlarmConfig] Loaded from {CONFIG_PATH}")
        except Exception as e:
            print(f"[AlarmConfig] Error loading config: {e}, using defaults")
            _alarm_config = AlarmConfig()
            save_alarm_config(_alarm_config)
    else:
        _alarm_config = AlarmConfig()
        save_alarm_config(_alarm_config)
        print(f"[AlarmConfig] Created default config at {CONFIG_PATH}")
    
    return _alarm_config


def save_alarm_config(cfg: AlarmConfig) -> bool:
    """Save alarm config to JSON file"""
    global _alarm_config
    
    try:
        data = config_to_dict(cfg)
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        _alarm_config = cfg
        print(f"[AlarmConfig] Saved to {CONFIG_PATH}")
        return True
    except Exception as e:
        print(f"[AlarmConfig] Error saving config: {e}")
        return False


def reload_alarm_config() -> AlarmConfig:
    """Force reload config from file"""
    global _alarm_config
    _alarm_config = None
    return load_alarm_config()


def get_config() -> AlarmConfig:
    """Shorthand for load_alarm_config"""
    return load_alarm_config()


def get_momentum_volume_threshold(market_type: str) -> float:
    """Get momentum volume threshold for market type"""
    cfg = load_alarm_config().momentum
    thresholds = {
        '1x2': cfg.volume_1x2,
        'ou25': cfg.volume_ou25,
        'btts': cfg.volume_btts,
    }
    return thresholds.get(market_type, cfg.volume_1x2)


def get_sharp_volume_threshold(market_type: str) -> float:
    """Get sharp volume threshold for market type"""
    cfg = load_alarm_config().sharp
    thresholds = {
        '1x2': cfg.volume_1x2,
        'ou25': cfg.volume_ou25,
        'btts': cfg.volume_btts,
    }
    return thresholds.get(market_type, cfg.volume_1x2)


def get_volume_shift_threshold(market_type: str) -> float:
    """Get volume shift threshold for market type"""
    cfg = load_alarm_config().volume_shift
    thresholds = {
        '1x2': cfg.volume_1x2,
        'ou25': cfg.volume_ou25,
        'btts': cfg.volume_btts,
    }
    return thresholds.get(market_type, cfg.volume_1x2)


def is_alarm_enabled(alarm_type: str) -> bool:
    """Check if an alarm type is enabled"""
    cfg = load_alarm_config()
    
    type_map = {
        'sharp': cfg.sharp.enabled,
        'medium_movement': cfg.sharp.enabled,
        'dropping': cfg.dropping.enabled,
        'dropping_l1': cfg.dropping.enabled,
        'dropping_l2': cfg.dropping.enabled,
        'dropping_l3': cfg.dropping.enabled,
        'dropping_preview': cfg.dropping.enabled,
        'reversal': cfg.reversal.enabled,
        'reversal_move': cfg.reversal.enabled,
        'momentum': cfg.momentum.enabled,
        'momentum_spike': cfg.momentum.enabled,
        'momentum_spike_l1': cfg.momentum.enabled,
        'momentum_spike_l2': cfg.momentum.enabled,
        'momentum_spike_l3': cfg.momentum.enabled,
        'line_freeze': cfg.line_freeze.enabled,
        'line_freeze_l1': cfg.line_freeze.enabled,
        'line_freeze_l2': cfg.line_freeze.enabled,
        'line_freeze_l3': cfg.line_freeze.enabled,
        'volume_shift': cfg.volume_shift.enabled,
        'big_money': cfg.big_money.enabled,
        'public_surge': cfg.public_surge.enabled,
    }
    
    return type_map.get(alarm_type, True)
