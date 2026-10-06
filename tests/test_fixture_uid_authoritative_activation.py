from __future__ import annotations

import sys
from types import SimpleNamespace

import core.fixture_uid_authoritative_activation as activation
from core.fixture_identity_payload_stage import (
    clear_betwatch_authoritative_payload,
    stage_betwatch_authoritative_payload,
)
from core.fixture_identity_shadow import (
    consume_betwatch_identity_stage,
    stage_betwatch_identity_payload,
)
from core.fixture_uid_provider_gate import attach_provider_verified_fixture_uids
from core.hash_utils import make_match_id_hash


FLAG = "SMARTXFLOW_FIXTURE_UID_AUTHORITATIVE_WRITER"


def _match(event_id: str, kickoff: str):
    return {
        "match_id": event_id,
        "league": "Test League",
        "kickoff": kickoff,
        "teams": {"v1": "Home FC", "v2": "Away FC"},
        "markets": [],
    }


def _install_fake_writer(monkeypatch):
    class FakeWriter:
        def __init__(self):
            self.original_fixture_calls = 0
            self.original_history_calls = 0
            self.last_write_errors = []

        def _rest_url(self, table):
            return f"https://example.supabase.co/rest/v1/{table}"

        def _headers(self):
            return {"apikey": "anon", "Authorization": "Bearer anon"}

        def upsert_fixtures(self, rows):
            self.original_fixture_calls += 1
            return True

        def upsert_rows(self, *args, **kwargs):
            return True

        def replace_table(self, *args, **kwargs):
            return True

        def append_history(self, *args, **kwargs):
            self.original_history_calls += 1
            return True

        def insert_snapshots(self, *args, **kwargs):
            return True

    monkeypatch.setitem(sys.modules, "standalone_scraper", SimpleNamespace(SupabaseWriter=FakeWriter))
    activation._PATCHED = False
    assert activation.install_provider_authoritative_fixture_writer_patch() is True
    return FakeWriter


def test_flag_off_is_exact_legacy_delegate(monkeypatch):
    monkeypatch.delenv(FLAG, raising=False)
    FakeWriter = _install_fake_writer(monkeypatch)
    writer = FakeWriter()

    assert writer.upsert_fixtures([{"match_id_hash": "abc"}]) is True
    assert writer.original_fixture_calls == 1
    assert writer.append_history("history", [], "now") is True
    assert writer.original_history_calls == 1


def test_authoritative_missing_payload_blocks_all_later_writes(monkeypatch):
    monkeypatch.setenv(FLAG, "true")
    clear_betwatch_authoritative_payload()
    FakeWriter = _install_fake_writer(monkeypatch)
    writer = FakeWriter()

    assert writer.upsert_fixtures([{"match_id_hash": "legacy"}]) is False
    assert writer.original_fixture_calls == 0
    assert writer.append_history("history", [{"x": 1}], "now") is False
    assert writer.original_history_calls == 0
    assert writer.upsert_rows("moneyway_1x2", [{"x": 1}]) is False
    assert writer.insert_snapshots("moneyway_snapshots", [{"x": 1}]) is False
    assert writer.last_fixture_uid_authoritative_stats["error"] == "provider_identity_payload_unavailable"


def test_authoritative_success_uses_service_role_and_clears_shadow(monkeypatch):
    monkeypatch.setenv(FLAG, "1")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-secret")
    matches = [_match("evt-1", "2026-10-06T18:00:00Z")]
    stage_betwatch_authoritative_payload(matches)
    stage_betwatch_identity_payload(matches)

    observed = {}

    def fake_authoritative_write(rpc_writer, received_matches):
        observed["auth"] = rpc_writer._headers()["Authorization"]
        observed["matches"] = received_matches
        return {
            "error": None,
            "received_count": 1,
            "mapped_updated_count": 1,
            "linked_existing_count": 0,
            "inserted_new_count": 0,
        }

    monkeypatch.setattr(
        activation,
        "write_provider_authoritative_fixture_batch",
        fake_authoritative_write,
    )
    FakeWriter = _install_fake_writer(monkeypatch)
    writer = FakeWriter()

    assert writer.upsert_fixtures([{"match_id_hash": "legacy"}]) is True
    assert writer.original_fixture_calls == 0
    assert observed["auth"] == "Bearer service-secret"
    assert observed["matches"] == matches
    assert writer._fixture_identity_authoritative_failed is False
    assert len(writer._fixture_identity_event_by_physical) == 1
    assert consume_betwatch_identity_stage() is None
    assert writer.append_history("history", [], "now") is True
    assert writer.original_history_calls == 1


def test_physical_context_supports_two_rematches_with_same_legacy_hash():
    first = _match("evt-old", "2026-10-06T18:00:00Z")
    second = _match("evt-new", "2026-11-06T18:00:00Z")
    context, error = activation.build_physical_event_context([first, second])

    assert error is None
    assert len(context) == 2
    assert set(context.values()) == {"evt-old", "evt-new"}
    assert make_match_id_hash("Home FC", "Away FC", "Test League") == make_match_id_hash(
        "Home FC", "Away FC", "Test League", "2026-11-06T18:00:00Z"
    )


def test_provider_gate_tags_same_hash_rematches_to_distinct_uids():
    class Writer:
        def _rest_url(self, table):
            return f"https://example.supabase.co/rest/v1/{table}"

        def _headers(self):
            return {"apikey": "anon"}

    writer = Writer()
    row_old = {
        "league": "Test League",
        "home": "Home FC",
        "away": "Away FC",
        "date": "2026-10-06T18:00:00+00:00",
    }
    row_new = {
        "league": "Test League",
        "home": "Home FC",
        "away": "Away FC",
        "date": "2026-11-06T18:00:00+00:00",
    }
    match_hash = make_match_id_hash("Home FC", "Away FC", "Test League")
    uid_old = "11111111-1111-1111-1111-111111111111"
    uid_new = "22222222-2222-2222-2222-222222222222"
    writer._fixture_identity_event_by_physical = {
        (row_old["league"], row_old["home"], row_old["away"], row_old["date"]): "evt-old",
        (row_new["league"], row_new["home"], row_new["away"], row_new["date"]): "evt-new",
    }

    class Response:
        def __init__(self, payload):
            self.status_code = 200
            self._payload = payload

        def json(self):
            return self._payload

    def fake_get(url, **kwargs):
        if url.endswith("/fixture_source_ids"):
            return Response([
                {"source_event_id": "evt-old", "fixture_uid": uid_old},
                {"source_event_id": "evt-new", "fixture_uid": uid_new},
            ])
        if url.endswith("/fixtures"):
            return Response([
                {
                    "fixture_uid": uid_old,
                    "match_id_hash": match_hash,
                    "league": row_old["league"],
                    "home_team": row_old["home"],
                    "away_team": row_old["away"],
                    "kickoff_utc": row_old["date"],
                },
                {
                    "fixture_uid": uid_new,
                    "match_id_hash": match_hash,
                    "league": row_new["league"],
                    "home_team": row_new["home"],
                    "away_team": row_new["away"],
                    "kickoff_utc": row_new["date"],
                },
            ])
        raise AssertionError(url)

    stats = attach_provider_verified_fixture_uids(
        writer,
        [row_old, row_new],
        request_get=fake_get,
    )

    assert stats["provider_context_mode"] == "physical"
    assert stats["tagged_rows"] == 2
    assert stats["unresolved_rows"] == 0
    assert row_old["fixture_uid"] == uid_old
    assert row_new["fixture_uid"] == uid_new
