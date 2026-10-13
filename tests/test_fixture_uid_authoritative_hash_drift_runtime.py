from __future__ import annotations

from unittest.mock import Mock

from core.fixture_uid_provider_gate import attach_provider_verified_fixture_uids
from core.hash_utils import make_match_id_hash


class Writer:
    def __init__(self):
        self._fixture_identity_authoritative_active = True

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
        "league": "FIFA Women's World Cup Qualifiers",
        "home": "Slovenia (W)",
        "away": "Turkey (W)",
        "date": "2026-10-13T15:00:00+00:00",
    }


def test_authoritative_physical_mapping_accepts_legacy_hash_drift():
    writer = Writer()
    row = _row()
    current_hash = make_match_id_hash(
        row["home"], row["away"], row["league"], row["date"]
    )
    legacy_hash = "1b8b35ae6b78"
    assert current_hash != legacy_hash

    fixture_uid = "0e765d5d-ceb4-40d5-a456-866d09ea50c1"
    physical = (row["league"], row["home"], row["away"], row["date"])
    writer._fixture_identity_event_by_physical = {physical: "36183488"}

    def fake_get(url, **kwargs):
        if url.endswith("/fixture_source_ids"):
            return _response(200, [{
                "source_event_id": "36183488",
                "fixture_uid": fixture_uid,
            }])
        if url.endswith("/fixtures"):
            return _response(200, [{
                "fixture_uid": fixture_uid,
                "match_id_hash": legacy_hash,
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
    assert stats["provider_context_mode"] == "physical"
    assert stats["tagged_rows"] == 1
    assert stats["unresolved_rows"] == 0
    assert stats["identity_mismatch_rows"] == 0
    assert stats["legacy_hash_drift_rows"] == 1
    assert row["fixture_uid"] == fixture_uid


def test_authoritative_physical_mapping_still_rejects_metadata_mismatch():
    writer = Writer()
    row = _row()
    fixture_uid = "0e765d5d-ceb4-40d5-a456-866d09ea50c1"
    physical = (row["league"], row["home"], row["away"], row["date"])
    writer._fixture_identity_event_by_physical = {physical: "36183488"}

    def fake_get(url, **kwargs):
        if url.endswith("/fixture_source_ids"):
            return _response(200, [{
                "source_event_id": "36183488",
                "fixture_uid": fixture_uid,
            }])
        if url.endswith("/fixtures"):
            return _response(200, [{
                "fixture_uid": fixture_uid,
                "match_id_hash": "1b8b35ae6b78",
                "league": "Different League",
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
    assert stats["legacy_hash_drift_rows"] == 0
    assert "fixture_uid" not in row


def test_hash_scoped_compatibility_mode_remains_strict_on_hash_drift():
    writer = Writer()
    writer._fixture_identity_authoritative_active = False
    row = _row()
    current_hash = make_match_id_hash(
        row["home"], row["away"], row["league"], row["date"]
    )
    fixture_uid = "11111111-1111-1111-1111-111111111111"
    writer._fixture_identity_event_by_hash = {current_hash: "evt-legacy"}
    writer._fixture_identity_physical_by_hash = {
        current_hash: (row["league"], row["home"], row["away"], row["date"])
    }

    def fake_get(url, **kwargs):
        if url.endswith("/fixture_source_ids"):
            return _response(200, [{
                "source_event_id": "evt-legacy",
                "fixture_uid": fixture_uid,
            }])
        if url.endswith("/fixtures"):
            return _response(200, [{
                "fixture_uid": fixture_uid,
                "match_id_hash": "1b8b35ae6b78",
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
