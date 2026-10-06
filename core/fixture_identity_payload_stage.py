from __future__ import annotations

from threading import Lock
from typing import Any, Dict, Iterable, List, Mapping

_LOCK = Lock()
_PAYLOAD: List[Dict[str, Any]] | None = None


def stage_betwatch_authoritative_payload(matches: Iterable[Mapping[str, Any]]) -> None:
    """Keep the latest Betwatch payload for the guarded authoritative fixture hook.

    This stage is memory-only. It performs no I/O and is independent from the
    Part 3 shadow stage so the authoritative hook can consume its copy without
    changing legacy shadow behavior while the feature flag remains off.
    """
    payload: List[Dict[str, Any]] = []
    for match in matches or []:
        if isinstance(match, Mapping):
            payload.append(dict(match))
    global _PAYLOAD
    with _LOCK:
        _PAYLOAD = payload


def consume_betwatch_authoritative_payload() -> List[Dict[str, Any]]:
    global _PAYLOAD
    with _LOCK:
        payload = _PAYLOAD or []
        _PAYLOAD = None
    return payload


def clear_betwatch_authoritative_payload() -> None:
    global _PAYLOAD
    with _LOCK:
        _PAYLOAD = None
