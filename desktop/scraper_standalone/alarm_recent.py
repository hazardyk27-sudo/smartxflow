"""Combined incremental alarm overrides used by Alarm Engine.

Part 1: BigMoney + MIM.
Part 2: VolumeLeader + VolumeShock.
Part 3: Sharp + Dropping + no-prefetch six-alarm runner.
"""

import alarm_recent_base as _base

for _name in dir(_base):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_base, _name)

from alarm_recent_part2 import (
    clear_part2_alarm_cache as _clear_part2_alarm_cache,
    install_part2_alarm_overrides as _install_part2_alarm_overrides,
)
from alarm_recent_part3 import (
    clear_part3_alarm_cache as _clear_part3_alarm_cache,
    install_part3_alarm_overrides as _install_part3_alarm_overrides,
)

_install_part1_alarm_overrides = _base.install_recent_alarm_overrides
_clear_part1_alarm_cache = _base.clear_recent_alarm_cache


def install_recent_alarm_overrides(calculator_cls):
    _install_part1_alarm_overrides(calculator_cls)
    _install_part2_alarm_overrides(calculator_cls)
    _install_part3_alarm_overrides(calculator_cls)


def clear_recent_alarm_cache(calculator):
    _clear_part1_alarm_cache(calculator)
    _clear_part2_alarm_cache(calculator)
    _clear_part3_alarm_cache(calculator)
