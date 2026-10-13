from __future__ import annotations

from unittest.mock import Mock

from core import current_table_sync as sync


class Writer:
    def __init__(self):
        self._fixture_identity_authoritative_active = True
        self.last_write_errors = []
        self.events = []

    def _rest_url(self, table: str) -> str:
        return f"https://example.supabase.co/rest/v1/{table}"

    def _headers(self):
        return {"apikey": "key"}

    def upsert_rows(self, table, rows, on_conflict="home,away,date"):
        self.events.append((table, rows, on_conflict))
        return True


def _row():
    return {
        "league": "League",
        "home": "Home",
        "away": "Away",
        "date": "2026-10-13T18:00:00+00:00",
        "odds1": "2.10",
    }


def test_authoritative_uid_binding_failure_aborts_before_current_upsert(monkeypatch):
    writer = Writer()
    row = _row()

    monkeypatch.setattr(sync, "_flush_identity_shadow", lambda *args, **kwargs: None)
    monkeypatch.setattr(sync, "_table_supports_fixture_uid", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        sync,
        "attach_provider_verified_fixture_uids",
        lambda *args, **kwargs: {
            "rows": 1,
            "tagged_rows": 0,
            "unresolved_rows": 1,
            "identity_mismatch_rows": 1,
            "conflicting_existing_uid": 0,
            "legacy_hash_drift_rows": 0,
            "error": None,
        },
    )
    monkeypatch.setattr(
        sync,
        "_read_current_index",
        Mock(side_effect=AssertionError("DB current read must not run after UID failure")),
    )

    assert sync.sync_current_table(writer, "moneyway_1x2", [row]) is False
    assert writer.events == []
    assert any("authoritative fixture_uid binding incomplete" in error for error in writer.last_write_errors)


def test_authoritative_uid_binding_success_reaches_current_upsert(monkeypatch):
    writer = Writer()
    row = _row()
    fixture_uid = "22222222-2222-2222-2222-222222222222"

    monkeypatch.setattr(sync, "_flush_identity_shadow", lambda *args, **kwargs: None)
    monkeypatch.setattr(sync, "_table_supports_fixture_uid", lambda *args, **kwargs: True)

    def bind_uid(_writer, rows, request_get=None):
        rows[0]["fixture_uid"] = fixture_uid
        return {
            "rows": 1,
            "tagged_rows": 1,
            "unresolved_rows": 0,
            "identity_mismatch_rows": 0,
            "conflicting_existing_uid": 0,
            "legacy_hash_drift_rows": 1,
            "provider_context_hashes": 0,
            "error": None,
        }

    monkeypatch.setattr(sync, "attach_provider_verified_fixture_uids", bind_uid)
    monkeypatch.setattr(sync, "_read_current_index", lambda *args, **kwargs: {})
    monkeypatch.setattr(sync, "_delete_stale_ids", lambda *args, **kwargs: True)

    assert sync.sync_current_table(writer, "moneyway_1x2", [row]) is True
    assert writer.events[0][1][0]["fixture_uid"] == fixture_uid
    assert writer.last_write_errors == []
