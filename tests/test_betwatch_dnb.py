from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_draw_no_bet_maps_real_provider_runners_in_both_clients():
    # Reversed runner order proves team-name matching is used when context exists.
    runners = [
        {"name": "Away FC", "odd": 2.15, "volume": 70},
        {"name": "Home FC", "odd": 1.72, "volume": 130},
    ]
    for idx, path in enumerate([
        ROOT / "betwatch_client.py",
        ROOT / "desktop" / "scraper_standalone" / "betwatch_client.py",
    ]):
        client = _load_module(f"betwatch_dnb_client_{idx}", path)
        market, selections = client.map_market(
            "Draw no Bet", runners, home="Home FC", away="Away FC"
        )
        assert market == "DNB"
        by_code = {code: runner for code, runner in selections}
        assert by_code["1"]["name"] == "Home FC"
        assert by_code["2"]["name"] == "Away FC"


def test_double_chance_is_never_synthesized_from_1x2():
    client = _load_module("betwatch_no_synthetic_dc", ROOT / "betwatch_client.py")
    market, selections = client.map_market(
        "Double Chance",
        [
            {"name": "Home or Draw", "odd": 1.30, "volume": 100},
            {"name": "Home or Away", "odd": 1.40, "volume": 90},
            {"name": "Draw or Away", "odd": 1.60, "volume": 80},
        ],
        home="Home",
        away="Away",
    )
    assert market is None
    assert selections == []


def _load_prematch(monkeypatch):
    standalone = types.ModuleType("standalone_scraper")
    standalone.SupabaseWriter = object
    standalone.get_turkey_now = lambda: "2026-10-04T18:00:00+03:00"
    monkeypatch.setitem(sys.modules, "standalone_scraper", standalone)
    return _load_module("betwatch_prematch_dnb_test", ROOT / "betwatch_prematch.py")


def test_prematch_persists_dnb_current_history_and_snapshots(monkeypatch):
    module = _load_prematch(monkeypatch)
    match = {
        "teams": {"v1": "Home FC", "v2": "Away FC"},
        "league": "Test League",
        "kickoff": "2026-10-04T20:00:00Z",
        "markets": [{
            "name": "Draw no Bet",
            "runners": [
                {"name": "Home FC", "odd": 1.75, "volume": 150},
                {"name": "Away FC", "odd": 2.10, "volume": 50},
            ],
        }],
    }
    monkeypatch.setattr(module, "fetch_prematch", lambda timeout=40: [match])

    empty = Mock()
    empty.status_code = 200
    empty.json.return_value = []
    monkeypatch.setattr(module.requests, "get", Mock(return_value=empty))

    class Writer:
        def __init__(self):
            self.replaced = []
            self.histories = []
            self.snapshots = []

        def _rest_url(self, table):
            return f"https://example.supabase.co/rest/v1/{table}"

        def _headers(self):
            return {}

        def upsert_fixtures(self, rows):
            return True

        def replace_table(self, table, rows):
            self.replaced.append((table, rows))
            return True

        def append_history(self, table, rows, scraped_at):
            self.histories.append((table, rows, scraped_at))
            return True

        def insert_snapshots(self, table, rows):
            self.snapshots.extend(rows)
            return True

    writer = Writer()
    assert module.run_scrape_betwatch(writer) == 1
    assert writer.last_scrape_stats["match_count"] == 1
    assert writer.last_scrape_stats["snapshot_count"] == 2
    assert writer.last_scrape_stats["row_count"] == 1

    assert [table for table, _ in writer.replaced] == ["moneyway_draw_no_bet"]
    assert [table for table, *_ in writer.histories] == ["moneyway_draw_no_bet_history"]
    assert {(row["market"], row["selection"]) for row in writer.snapshots} == {
        ("DNB", "1"), ("DNB", "2")
    }

    dnb_row = writer.replaced[0][1][0]
    assert dnb_row["odds1"] == "1.75"
    assert dnb_row["odds2"] == "2.1"
    assert dnb_row["pct1"] == "75.0%"
    assert dnb_row["pct2"] == "25.0%"
