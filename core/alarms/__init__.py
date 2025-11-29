"""
SmartXFlow Alarm System
========================

Tüm alarm modülleri bu klasörde toplanmıştır.

Modüller:
- alarm_config: Alarm yapılandırma yönetimi
- alarm_model: Alarm veri modelleri
- alarm_safety: Güvenli alarm kaydetme (fingerprint deduplication)
- alarm_state: Alarm durumu yönetimi (dropping persistence)
- main: Ana alarm analizi (detect_and_save_alarms)
- real_sharp: Sharp Money tespiti
- dropping_alert: Dropping Alert tespiti
- line_freeze: Line Freeze tespiti
- momentum_spike: Momentum Spike tespiti
- volume_shift: Volume Shift tespiti
- reversal_move: Reversal Move tespiti
"""

from core.alarms.alarm_config import (
    load_alarm_config,
    save_alarm_config,
    AlarmConfig,
    SharpConfig,
    DroppingConfig,
    ReversalConfig,
    MomentumConfig,
    LineFreezeConfig,
    VolumeShiftConfig,
    BigMoneyConfig,
    PublicSurgeConfig
)

from core.alarms.alarm_safety import (
    AlarmSafetyGuard,
    generate_alarm_fingerprint,
    log_failed_alarm,
    get_failed_alarms,
    retry_failed_alarms
)

from core.alarms.alarm_state import (
    get_dropping_level,
    update_dropping_state,
    mark_dropping_alarm_fired,
    DROPPING_PERSISTENCE_MINUTES
)

from core.alarms.main import (
    analyze_match_alarms,
    format_alarm_for_ticker,
    format_alarm_for_modal,
    ALARM_TYPES
)

from core.alarms.real_sharp import SharpDetector
from core.alarms.dropping_alert import DroppingAlertDetector, detect_dropping_alerts
from core.alarms.line_freeze import LineFreezeDetector, detect_line_freeze
from core.alarms.momentum_spike import detect_momentum_spike, check_momentum_spike_for_match
from core.alarms.volume_shift import VolumeShiftDetector, detect_volume_shift
from core.alarms.reversal_move import ReversalMoveDetector

__all__ = [
    'load_alarm_config',
    'save_alarm_config',
    'AlarmConfig',
    'SharpConfig',
    'DroppingConfig',
    'ReversalConfig',
    'MomentumConfig',
    'LineFreezeConfig',
    'VolumeShiftConfig',
    'BigMoneyConfig',
    'PublicSurgeConfig',
    'AlarmSafetyGuard',
    'generate_alarm_fingerprint',
    'log_failed_alarm',
    'get_failed_alarms',
    'retry_failed_alarms',
    'get_dropping_level',
    'update_dropping_state',
    'mark_dropping_alarm_fired',
    'DROPPING_PERSISTENCE_MINUTES',
    'analyze_match_alarms',
    'format_alarm_for_ticker',
    'format_alarm_for_modal',
    'ALARM_TYPES',
    'SharpDetector',
    'DroppingAlertDetector',
    'detect_dropping_alerts',
    'LineFreezeDetector',
    'detect_line_freeze',
    'detect_momentum_spike',
    'check_momentum_spike_for_match',
    'VolumeShiftDetector',
    'detect_volume_shift',
    'ReversalMoveDetector',
]
