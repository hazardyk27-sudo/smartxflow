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
