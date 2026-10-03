from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import Mock

import sinyal_engine_runtime as runtime


def test_signal_trigger_only_reads_scrape_complete(monkeypatch):
    runtime.engine.SUPABASE_URL = "https://example.supabase.co"
    runtime.engine.SUPABASE_ANON_KEY = "anon"

    response = Mock()
    response.status_code = 200
    response.json.return_value = [{"created_at": "2026-10-04T00:00:00+00:00"}]
    get = Mock(return_value=response)
    monkeypatch.setattr(runtime.requests, "get", get)

    result = runtime.check_new_scraper_signal("2026-10-03T23:50:00+00:00")

    assert result == "2026-10-04T00:00:00+00:00"
    requested_url = get.call_args.args[0]
    assert "signal_type=eq.scrape_complete" in requested_url
    assert "order=created_at.desc" in requested_url
    assert "live_heartbeat" not in requested_url


def test_missing_heartbeat_disables_repeated_posts(monkeypatch):
    runtime.engine.SUPABASE_URL = "https://example.supabase.co"
    runtime.engine.SUPABASE_ANON_KEY = "anon"
    runtime.engine.SUPABASE_SERVICE_KEY = ""
    runtime._HEARTBEAT_TABLE_AVAILABLE = None
    runtime._HEARTBEAT_MISSING_LOGGED = False

    response = Mock()
    response.status_code = 404
    response.text = '{"code":"PGRST205","message":"scraper_heartbeat missing"}'
    post = Mock(return_value=response)
    monkeypatch.setattr(runtime.requests, "post", post)

    assert runtime.update_heartbeat("started") is False
    assert runtime._HEARTBEAT_TABLE_AVAILABLE is False
    assert post.call_count == 1

    assert runtime.update_heartbeat("idle") is False
    assert post.call_count == 1


def test_runtime_guard_patches_engine_hooks(monkeypatch):
    old_update = runtime.engine.update_heartbeat
    old_check = runtime.engine.check_new_scraper_signal
    try:
        runtime._install_runtime_guards()
        assert runtime.engine.update_heartbeat is runtime.update_heartbeat
        assert runtime.engine.check_new_scraper_signal is runtime.check_new_scraper_signal
    finally:
        runtime.engine.update_heartbeat = old_update
        runtime.engine.check_new_scraper_signal = old_check
