from __future__ import annotations

import os
from typing import Any, Dict, Mapping, Sequence, Tuple

from core.fixture_identity_shadow import consume_staged_betwatch_payload
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
    if raw.endswith("Z"):
        return raw[:-1] + "+00:00"
    return raw


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

    The patch intercepts the legacy fixture upsert before it can merge a rematch by
    ``match_id_hash``. On authoritative failure all later market/history/snapshot
    writer methods are blocked for that scrape attempt, so there is no silent
    fallback to the legacy physical-identity path.
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

        self._fixture_identity_authoritative_active = True
        self._fixture_identity_authoritative_failed = False

        _stage, matches = consume_staged_betwatch_payload()
        if not matches:
            _record_failure(self, "provider_identity_payload_unavailable")
            self.last_fixture_uid_authoritative_stats = {
                "error": "provider_identity_payload_unavailable"
            }
            return False

        physical_context, context_error = build_physical_event_context(matches)
        if context_error:
            _record_failure(self, context_error)
            self.last_fixture_uid_authoritative_stats = {"error": context_error}
            return False

        service_role_key = _text(os.environ.get("SUPABASE_SERVICE_ROLE_KEY"))
        if not service_role_key:
            _record_failure(self, "service_role_key_unavailable")
            self.last_fixture_uid_authoritative_stats = {
                "error": "service_role_key_unavailable"
            }
            return False

        rpc_writer = _ServiceRoleRpcWriter(self, service_role_key)
        stats = write_provider_authoritative_fixture_batch(rpc_writer, matches)
        self.last_fixture_uid_authoritative_stats = stats
        if stats.get("error"):
            _record_failure(self, str(stats["error"]))
            return False

        self._fixture_identity_event_by_physical = physical_context
        self._fixture_identity_authoritative_failed = False
        return True

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
