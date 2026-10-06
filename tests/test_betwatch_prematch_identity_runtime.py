import importlib.util
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FakeWriter:
    def __init__(self):
        self.upsert_fixture_calls = []
        self.history_calls = []
        self.snapshot_calls = []
        self.last_write_errors = []
        self.last_scrape_stats = {}

    def upsert_fixtures(self, rows):
        self.upsert_fixture_calls.append(list(rows))
        return True

    def append_history(self, table, rows, scraped_at):
        self.history_calls.append((table, list(rows), scraped_at))
        return True

    def insert_snapshots(self, table, rows):
        self.snapshot_calls.append((table, list(rows)))
        return True


def _load_module():
    standalone = types.ModuleType("standalone_scraper")
    standalone.SupabaseWriter = FakeWriter
    standalone.get_turkey_now = lambda: "2026-10-06 12:00:00"
    sys.modules["standalone_scraper"] = standalone

    betwatch_client = types.ModuleType("betwatch_client")
    betwatch_client.fetch_prematch = lambda timeout=40: []
    betwatch_client.normalize_kickoff = lambda value: str(value or "")

    def map_market(name, runners):
        if name != "1X2":
            return None, []
        return "1X2", [(str(row["selection"]), row) for row in runners]

    betwatch_client.map_market = map_market
    sys.modules["betwatch_client"] = betwatch_client

    spec = importlib.util.spec_from_file_location(
        "betwatch_prematch_identity_runtime_under_test",
        ROOT / "betwatch_prematch.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _match(event_id, kickoff, with_market=False):
    markets = []
    if with_market:
        markets = [
            {
                "name": "1X2",
                "runners": [
                    {"selection": "1", "odd": 2.0, "volume": 100},
                    {"selection": "X", "odd": 3.0, "volume": 50},
                    {"selection": "2", "odd": 4.0, "volume": 25},
                ],
            }
        ]
    return {
        "match_id": event_id,
        "teams": {"v1": "Same Home", "v2": "Same Away"},
        "league": "Same League",
        "kickoff": kickoff,
        "markets": markets,
    }


def _patch_common(module, monkeypatch, matches):
    monkeypatch.setattr(module, "fetch_prematch", lambda timeout=40: matches)
    monkeypatch.setattr(module, "_read_prev_dropping", lambda *args, **kwargs: {})
    monkeypatch.setattr(module, "sync_current_table", lambda *args, **kwargs: True)


def test_uid_first_preserves_two_physical_rematches_with_same_legacy_hash(monkeypatch):
    module = _load_module()
    matches = [
        _match(1001, "2026-10-06T12:00:00+00:00"),
        _match(1002, "2026-11-06T12:00:00+00:00"),
    ]
    _patch_common(module, monkeypatch, matches)
    monkeypatch.setenv("SMARTXFLOW_FIXTURE_UID_AUTHORITATIVE_WRITE", "true")
    monkeypatch.setattr(
        module,
        "write_provider_authoritative_fixture_batch",
        lambda *args, **kwargs: {
            "error": None,
            "received_count": 2,
            "mapped_updated_count": 0,
            "linked_existing_count": 0,
            "inserted_new_count": 2,
        },
    )

    writer = FakeWriter()
    module.run_scrape_betwatch(writer)

    assert writer.upsert_fixture_calls == []
    assert writer.last_scrape_stats["fixture_identity_mode"] == "uid_authoritative"
    assert writer.last_scrape_stats["match_count"] == 2
    assert writer.last_scrape_stats["legacy_hash_collision_groups"] == 1
    assert writer.last_scrape_stats["write_errors"] == 0


def test_legacy_mode_fails_closed_instead_of_overwriting_rematch(monkeypatch):
    module = _load_module()
    matches = [
        _match(1001, "2026-10-06T12:00:00+00:00"),
        _match(1002, "2026-11-06T12:00:00+00:00"),
    ]
    _patch_common(module, monkeypatch, matches)
    monkeypatch.delenv("SMARTXFLOW_FIXTURE_UID_AUTHORITATIVE_WRITE", raising=False)

    writer = FakeWriter()
    result = module.run_scrape_betwatch(writer)

    assert result == 0
    assert writer.upsert_fixture_calls == []
    assert writer.last_scrape_stats["fixture_identity_mode"] == "legacy_hash"
    assert writer.last_scrape_stats["write_errors"] == 1
    assert writer.last_write_errors == ["legacy_hash_collision_groups:1"]


def test_same_day_distinct_kickoffs_are_not_deduped(monkeypatch):
    module = _load_module()
    matches = [
        _match(1001, "2026-10-06T12:00:00+00:00", with_market=True),
        _match(1002, "2026-10-06T20:00:00+00:00", with_market=True),
    ]
    monkeypatch.setenv("SMARTXFLOW_FIXTURE_UID_AUTHORITATIVE_WRITE", "true")
    monkeypatch.setattr(module, "fetch_prematch", lambda timeout=40: matches)
    monkeypatch.setattr(module, "_read_prev_dropping", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        module,
        "write_provider_authoritative_fixture_batch",
        lambda *args, **kwargs: {
            "error": None,
            "received_count": 2,
            "mapped_updated_count": 0,
            "linked_existing_count": 0,
            "inserted_new_count": 2,
        },
    )
    monkeypatch.setattr(
        module,
        "attach_provider_fixture_uids_to_snapshots",
        lambda writer, snapshots, request_get=None: {
            "error": None,
            "rows": len(snapshots),
            "provider_events": 2,
            "resolved_events": 2,
            "tagged_rows": len(snapshots),
            "unresolved_rows": 0,
        },
    )

    seen = {}

    def fake_sync(writer, table, rows, logger=None):
        seen[table] = list(rows)
        return True

    monkeypatch.setattr(module, "sync_current_table", fake_sync)

    writer = FakeWriter()
    module.run_scrape_betwatch(writer)

    assert len(seen["moneyway_1x2"]) == 2
    assert len(seen["dropping_1x2"]) == 2
    assert {row["date"] for row in seen["moneyway_1x2"]} == {
        "2026-10-06T12:00:00+00:00",
        "2026-10-06T20:00:00+00:00",
    }
