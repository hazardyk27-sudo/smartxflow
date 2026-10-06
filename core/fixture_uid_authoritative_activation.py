from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from core.fixture_identity_payload_stage import consume_betwatch_authoritative_payload
from core.fixture_identity_shadow import clear_betwatch_identity_stage
from core.fixture_identity_v2 import extract_betwatch_identity
from core.fixture_uid_authoritative_writer import write_provider_authoritative_fixture_batch

_FLAG = "SMARTXFLOW_FIXTURE_UID_AUTHORITATIVE_WRITER"
_PATCHED = False
_TRUE_VALUES = {"1", "true", "yes", "on", "enabled"}
_WRITE_METHODS = ("upsert_rows", "replace_table", "append_history", "insert_snapshots")


def authoritative_writer_enabled() -> bool:
    return str(os.environ.get(_FLAG, "")).strip().lower() in _TRUE_VALUES


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_instant(value: Any) -> str:
    raw = _text(value)
    if not raw:
        return ""
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return raw
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat(timespec="seconds")


def build_physical_event_context(
    matches: Sequence[Mapping[str, Any]],
) -> Tuple[Dict[tuple[str, str, str, str], str], str | None]:
    """Build exact physical-row -> Betwatch event context for current-table UID tagging."""
    result: Dict[tuple[str, str, str, str], str] = {}
    event_physical: Dict[str, set[tuple[str, str, str, str]]] = {}
    physical_events: Dict[tuple[str, str, str, str], set[str]] = {}

    for match in matches or []:
        identity = extract_betwatch_identity(match)
        if identity is None:
            return {}, "missing_provider_id"
        teams = match.get("teams") or {}
        if not isinstance(teams, Mapping):
            return {}, "incomplete_physical_identity"
        home = _text(teams.get("v1"))
        away = _text(teams.get("v2"))
        league = _text(match.get("league"))
        kickoff = _normalize_instant(match.get("kickoff"))
        event_id = _text(identity.event_id)
        if not event_id or not home or not away or not league or not kickoff:
            return {}, "incomplete_physical_identity"

        physical = (league, home, away, kickoff)
        event_physical.setdefault(event_id, set()).add(physical)
        physical_events.setdefault(physical, set()).add(event_id)
        result[physical] = event_id

    if any(len(values) != 1 for values in event_physical.values()):
        return {}, "provider_event_collision"
    if any(len(values) != 1 for values in physical_events.values()):
        return {}, "physical_event_collision"
    return result, None


class _ServiceRoleRpcWriter:
    def __init__(self, legacy_writer: Any, service_role_key: str):
        self._legacy_writer = legacy_writer
        self._service_role_key = service_role_key

    def _rest_url(self, table: str) -> str:
        return self._legacy_writer._rest_url(table)

    def _headers(self) -> Dict[str, str]:
        return {
            "apikey": self._service_role_key,
            "Authorization": f"Bearer {self._service_role_key}",
            "Content-Type": "application/json",
        }


def _record_failure(writer: Any, error: str) -> None:
    writer._fixture_identity_authoritative_failed = True
    writer._fixture_identity_authoritative_active = True
    errors = getattr(writer, "last_write_errors", None)
    message = f"fixture identity authoritative writer blocked: {error}"
    if isinstance(errors, list) and message not in errors:
        errors.append(message)


def write_authoritative_fixture_batch_with_service_role(
    writer: Any,
    matches: Sequence[Mapping[str, Any]],
    *,
    observed_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the provider-authoritative fixture RPC with the service-role credential.

    This is the canonical Part 8 activation entry point for the server scraper.
    It clears the old hash-scoped shadow stage, validates an exact physical-event
    context, and never falls back to the legacy fixture upsert on failure.
    """
    writer._fixture_identity_authoritative_active = True
    writer._fixture_identity_authoritative_failed = False

    # The caller may pass the fetched payload directly; clear the memory-only copy
    # so it cannot be replayed by the patched legacy writer later in the same run.
    consume_betwatch_authoritative_payload()
    clear_betwatch_identity_stage()

    if not matches:
        stats = {"error": "provider_identity_payload_unavailable"}
        writer.last_fixture_uid_authoritative_stats = stats
        _record_failure(writer, stats["error"])
        return stats

    physical_context, context_error = build_physical_event_context(matches)
    if context_error:
        stats = {"error": context_error}
        writer.last_fixture_uid_authoritative_stats = stats
        _record_failure(writer, context_error)
        return stats

    service_role_key = _text(os.environ.get("SUPABASE_SERVICE_ROLE_KEY"))
    if not service_role_key:
        stats = {"error": "service_role_key_unavailable"}
        writer.last_fixture_uid_authoritative_stats = stats
        _record_failure(writer, stats["error"])
        return stats

    rpc_writer = _ServiceRoleRpcWriter(writer, service_role_key)
    stats = write_provider_authoritative_fixture_batch(
        rpc_writer,
        matches,
        observed_at=observed_at,
    )
    writer.last_fixture_uid_authoritative_stats = stats
    if stats.get("error"):
        _record_failure(writer, str(stats["error"]))
        return stats

    writer._fixture_identity_event_by_physical = physical_context
    writer._fixture_identity_authoritative_failed = False
    return stats


def _guard_write_method(original):
    def guarded(self, *args, **kwargs):
        if (
            authoritative_writer_enabled()
            and getattr(self, "_fixture_identity_authoritative_failed", False)
        ):
            return False
        return original(self, *args, **kwargs)

    guarded._smartxflow_fixture_uid_guard = True
    return guarded


def install_provider_authoritative_fixture_writer_patch() -> bool:
    """Patch SupabaseWriter once; behavior changes only when the explicit flag is on.

    The patch is a safety net for runtimes that still call the legacy
    ``upsert_fixtures`` method. The canonical server path calls
    ``write_authoritative_fixture_batch_with_service_role`` directly.
    """
    global _PATCHED
    if _PATCHED:
        return True

    try:
        import standalone_scraper
    except Exception:
        return False

    writer_cls = getattr(standalone_scraper, "SupabaseWriter", None)
    if writer_cls is None:
        return False

    original_upsert = getattr(writer_cls, "upsert_fixtures", None)
    if not callable(original_upsert):
        return False
    if getattr(original_upsert, "_smartxflow_fixture_uid_authoritative", False):
        _PATCHED = True
        return True

    def upsert_fixtures_v2(self, fixtures):
        if not authoritative_writer_enabled():
            return original_upsert(self, fixtures)

        matches = consume_betwatch_authoritative_payload()
        stats = write_authoritative_fixture_batch_with_service_role(self, matches)
        return not bool(stats.get("error"))

    upsert_fixtures_v2._smartxflow_fixture_uid_authoritative = True
    writer_cls.upsert_fixtures = upsert_fixtures_v2

    for method_name in _WRITE_METHODS:
        original = getattr(writer_cls, method_name, None)
        if not callable(original):
            continue
        if getattr(original, "_smartxflow_fixture_uid_guard", False):
            continue
        setattr(writer_cls, method_name, _guard_write_method(original))

    _PATCHED = True
    return True
