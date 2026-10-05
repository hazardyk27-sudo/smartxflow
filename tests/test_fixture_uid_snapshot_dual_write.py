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


def test_snapshot_rows_receive_existing_fixture_uid():
    writer = Writer()
    snapshots = [
        {"match_id_hash": "abc123", "market": "1X2", "selection": "1"},
        {"match_id_hash": "abc123", "market": "1X2", "selection": "X"},
    ]

    def fake_get(url, **kwargs):
        if url.endswith("/moneyway_snapshots"):
            return _response(200, [])
        if url.endswith("/fixtures"):
            return _response(200, [{
                "match_id_hash": "abc123",
                "fixture_uid": "11111111-1111-1111-1111-111111111111",
            }])
        raise AssertionError(url)

    stats = dual.attach_fixture_uids_to_snapshots(
        writer, "moneyway_snapshots", snapshots, request_get=fake_get
    )
    assert stats["column_available"] is True
    assert stats["requested_hashes"] == 1
    assert stats["resolved_hashes"] == 1
    assert stats["tagged_rows"] == 2
    assert stats["unresolved_rows"] == 0
    assert all(
        row["fixture_uid"] == "11111111-1111-1111-1111-111111111111"
        for row in snapshots
    )


def test_snapshot_schema_or_lookup_failure_is_soft():
    writer = Writer()
    snapshots = [{"match_id_hash": "abc123", "market": "1X2", "selection": "1"}]

    stats_missing_column = dual.attach_fixture_uids_to_snapshots(
        writer,
        "moneyway_snapshots",
        snapshots,
        request_get=lambda *args, **kwargs: _response(400, {}),
    )
    assert stats_missing_column["error"] == "fixture_uid_column_unavailable"
    assert "fixture_uid" not in snapshots[0]

    writer2 = Writer()

    def fake_get(url, **kwargs):
        if url.endswith("/moneyway_snapshots"):
            return _response(200, [])
        if url.endswith("/fixtures"):
            return _response(503, [])
        raise AssertionError(url)

    stats_lookup = dual.attach_fixture_uids_to_snapshots(
        writer2, "moneyway_snapshots", snapshots, request_get=fake_get
    )
    assert "HTTP 503" in stats_lookup["error"]
    assert stats_lookup["tagged_rows"] == 0
    assert "fixture_uid" not in snapshots[0]


def test_snapshot_existing_conflicting_uid_is_preserved():
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
        if url.endswith("/fixtures"):
            return _response(200, [{
                "match_id_hash": "abc123",
                "fixture_uid": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            }])
        raise AssertionError(url)

    stats = dual.attach_fixture_uids_to_snapshots(
        writer, "moneyway_snapshots", snapshots, request_get=fake_get
    )
    assert stats["conflicting_existing_uid"] == 1
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
