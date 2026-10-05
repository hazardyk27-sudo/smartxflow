from __future__ import annotations

from unittest.mock import Mock

from core import fixture_uid_dual_write as dual


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


def test_snapshot_rows_fail_closed_without_provider_verifiable_identity():
    writer = Writer()
    snapshots = [
        {"match_id_hash": "abc123", "market": "1X2", "selection": "1"},
        {"match_id_hash": "abc123", "market": "1X2", "selection": "X"},
    ]

    def fake_get(url, **kwargs):
        if url.endswith("/moneyway_snapshots"):
            return _response(200, [])
        raise AssertionError(url)

    stats = dual.attach_fixture_uids_to_snapshots(
        writer, "moneyway_snapshots", snapshots, request_get=fake_get
    )
    assert stats["column_available"] is True
    assert stats["requested_hashes"] == 1
    assert stats["resolved_hashes"] == 0
    assert stats["tagged_rows"] == 0
    assert stats["unresolved_rows"] == 2
    assert stats["error"] == "snapshot_provider_identity_required"
    assert all("fixture_uid" not in row for row in snapshots)


def test_snapshot_missing_schema_column_fails_soft():
    writer = Writer()
    snapshots = [{"match_id_hash": "abc123", "market": "1X2", "selection": "1"}]

    stats = dual.attach_fixture_uids_to_snapshots(
        writer,
        "moneyway_snapshots",
        snapshots,
        request_get=lambda *args, **kwargs: _response(400, {}),
    )
    assert stats["error"] == "fixture_uid_column_unavailable"
    assert stats["tagged_rows"] == 0
    assert "fixture_uid" not in snapshots[0]


def test_snapshot_existing_uid_is_preserved_while_new_resolution_is_disabled():
    writer = Writer()
    snapshots = [{
        "match_id_hash": "abc123",
        "market": "1X2",
        "selection": "1",
        "fixture_uid": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    }]

    def fake_get(url, **kwargs):
        if url.endswith("/moneyway_snapshots"):
            return _response(200, [])
        raise AssertionError(url)

    stats = dual.attach_fixture_uids_to_snapshots(
        writer, "moneyway_snapshots", snapshots, request_get=fake_get
    )
    assert stats["tagged_rows"] == 0
    assert stats["error"] == "snapshot_provider_identity_required"
    assert snapshots[0]["fixture_uid"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def test_non_snapshot_table_is_ignored():
    writer = Writer()
    rows = [{"match_id_hash": "abc123"}]
    stats = dual.attach_fixture_uids_to_snapshots(
        writer,
        "unrelated_table",
        rows,
        request_get=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError()),
    )
    assert stats["attempted"] is False
    assert "fixture_uid" not in rows[0]
