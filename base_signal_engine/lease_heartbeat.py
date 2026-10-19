"""Cooperative lease heartbeat; no background worker or concurrent session access."""
from __future__ import annotations
import time
from typing import Callable


class CooperativeLeaseHeartbeat:
    """Renew a fenced lease at IO page boundaries, never on a background timer."""

    def __init__(self, renew: Callable[[], None], *, lease_seconds: int = 900,
                 clock: Callable[[], float] = time.monotonic):
        if not callable(renew) or type(lease_seconds) is not int or not 60 <= lease_seconds <= 1800:
            raise ValueError("invalid lease heartbeat configuration")
        self._renew = renew
        self._clock = clock
        self._interval = min(60.0, lease_seconds / 3)
        self._last = clock()

    def pulse(self, *, force: bool = False) -> bool:
        now = self._clock()
        if force or now - self._last >= self._interval:
            self._renew()  # failure means ownership has NOT been established
            self._last = self._clock()
            return True
        return False
