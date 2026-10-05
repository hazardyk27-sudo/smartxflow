from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
    old_scan = runtime.engine.run_scan
    try:
        runtime._install_runtime_guards()
        assert runtime.engine.update_heartbeat is runtime.update_heartbeat
        assert runtime.engine.check_new_scraper_signal is runtime.check_new_scraper_signal
        assert runtime.engine.run_scan is runtime.run_scan_guarded
    finally:
        runtime.engine.update_heartbeat = old_update
        runtime.engine.check_new_scraper_signal = old_check
        runtime.engine.run_scan = old_scan


def test_current_kickoff_parser_does_not_roll_stale_september_into_next_year():
    now = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)

    parsed = runtime._parse_current_kickoff("27.Sep 12:00:00", now)

    assert parsed == datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)
    assert parsed < now


def test_current_kickoff_parser_handles_year_boundary_by_nearest_date():
    now = datetime(2026, 12, 28, 12, 0, tzinfo=timezone.utc)

    parsed = runtime._parse_current_kickoff("02.Jan 18:00:00", now)

    assert parsed == datetime(2027, 1, 2, 18, 0, tzinfo=timezone.utc)
    assert parsed > now


def test_strict_current_snapshot_read_filters_started_and_invalid_rows(monkeypatch):
    runtime.engine.SUPABASE_URL = "https://example.supabase.co"
    runtime.engine.SUPABASE_ANON_KEY = "anon"
    now = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)

    response = Mock()
    response.status_code = 200
    response.json.return_value = [
        {
            "home": "Future FC",
            "away": "Away",
            "league": "League",
            "date": "05.Oct 13:00:00",
            "volume": "1000",
        },
        {
            "home": "Equal FC",
            "away": "Away",
            "league": "League",
            "date": "05.Oct 12:00:00",
            "volume": "1000",
        },
        {
            "home": "Old FC",
            "away": "Away",
            "league": "League",
            "date": "27.Sep 12:00:00",
            "volume": "1000",
        },
        {
            "home": "Bad Date",
            "away": "Away",
            "league": "League",
            "date": "bad-date",
            "volume": "1000",
        },
        {
            "home": "",
            "away": "Away",
            "league": "League",
            "date": "05.Oct 13:00:00",
            "volume": "1000",
        },
    ]
    monkeypatch.setattr(runtime.requests, "get", Mock(return_value=response))

    snapshots, active_keys = runtime._fetch_current_snapshots_strict(now_utc=now)

    assert snapshots is not None
    assert set(snapshots) == {"Future FC|Away|05.Oct 13:00:00"}
    assert active_keys == {"Future FC|Away|05.Oct 13:00:00"}
    assert snapshots["Future FC|Away|05.Oct 13:00:00"]["match_id_hash"] == (
        "Future FC|Away|05.Oct 13:00:00"
    )


def test_strict_current_snapshot_read_fails_closed_on_http_error(monkeypatch):
    runtime.engine.SUPABASE_URL = "https://example.supabase.co"
    response = Mock()
    response.status_code = 503
    response.text = "unavailable"
    monkeypatch.setattr(runtime.requests, "get", Mock(return_value=response))

    snapshots, active_keys = runtime._fetch_current_snapshots_strict()

    assert snapshots is None
    assert active_keys is None


def test_guarded_scan_skips_all_engines_when_latest_scrape_is_stale(monkeypatch):
    stale = (datetime.now(timezone.utc) - timedelta(seconds=runtime.MAX_PREMATCH_AGE_SECONDS + 1)).isoformat()
    heartbeats = []

    monkeypatch.setattr(runtime, "_latest_scrape_complete_timestamp", lambda: stale)
    monkeypatch.setattr(
        runtime,
        "_fetch_current_snapshots_strict",
        lambda now_utc=None: (_ for _ in ()).throw(AssertionError("current table must not be read")),
    )
    monkeypatch.setattr(
        runtime,
        "update_heartbeat",
        lambda status, error_message=None: heartbeats.append((status, error_message)) or True,
    )

    assert runtime.run_scan_guarded() is False
    assert len(heartbeats) == 1
    assert heartbeats[0][0] == "stale_input"
    assert "stale" in heartbeats[0][1]


def test_guarded_scan_uses_current_only_snapshot_set(monkeypatch):
    fresh = datetime.now(timezone.utc).isoformat()
    key = "Home|Away|05.Oct 23:00:00"
    row = {
        "home": "Home",
        "away": "Away",
        "league": "League",
        "date": "05.Oct 23:00:00",
        "volume": "1000",
    }
    snapshots = {key: row}
    active_keys = {key}
    calls = []
    lookup = {"lookup": row}
    history = {"history": []}
    first = {"first": row}

    monkeypatch.setattr(runtime, "_latest_scrape_complete_timestamp", lambda: fresh)
    monkeypatch.setattr(
        runtime,
        "_fetch_current_snapshots_strict",
        lambda now_utc=None: (snapshots, active_keys),
    )
    monkeypatch.setattr(runtime.engine, "build_snapshot_lookup", lambda rows: lookup)
    monkeypatch.setattr(
        runtime.engine,
        "fetch_recent_history",
        lambda keys: calls.append(("history", keys)) or history,
    )
    monkeypatch.setattr(
        runtime.engine,
        "fetch_first_snapshots",
        lambda keys: calls.append(("first", keys)) or first,
    )
    monkeypatch.setattr(
        runtime.engine,
        "run_underdog_scan",
        lambda s, l, a: calls.append(("underdog", s, l, a)),
    )
    monkeypatch.setattr(
        runtime.engine,
        "run_cm_scan",
        lambda s, l, a, history=None, first_snaps=None: calls.append(
            ("cm", s, l, a, history, first_snaps)
        ),
    )
    monkeypatch.setattr(
        runtime.engine,
        "run_cm_v2_scan",
        lambda s, l, a, history=None, first_snaps=None: calls.append(
            ("cmv2", s, l, a, history, first_snaps)
        ),
    )
    monkeypatch.setattr(
        runtime.engine,
        "run_fs_scan",
        lambda s, l, a, history=None, first_snaps=None: calls.append(
            ("fs", s, l, a, history, first_snaps)
        ),
    )
    monkeypatch.setattr(
        runtime.engine,
        "run_eml_scan",
        lambda s, a: calls.append(("eml", s, a)),
    )

    assert runtime.run_scan_guarded() is True
    assert ("history", active_keys) in calls
    assert ("first", active_keys) in calls
    assert ("underdog", snapshots, lookup, active_keys) in calls
    assert ("cm", snapshots, lookup, active_keys, history, first) in calls
    assert ("cmv2", snapshots, lookup, active_keys, history, first) in calls
    assert ("fs", snapshots, lookup, active_keys, history, first) in calls
    assert ("eml", snapshots, active_keys) in calls


def test_guarded_scan_accepts_proven_empty_current_set_without_history_fallback(monkeypatch):
    fresh = datetime.now(timezone.utc).isoformat()
    monkeypatch.setattr(runtime, "_latest_scrape_complete_timestamp", lambda: fresh)
    monkeypatch.setattr(runtime, "_fetch_current_snapshots_strict", lambda now_utc=None: ({}, set()))
    monkeypatch.setattr(
        runtime.engine,
        "fetch_recent_history",
        lambda keys: (_ for _ in ()).throw(AssertionError("history must not be fetched")),
    )

    assert runtime.run_scan_guarded() is True
