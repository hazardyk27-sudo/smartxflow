from __future__ import annotations

from unittest.mock import Mock

from core.fixture_uid_provider_gate import attach_provider_verified_fixture_uids
from core.hash_utils import make_match_id_hash


class Writer:
    def _rest_url(self, table: str) -> str:
        return f"https://example.supabase.co/rest/v1/{table}"

    def _headers(self):
        return {"apikey": "key"}


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
    }


def _hash(row):
    return make_match_id_hash(row["home"], row["away"], row["league"], row["date"])


def test_missing_provider_context_never_falls_back_to_hash_lookup():
    writer = Writer()
    row = _row()

    stats = attach_provider_verified_fixture_uids(
        writer,
        [row],
        request_get=lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("DB lookup must not run without provider context")
        ),
    )

    assert stats["tagged_rows"] == 0
    assert stats["unresolved_rows"] == 1
    assert stats["error"] == "provider_identity_context_unavailable"
    assert "fixture_uid" not in row


def test_exact_provider_registry_and_physical_fixture_proof_tags_row():
    writer = Writer()
    row = _row()
    match_hash = _hash(row)
    fixture_uid = "11111111-1111-1111-1111-111111111111"
    writer._fixture_identity_event_by_hash = {match_hash: "evt-1"}
    writer._fixture_identity_physical_by_hash = {
        match_hash: (row["league"], row["home"], row["away"], row["date"])
    }

    def fake_get(url, **kwargs):
        if url.endswith("/fixture_source_ids"):
            return _response(200, [{
                "source_event_id": "evt-1",
                "fixture_uid": fixture_uid,
            }])
        if url.endswith("/fixtures"):
            return _response(200, [{
                "fixture_uid": fixture_uid,
                "match_id_hash": match_hash,
                "league": row["league"],
                "home_team": row["home"],
                "away_team": row["away"],
                "kickoff_utc": row["date"],
            }])
        raise AssertionError(url)

    stats = attach_provider_verified_fixture_uids(
        writer,
        [row],
        request_get=fake_get,
    )

    assert stats["error"] is None
    assert stats["tagged_rows"] == 1
    assert stats["unresolved_rows"] == 0
    assert stats["identity_mismatch_rows"] == 0
    assert row["fixture_uid"] == fixture_uid


def test_new_provider_event_without_registry_mapping_stays_null_even_if_hash_exists():
    writer = Writer()
    row = _row()
    match_hash = _hash(row)
    writer._fixture_identity_event_by_hash = {match_hash: "new-event"}
    writer._fixture_identity_physical_by_hash = {
        match_hash: (row["league"], row["home"], row["away"], row["date"])
    }

    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        if url.endswith("/fixture_source_ids"):
            return _response(200, [])
        if url.endswith("/fixtures"):
            return _response(200, [])
        raise AssertionError(url)

    stats = attach_provider_verified_fixture_uids(
        writer,
        [row],
        request_get=fake_get,
    )

    assert stats["tagged_rows"] == 0
    assert stats["unresolved_rows"] == 1
    assert stats["resolved_hashes"] == 0
    assert "fixture_uid" not in row
    assert any(url.endswith("/fixture_source_ids") for url in calls)


def test_stale_physical_context_cannot_tag_current_row():
    writer = Writer()
    row = _row()
    match_hash = _hash(row)
    fixture_uid = "22222222-2222-2222-2222-222222222222"
    writer._fixture_identity_event_by_hash = {match_hash: "evt-old"}
    writer._fixture_identity_physical_by_hash = {
        match_hash: (
            row["league"],
            row["home"],
            row["away"],
            "2026-09-06T18:00:00+00:00",
        )
    }

    def fake_get(url, **kwargs):
        if url.endswith("/fixture_source_ids"):
            return _response(200, [{
                "source_event_id": "evt-old",
                "fixture_uid": fixture_uid,
            }])
        if url.endswith("/fixtures"):
            return _response(200, [{
                "fixture_uid": fixture_uid,
                "match_id_hash": match_hash,
                "league": row["league"],
                "home_team": row["home"],
                "away_team": row["away"],
                "kickoff_utc": row["date"],
            }])
        raise AssertionError(url)

    stats = attach_provider_verified_fixture_uids(
        writer,
        [row],
        request_get=fake_get,
    )

    assert stats["tagged_rows"] == 0
    assert stats["unresolved_rows"] == 1
    assert stats["identity_mismatch_rows"] == 1
    assert "fixture_uid" not in row


def test_fixture_metadata_mismatch_cannot_be_overridden_by_registry_mapping():
    writer = Writer()
    row = _row()
    match_hash = _hash(row)
    fixture_uid = "33333333-3333-3333-3333-333333333333"
    writer._fixture_identity_event_by_hash = {match_hash: "evt-3"}
    writer._fixture_identity_physical_by_hash = {
        match_hash: (row["league"], row["home"], row["away"], row["date"])
    }

    def fake_get(url, **kwargs):
        if url.endswith("/fixture_source_ids"):
            return _response(200, [{
                "source_event_id": "evt-3",
                "fixture_uid": fixture_uid,
            }])
        if url.endswith("/fixtures"):
            return _response(200, [{
                "fixture_uid": fixture_uid,
                "match_id_hash": match_hash,
                "league": row["league"],
                "home_team": "Different Home",
                "away_team": row["away"],
                "kickoff_utc": row["date"],
            }])
        raise AssertionError(url)

    stats = attach_provider_verified_fixture_uids(
        writer,
        [row],
        request_get=fake_get,
    )

    assert stats["tagged_rows"] == 0
    assert stats["unresolved_rows"] == 1
    assert stats["identity_mismatch_rows"] == 1
    assert "fixture_uid" not in row
