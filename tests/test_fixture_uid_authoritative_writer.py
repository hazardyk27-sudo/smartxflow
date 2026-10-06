from pathlib import Path

from core.fixture_uid_authoritative_writer import (
    build_betwatch_fixture_rpc_rows,
    write_provider_authoritative_fixture_batch,
)


def _match(event_id, kickoff, home="Alpha FC", away="Beta FC", league="League One"):
    return {
        "match_id": event_id,
        "kickoff": kickoff,
        "league": league,
        "teams": {"v1": home, "v2": away},
    }


def test_same_legacy_hash_different_events_and_kickoffs_are_allowed():
    rows, stats = build_betwatch_fixture_rpc_rows([
        _match("evt-1", "2026-10-06T18:00:00Z"),
        _match("evt-2", "2027-02-10T18:00:00Z"),
    ])
    assert stats["error"] is None
    assert len(rows) == 2
    assert rows[0]["match_id_hash"] == rows[1]["match_id_hash"]
    assert rows[0]["source_event_id"] != rows[1]["source_event_id"]


def test_same_provider_event_cannot_describe_two_physical_matches():
    rows, stats = build_betwatch_fixture_rpc_rows([
        _match("evt-1", "2026-10-06T18:00:00Z"),
        _match("evt-1", "2026-10-07T18:00:00Z"),
    ])
    assert rows == []
    assert stats["error"] == "provider_event_collision"
    assert stats["provider_event_collision_groups"] == 1


def test_same_physical_match_cannot_have_two_provider_events():
    rows, stats = build_betwatch_fixture_rpc_rows([
        _match("evt-1", "2026-10-06T18:00:00Z"),
        _match("evt-2", "2026-10-06T18:00:00Z"),
    ])
    assert rows == []
    assert stats["error"] == "physical_event_collision"
    assert stats["physical_event_collision_groups"] == 1


def test_missing_provider_id_fails_closed_without_rpc():
    calls = []

    class Writer:
        def _rest_url(self, table):
            return "https://example.invalid/" + table

        def _headers(self):
            return {}

    stats = write_provider_authoritative_fixture_batch(
        Writer(),
        [_match(None, "2026-10-06T18:00:00Z")],
        request_post=lambda *a, **k: calls.append((a, k)),
    )
    assert stats["error"] == "missing_provider_id"
    assert calls == []


def test_writer_calls_single_transactional_rpc_and_requires_complete_count():
    calls = []

    class Response:
        status_code = 200

        def json(self):
            return [{
                "received_count": 2,
                "mapped_updated_count": 1,
                "linked_existing_count": 1,
                "inserted_new_count": 0,
            }]

    class Writer:
        def _rest_url(self, table):
            assert table == "rpc/record_betwatch_fixture_batch_v2"
            return "https://example.invalid/rest/v1/" + table

        def _headers(self):
            return {"Authorization": "secret"}

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))
        return Response()

    stats = write_provider_authoritative_fixture_batch(
        Writer(),
        [
            _match("evt-1", "2026-10-06T18:00:00Z"),
            _match("evt-2", "2027-02-10T18:00:00Z"),
        ],
        observed_at="2026-10-06T00:00:00+00:00",
        request_post=fake_post,
    )
    assert stats["error"] is None
    assert stats["received_count"] == 2
    assert len(calls) == 1
    assert len(calls[0][1]["json"]["p_rows"]) == 2


def test_rpc_error_never_falls_back_to_legacy_hash_writer():
    class Response:
        status_code = 409

        def json(self):
            return {"message": "conflict"}

    class Writer:
        def _rest_url(self, table):
            return "https://example.invalid/rest/v1/" + table

        def _headers(self):
            return {}

    stats = write_provider_authoritative_fixture_batch(
        Writer(),
        [_match("evt-1", "2026-10-06T18:00:00Z")],
        request_post=lambda *a, **k: Response(),
    )
    assert stats["error"] == "provider_fixture_rpc_http_409"
    assert stats["received_count"] == 0


def test_provider_writer_migration_retires_hash_uniqueness_but_keeps_hash_index():
    sql = Path("migrations/2026_10_06_fixture_identity_v2_provider_writer.sql").read_text()
    assert "drop constraint if exists fixtures_match_id_hash_key" in sql
    assert "create index if not exists fixtures_match_id_hash_idx" in sql
    assert "fixture_source_ids_betwatch_fixture_uid_uidx" in sql
    assert "record_betwatch_fixture_batch_v2" in sql
    assert "fixture_uid set not null" in sql
