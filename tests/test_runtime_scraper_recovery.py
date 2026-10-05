from __future__ import annotations

import importlib.util
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_map_market_accepts_legacy_keyword_arguments_in_both_clients():
    runners = [
        {"name": "Home", "odd": 2.1},
        {"name": "Draw", "odd": 3.2},
        {"name": "Away", "odd": 3.4},
    ]
    for idx, path in enumerate(
        [
            ROOT / "betwatch_client.py",
            ROOT / "desktop" / "scraper_standalone" / "betwatch_client.py",
        ]
    ):
        mod = _load_module(f"betwatch_client_test_{idx}", path)
        market, sels = mod.map_market(
            "Match Odds",
            runners,
            home="Home",
            away="Away",
            league="League",
            obsolete_flag=True,
        )
        assert market == "1X2"
        assert [selection for selection, _ in sels] == ["1", "X", "2"]


def _load_scheduled_scraper_with_stubs(monkeypatch):
    standalone = types.ModuleType("standalone_scraper")
    standalone.SupabaseWriter = object
    standalone.cleanup_old_matches = lambda *args, **kwargs: 0
    monkeypatch.setitem(sys.modules, "standalone_scraper", standalone)

    prematch = types.ModuleType("betwatch_prematch")
    prematch.run_scrape_betwatch = lambda *args, **kwargs: 1
    monkeypatch.setitem(sys.modules, "betwatch_prematch", prematch)

    core_pkg = types.ModuleType("core")
    core_pkg.__path__ = []
    retention = types.ModuleType("core.retention_guard")
    retention.retention_cleanup_disabled = lambda: True
    monkeypatch.setitem(sys.modules, "core", core_pkg)
    monkeypatch.setitem(sys.modules, "core.retention_guard", retention)

    return _load_module("scheduled_scraper_runtime_test", ROOT / "scheduled_scraper.py")


def test_replit_runtime_uses_distinct_scraper_source(monkeypatch):
    monkeypatch.setenv("REPL_ID", "preview-runtime")
    mod = _load_scheduled_scraper_with_stubs(monkeypatch)
    assert mod.SCRAPER_SOURCE == "replit-preview"


def test_missing_heartbeat_table_switches_to_signal_fallback(monkeypatch):
    mod = _load_scheduled_scraper_with_stubs(monkeypatch)

    class MissingResponse:
        status_code = 404
        text = '{"code":"PGRST205","message":"Could not find the table public.scraper_heartbeat"}'

    assert mod._heartbeat_table_missing(MissingResponse()) is True

    mod._HEARTBEAT_TABLE_AVAILABLE = False
    post = Mock(side_effect=AssertionError("heartbeat POST must stay disabled after PGRST205"))
    monkeypatch.setattr(mod.requests, "post", post)
    assert mod.update_heartbeat("https://example.supabase.co", "key", "active", 10) is False
    post.assert_not_called()


def test_master_fallback_uses_recent_external_scrape_signal(monkeypatch):
    mod = _load_scheduled_scraper_with_stubs(monkeypatch)
    mod._HEARTBEAT_TABLE_AVAILABLE = False
    created_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()

    response = Mock()
    response.status_code = 200
    response.json.return_value = [{"source": "hetzner", "created_at": created_at}]
    monkeypatch.setattr(mod.requests, "get", Mock(return_value=response))

    is_master, reason = mod.check_master_status("https://example.supabase.co", "key")
    assert is_master is False
    assert "recent scrape" in reason


def test_master_fallback_keeps_preview_standby_within_seven_minute_lease(monkeypatch):
    mod = _load_scheduled_scraper_with_stubs(monkeypatch)
    mod.SCRAPER_SOURCE = "replit-preview"
    mod._HEARTBEAT_TABLE_AVAILABLE = False
    created_at = (datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat()

    response = Mock()
    response.status_code = 200
    response.json.return_value = [{"source": "replit", "created_at": created_at}]
    monkeypatch.setattr(mod.requests, "get", Mock(return_value=response))

    is_master, reason = mod.check_master_status("https://example.supabase.co", "key")
    assert is_master is False
    assert "recent scrape" in reason


def test_send_signal_skips_recent_duplicate(monkeypatch):
    mod = _load_scheduled_scraper_with_stubs(monkeypatch)
    monkeypatch.setattr(mod, "fcntl", None)
    mod.SCRAPER_SOURCE = "replit-preview"

    response = Mock()
    response.status_code = 200
    response.json.return_value = [
        {
            "id": 101,
            "source": "replit",
            "created_at": (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat(),
            "match_count": 3186,
            "snapshot_count": 3186,
        }
    ]
    monkeypatch.setattr(mod.requests, "get", Mock(return_value=response))
    post = Mock(side_effect=AssertionError("recent duplicate must not be inserted"))
    monkeypatch.setattr(mod.requests, "post", post)

    assert mod.send_alarm_engine_signal(
        "https://example.supabase.co",
        "key",
        614,
        1327,
    ) is True
    post.assert_not_called()


def test_send_signal_allows_stale_previous_signal(monkeypatch):
    mod = _load_scheduled_scraper_with_stubs(monkeypatch)
    monkeypatch.setattr(mod, "fcntl", None)

    previous = Mock()
    previous.status_code = 200
    previous.json.return_value = [
        {
            "id": 100,
            "created_at": (datetime.now(timezone.utc) - timedelta(minutes=9)).isoformat(),
            "match_count": 614,
            "snapshot_count": 1327,
        }
    ]
    posted = Mock()
    posted.status_code = 201
    posted.text = '[{"id":102}]'
    monkeypatch.setattr(mod.requests, "get", Mock(return_value=previous))
    post = Mock(return_value=posted)
    monkeypatch.setattr(mod.requests, "post", post)

    assert mod.send_alarm_engine_signal(
        "https://example.supabase.co",
        "key",
        614,
        1327,
    ) is True
    assert post.call_count == 1
    assert post.call_args.kwargs["json"]["match_count"] == 614
    assert post.call_args.kwargs["json"]["snapshot_count"] == 1327


def test_scheduled_scraper_uses_exact_scrape_counts(monkeypatch):
    mod = _load_scheduled_scraper_with_stubs(monkeypatch)

    class FakeWriter:
        def __init__(self, *args, **kwargs):
            self.last_write_errors = []
            self.last_scrape_stats = {}

    def fake_run(writer, logger_callback=None):
        writer.last_scrape_stats = {
            "match_count": 614,
            "snapshot_count": 1327,
            "row_count": 3186,
        }
        return 3186

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "key")
    monkeypatch.setattr(mod, "SupabaseWriter", FakeWriter)
    monkeypatch.setattr(mod, "run_scrape", fake_run)
    monkeypatch.setattr(mod, "check_master_status", lambda *args, **kwargs: (True, "test"))
    heartbeat = Mock(return_value=True)
    signal = Mock(return_value=True)
    monkeypatch.setattr(mod, "update_heartbeat", heartbeat)
    monkeypatch.setattr(mod, "send_alarm_engine_signal", signal)
    monkeypatch.setattr(mod, "send_telegram", Mock(return_value=True))

    assert mod.main() is True
    signal.assert_called_once_with(
        "https://example.supabase.co",
        "key",
        614,
        1327,
    )
    assert any(
        call.args[:4] == ("https://example.supabase.co", "key", "active", 614)
        for call in heartbeat.call_args_list
    )


def _load_prematch_with_stubs(monkeypatch):
    standalone = types.ModuleType("standalone_scraper")
    standalone.SupabaseWriter = object
    standalone.get_turkey_now = lambda: "2026-10-04T00:00:00+03:00"
    monkeypatch.setitem(sys.modules, "standalone_scraper", standalone)

    client = types.ModuleType("betwatch_client")
    client.fetch_prematch = lambda timeout=40: []
    client.normalize_kickoff = lambda value: value.replace("Z", "+00:00")

    def map_market(name, runners):
        if name != "Match Odds":
            return None, []
        return "1X2", [("1", runners[0]), ("X", runners[1]), ("2", runners[2])]

    client.map_market = map_market
    monkeypatch.setitem(sys.modules, "betwatch_client", client)
    return _load_module("betwatch_prematch_runtime_test", ROOT / "betwatch_prematch.py")


def test_prematch_exposes_fixture_and_snapshot_counts(monkeypatch):
    mod = _load_prematch_with_stubs(monkeypatch)

    match = {
        "teams": {"v1": "Home", "v2": "Away"},
        "league": "League",
        "kickoff": "2026-10-04T18:00:00Z",
        "markets": [
            {
                "name": "Match Odds",
                "runners": [
                    {"name": "Home", "odd": 2.0, "volume": 100},
                    {"name": "Draw", "odd": 3.0, "volume": 50},
                    {"name": "Away", "odd": 4.0, "volume": 25},
                ],
            }
        ],
    }
    monkeypatch.setattr(mod, "fetch_prematch", lambda timeout=40: [match])
    prev_response = Mock()
    prev_response.status_code = 200
    prev_response.json.return_value = []
    monkeypatch.setattr(mod.requests, "get", Mock(return_value=prev_response))

    class Writer:
        def _rest_url(self, table):
            return f"https://example.supabase.co/rest/v1/{table}"

        def _headers(self):
            return {}

        def upsert_fixtures(self, rows):
            return True

        def replace_table(self, table, rows):
            return True

        def append_history(self, table, rows, scraped_at):
            return True

        def insert_snapshots(self, table, rows):
            return True

    writer = Writer()
    assert mod.run_scrape_betwatch(writer) == 2
    assert writer.last_scrape_stats["match_count"] == 1
    assert writer.last_scrape_stats["snapshot_count"] == 3
    assert writer.last_scrape_stats["row_count"] == 2


def _load_live_scraper(monkeypatch):
    monkeypatch.delenv("SMARTXFLOW_LIVE_INSTANCE_ID", raising=False)
    return _load_module("live_scraper_runtime_test", ROOT / "live_scraper.py")


def test_live_scraper_missing_heartbeat_switches_to_signal_lease(monkeypatch):
    mod = _load_live_scraper(monkeypatch)
    mod._HEARTBEAT_TABLE_AVAILABLE = None
    mod._LIVE_SIGNAL_SOURCE = "replit-live-aaaaaaaa"
    mod._LIVE_INSTANCE_ID = "aaaaaaaa"
    monkeypatch.setattr(mod.time, "sleep", lambda *_: None)

    missing = Mock()
    missing.status_code = 404
    missing.text = '{"code":"PGRST205","message":"Could not find the table public.scraper_heartbeat"}'

    signals = Mock()
    signals.status_code = 200
    signals.json.return_value = [
        {
            "source": mod._LIVE_SIGNAL_SOURCE,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    ]

    lease_posted = Mock()
    lease_posted.status_code = 201
    lease_posted.text = ""

    get = Mock(side_effect=[missing, signals])
    post = Mock(return_value=lease_posted)
    monkeypatch.setattr(mod.requests, "get", get)
    monkeypatch.setattr(mod.requests, "post", post)

    is_master, reason = mod.check_live_master_status("https://example.supabase.co", "key")
    assert is_master is True
    assert reason.startswith("signal_fallback_master")
    assert mod._HEARTBEAT_TABLE_AVAILABLE is False
    assert post.call_count == 1
    assert post.call_args.kwargs["json"]["signal_type"] == "live_heartbeat"
    assert post.call_args.kwargs["json"]["processed"] is True

    before = post.call_count
    assert mod.update_heartbeat("https://example.supabase.co", "key", "active", 3) is False
    assert post.call_count == before


def test_live_scraper_signal_lease_selects_single_master(monkeypatch):
    mod = _load_live_scraper(monkeypatch)
    mod._HEARTBEAT_TABLE_AVAILABLE = False
    mod._LIVE_SIGNAL_SOURCE = "replit-live-ffffffff"
    mod._LIVE_INSTANCE_ID = "ffffffff"
    monkeypatch.setattr(mod.time, "sleep", lambda *_: None)

    posted = Mock()
    posted.status_code = 201
    posted.text = ""
    monkeypatch.setattr(mod.requests, "post", Mock(return_value=posted))

    now = datetime.now(timezone.utc).isoformat()
    response = Mock()
    response.status_code = 200
    response.json.return_value = [
        {"source": "replit-live-00000000", "created_at": now},
        {"source": mod._LIVE_SIGNAL_SOURCE, "created_at": now},
    ]
    monkeypatch.setattr(mod.requests, "get", Mock(return_value=response))

    is_master, reason = mod.check_live_master_status("https://example.supabase.co", "key")
    assert is_master is False
    assert "replit-live-00000000" in reason


def _load_alarm_engine_with_stubs(monkeypatch):
    calculator_module = types.ModuleType("alarm_calculator")

    class AlarmCalculator:
        pass

    calculator_module.AlarmCalculator = AlarmCalculator
    monkeypatch.setitem(sys.modules, "alarm_calculator", calculator_module)

    recent_module = types.ModuleType("alarm_recent")
    recent_module.install_recent_alarm_overrides = lambda cls: None
    recent_module.clear_recent_alarm_cache = lambda calc: None
    monkeypatch.setitem(sys.modules, "alarm_recent", recent_module)

    return _load_module("alarm_engine_runtime_test", ROOT / "alarm_engine.py")


def test_alarm_engine_disables_repeated_missing_heartbeat_posts(monkeypatch):
    mod = _load_alarm_engine_with_stubs(monkeypatch)

    response = Mock()
    response.status_code = 404
    response.text = '{"code":"PGRST205","message":"scraper_heartbeat missing"}'
    post = Mock(return_value=response)
    monkeypatch.setattr(mod.requests, "post", post)

    mod.SUPABASE_URL = "https://example.supabase.co"
    mod._HEARTBEAT_TABLE_AVAILABLE = None
    assert mod.update_engine_heartbeat("started") is False
    assert mod._HEARTBEAT_TABLE_AVAILABLE is False
    assert post.call_count == 1

    assert mod.update_engine_heartbeat("idle") is False
    assert post.call_count == 1


def test_alarm_engine_only_consumes_scrape_complete_signals(monkeypatch):
    mod = _load_alarm_engine_with_stubs(monkeypatch)
    response = Mock()
    response.status_code = 200
    response.json.return_value = []
    get = Mock(return_value=response)
    monkeypatch.setattr(mod.requests, "get", get)
    mod.SUPABASE_URL = "https://example.supabase.co"

    assert mod.check_unprocessed_signals() is None
    requested_url = get.call_args.args[0]
    assert "signal_type=eq.scrape_complete" in requested_url
