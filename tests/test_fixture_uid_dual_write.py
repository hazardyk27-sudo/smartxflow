from __future__ import annotations

from unittest.mock import Mock

from core import current_table_sync as sync
from core import fixture_uid_dual_write as dual
from core.hash_utils import make_match_id_hash


class Writer:
    def __init__(self):
        self.last_write_errors = []
        self.events = []

    def _rest_url(self, table: str) -> str:
        return f"https://example.supabase.co/rest/v1/{table}"

    def _headers(self):
        return {"apikey": "key"}

    def upsert_rows(self, table, rows, on_conflict="home,away,date"):
        self.events.append((table, [dict(row) for row in rows], on_conflict))
        return True


def _response(status: int, payload=None):
    response = Mock()
    response.status_code = status
    response.json.return_value = [] if payload is None else payload
    return response


def _row():
    return {
        "league": "Test League",
        "home": "Home FC",
        "away": "Away FC",
        "date": "2026-10-06T18:00:00+00:00",
        "odds1": "2.1",
    }


def test_attach_tags_row_with_existing_fixture_uid_and_caches_lookup():
    writer = Writer()
    row = _row()
    match_hash = make_match_id_hash(row["home"], row["away"], row["league"], row["date"])
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs.get("params")))
        if url.endswith("/moneyway_1x2"):
            return _response(200, [])
        if url.endswith("/fixtures"):
            return _response(200, [{
                "match_id_hash": match_hash,
                "fixture_uid": "11111111-1111-1111-1111-111111111111",
            }])
        raise AssertionError(url)

    stats = dual.attach_fixture_uids_to_current_rows(
        writer, "moneyway_1x2", [row], request_get=fake_get
    )
    assert stats["error"] is None
    assert stats["column_available"] is True
    assert stats["tagged_rows"] == 1
    assert stats["unresolved_rows"] == 0
    assert row["fixture_uid"] == "11111111-1111-1111-1111-111111111111"

    second = _row()
    stats2 = dual.attach_fixture_uids_to_current_rows(
        writer, "moneyway_1x2", [second], request_get=fake_get
    )
    assert stats2["cache_hits"] == 1
    assert second["fixture_uid"] == row["fixture_uid"]
    fixture_calls = [url for url, _ in calls if url.endswith("/fixtures")]
    assert len(fixture_calls) == 1


def test_missing_schema_column_fails_soft_and_does_not_mutate_row():
    writer = Writer()
    row = _row()

    def fake_get(url, **kwargs):
        assert url.endswith("/moneyway_1x2")
        return _response(400, {"message": "column fixture_uid does not exist"})

    stats = dual.attach_fixture_uids_to_current_rows(
        writer, "moneyway_1x2", [row], request_get=fake_get
    )
    assert stats["attempted"] is True
    assert stats["column_available"] is False
    assert stats["error"] == "fixture_uid_column_unavailable"
    assert "fixture_uid" not in row


def test_fixture_lookup_failure_fails_soft_without_overwriting_legacy_fields():
    writer = Writer()
    row = _row()

    def fake_get(url, **kwargs):
        if url.endswith("/moneyway_1x2"):
            return _response(200, [])
        if url.endswith("/fixtures"):
            return _response(503, [])
        raise AssertionError(url)

    stats = dual.attach_fixture_uids_to_current_rows(
        writer, "moneyway_1x2", [row], request_get=fake_get
    )
    assert stats["tagged_rows"] == 0
    assert stats["unresolved_rows"] == 1
    assert "HTTP 503" in stats["error"]
    assert row["odds1"] == "2.1"
    assert "fixture_uid" not in row


def test_current_sync_tags_original_rows_only_with_provider_and_physical_proof(monkeypatch):
    writer = Writer()
    row = _row()
    match_hash = make_match_id_hash(row["home"], row["away"], row["league"], row["date"])
    expected_uid = "22222222-2222-2222-2222-222222222222"
    writer._fixture_identity_event_by_hash = {match_hash: "evt-1"}
    writer._fixture_identity_physical_by_hash = {
        match_hash: (row["league"], row["home"], row["away"], row["date"])
    }

    def fake_get(url, **kwargs):
        params = kwargs.get("params") or {}
        if url.endswith("/moneyway_1x2") and params.get("select") == "fixture_uid":
            return _response(200, [])
        if url.endswith("/fixture_source_ids"):
            return _response(200, [{
                "source_event_id": "evt-1",
                "fixture_uid": expected_uid,
            }])
        if url.endswith("/fixtures"):
            return _response(200, [{
                "fixture_uid": expected_uid,
                "match_id_hash": match_hash,
                "league": row["league"],
                "home_team": row["home"],
                "away_team": row["away"],
                "kickoff_utc": row["date"],
            }])
        if "moneyway_1x2?select=id,league,home,away,date" in url:
            return _response(200, [])
        raise AssertionError((url, kwargs))

    monkeypatch.setattr(sync.requests, "get", fake_get)
    monkeypatch.setattr(sync.requests, "delete", Mock(return_value=_response(204)))
    monkeypatch.setattr(sync, "_flush_identity_shadow", lambda *args, **kwargs: None)

    assert sync.sync_current_table(writer, "moneyway_1x2", [row]) is True
    assert row["fixture_uid"] == expected_uid
    assert writer.events[0][1][0]["fixture_uid"] == expected_uid
    assert writer.events[0][2] == "league,home,away,date"


def test_current_sync_leaves_uid_null_when_physical_context_is_stale(monkeypatch):
    writer = Writer()
    row = _row()
    match_hash = make_match_id_hash(row["home"], row["away"], row["league"], row["date"])
    writer._fixture_identity_event_by_hash = {match_hash: "evt-old"}
    writer._fixture_identity_physical_by_hash = {
        match_hash: (row["league"], row["home"], row["away"], "2026-09-01T18:00:00+00:00")
    }

    def fake_get(url, **kwargs):
        params = kwargs.get("params") or {}
        if url.endswith("/moneyway_1x2") and params.get("select") == "fixture_uid":
            return _response(200, [])
        if url.endswith("/fixture_source_ids"):
            return _response(200, [{
                "source_event_id": "evt-old",
                "fixture_uid": "33333333-3333-3333-3333-333333333333",
            }])
        if url.endswith("/fixtures"):
            return _response(200, [{
                "fixture_uid": "33333333-3333-3333-3333-333333333333",
                "match_id_hash": match_hash,
                "league": row["league"],
                "home_team": row["home"],
                "away_team": row["away"],
                "kickoff_utc": row["date"],
            }])
        if "moneyway_1x2?select=id,league,home,away,date" in url:
            return _response(200, [])
        raise AssertionError((url, kwargs))

    monkeypatch.setattr(sync.requests, "get", fake_get)
    monkeypatch.setattr(sync.requests, "delete", Mock(return_value=_response(204)))
    monkeypatch.setattr(sync, "_flush_identity_shadow", lambda *args, **kwargs: None)

    assert sync.sync_current_table(writer, "moneyway_1x2", [row]) is True
    assert "fixture_uid" not in row
    assert "fixture_uid" not in writer.events[0][1][0]


def test_existing_conflicting_uid_is_never_overwritten():
    writer = Writer()
    row = _row()
    row["fixture_uid"] = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    match_hash = make_match_id_hash(row["home"], row["away"], row["league"], row["date"])

    def fake_get(url, **kwargs):
        if url.endswith("/moneyway_1x2"):
            return _response(200, [])
        if url.endswith("/fixtures"):
            return _response(200, [{
                "match_id_hash": match_hash,
                "fixture_uid": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            }])
        raise AssertionError(url)

    stats = dual.attach_fixture_uids_to_current_rows(
        writer, "moneyway_1x2", [row], request_get=fake_get
    )
    assert stats["conflicting_existing_uid"] == 1
    assert row["fixture_uid"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
