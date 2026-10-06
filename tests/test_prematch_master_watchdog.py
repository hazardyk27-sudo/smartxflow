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


def _load_scheduled_scraper(monkeypatch):
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

    return _load_module("scheduled_scraper_master_test", ROOT / "scheduled_scraper_legacy.py")


def _heartbeat_response(rows):
    response = Mock()
    response.status_code = 200
    response.json.return_value = rows
    return response


def test_live_and_engine_heartbeats_do_not_block_prematch_master(monkeypatch):
    mod = _load_scheduled_scraper(monkeypatch)
    mod.SCRAPER_SOURCE = "replit-preview"
    now = datetime.now(timezone.utc).isoformat()
    rows = [
        {"source": "replit-live", "status": "active", "last_heartbeat": now},
        {"source": "replit-live-worker", "status": "active", "last_heartbeat": now},
        {"source": "alarm_engine", "status": "active", "last_heartbeat": now},
        {"source": "sinyal_engine", "status": "active", "last_heartbeat": now},
    ]
    monkeypatch.setattr(mod.requests, "get", Mock(return_value=_heartbeat_response(rows)))

    is_master, reason = mod.check_master_status("https://example.supabase.co", "key")

    assert is_master is True
    assert reason == "i_am_master"


def test_active_prematch_peer_blocks_duplicate_master(monkeypatch):
    mod = _load_scheduled_scraper(monkeypatch)
    mod.SCRAPER_SOURCE = "replit-preview"
    rows = [
        {
            "source": "replit",
            "status": "active",
            "last_heartbeat": (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat(),
        }
    ]
    monkeypatch.setattr(mod.requests, "get", Mock(return_value=_heartbeat_response(rows)))

    is_master, reason = mod.check_master_status("https://example.supabase.co", "key")

    assert is_master is False
    assert "prematch master" in reason


def test_active_degraded_prematch_peer_still_holds_master_lease(monkeypatch):
    mod = _load_scheduled_scraper(monkeypatch)
    mod.SCRAPER_SOURCE = "replit-preview"
    rows = [
        {
            "source": "replit",
            "status": "active_degraded",
            "last_heartbeat": (datetime.now(timezone.utc) - timedelta(seconds=45)).isoformat(),
        }
    ]
    monkeypatch.setattr(mod.requests, "get", Mock(return_value=_heartbeat_response(rows)))

    is_master, _ = mod.check_master_status("https://example.supabase.co", "key")

    assert is_master is False


def test_signal_fallback_ignores_non_prematch_sources(monkeypatch):
    mod = _load_scheduled_scraper(monkeypatch)
    mod.SCRAPER_SOURCE = "replit-preview"
    mod._HEARTBEAT_TABLE_AVAILABLE = False
    response = Mock()
    response.status_code = 200
    response.json.return_value = [
        {
            "source": "replit-live",
            "created_at": (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat(),
        },
        {
            "source": "replit",
            "created_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
        },
    ]
    monkeypatch.setattr(mod.requests, "get", Mock(return_value=response))

    is_master, reason = mod.check_master_status("https://example.supabase.co", "key")

    assert is_master is False
    assert reason.startswith("replit recent scrape")


def test_standby_main_is_not_reported_as_successful_scrape(monkeypatch):
    mod = _load_scheduled_scraper(monkeypatch)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "key")
    monkeypatch.setattr(mod, "check_master_status", lambda *args, **kwargs: (False, "replit is prematch master"))
    heartbeat = Mock(return_value=True)
    monkeypatch.setattr(mod, "update_heartbeat", heartbeat)
    signal = Mock(side_effect=AssertionError("standby must not emit scrape_complete"))
    monkeypatch.setattr(mod, "send_alarm_engine_signal", signal)

    assert mod.main() is False
    signal.assert_not_called()
    assert any(call.args[2] == "standby" for call in heartbeat.call_args_list)


def test_last_signal_time_uses_real_prematch_scrape_complete(monkeypatch):
    mod = _load_scheduled_scraper(monkeypatch)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "key")
    live_time = datetime.now(timezone.utc) - timedelta(seconds=5)
    prematch_time = datetime.now(timezone.utc) - timedelta(minutes=2)
    response = Mock()
    response.status_code = 200
    response.json.return_value = [
        {"source": "replit-live", "created_at": live_time.isoformat()},
        {"source": "replit", "created_at": prematch_time.isoformat()},
    ]
    monkeypatch.setattr(mod.requests, "get", Mock(return_value=response))

    result = mod.get_last_signal_time()

    assert result is not None
    assert abs((result - prematch_time).total_seconds()) < 0.01


def test_successful_scrape_requires_alarm_engine_signal(monkeypatch):
    mod = _load_scheduled_scraper(monkeypatch)

    class FakeWriter:
        def __init__(self, *args, **kwargs):
            self.last_write_errors = []
            self.last_scrape_stats = {"match_count": 12, "snapshot_count": 30}

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "key")
    monkeypatch.setattr(mod, "SupabaseWriter", FakeWriter)
    monkeypatch.setattr(mod, "check_master_status", lambda *args, **kwargs: (True, "test"))
    monkeypatch.setattr(mod, "run_scrape", lambda *args, **kwargs: 42)
    monkeypatch.setattr(mod, "update_heartbeat", Mock(return_value=True))
    monkeypatch.setattr(mod, "send_telegram", Mock(return_value=True))
    monkeypatch.setattr(mod, "send_alarm_engine_signal", Mock(return_value=False))

    assert mod.main() is False


def test_prematch_cadence_defaults_to_five_minutes(monkeypatch):
    mod = _load_scheduled_scraper(monkeypatch)

    assert mod.PREMATCH_INTERVAL_MINUTES == 5
    assert mod.PREMATCH_INTERVAL_SECONDS == 300
    assert mod.PREMATCH_WATCHDOG_MINUTES == 12
    assert mod.PREMATCH_WATCHDOG_SECONDS == 720
    assert mod.PREMATCH_FAILURE_RETRY_SECONDS == 60
    assert mod.PREMATCH_MASTER_LEASE_MINUTES == 7
    assert mod.PREMATCH_MASTER_LEASE_MINUTES > mod.PREMATCH_INTERVAL_MINUTES
    assert mod.PREMATCH_WATCHDOG_SECONDS > mod.PREMATCH_INTERVAL_SECONDS * 2


def test_next_scrape_delay_is_anchored_to_last_real_signal(monkeypatch):
    mod = _load_scheduled_scraper(monkeypatch)
    now = datetime.now(timezone.utc)

    assert mod._seconds_until_next_scrape(now - timedelta(minutes=2), now) == 180
    assert mod._seconds_until_next_scrape(now - timedelta(minutes=5), now) == 0
    assert mod._seconds_until_next_scrape(now - timedelta(minutes=20), now) == 0
    assert mod._seconds_until_next_scrape(None, now) == 0


def test_seven_minute_lease_covers_five_minute_sleep_without_false_failover(monkeypatch):
    mod = _load_scheduled_scraper(monkeypatch)
    mod.SCRAPER_SOURCE = "replit-preview"
    rows = [
        {
            "source": "replit",
            "status": "active",
            "last_heartbeat": (datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat(),
        }
    ]
    monkeypatch.setattr(mod.requests, "get", Mock(return_value=_heartbeat_response(rows)))

    is_master, _ = mod.check_master_status("https://example.supabase.co", "key")

    assert is_master is False


def test_expired_seven_minute_lease_allows_failover(monkeypatch):
    mod = _load_scheduled_scraper(monkeypatch)
    mod.SCRAPER_SOURCE = "replit-preview"
    rows = [
        {
            "source": "replit",
            "status": "active",
            "last_heartbeat": (datetime.now(timezone.utc) - timedelta(minutes=8)).isoformat(),
        }
    ]
    monkeypatch.setattr(mod.requests, "get", Mock(return_value=_heartbeat_response(rows)))

    is_master, reason = mod.check_master_status("https://example.supabase.co", "key")

    assert is_master is True
    assert reason == "i_am_master"
