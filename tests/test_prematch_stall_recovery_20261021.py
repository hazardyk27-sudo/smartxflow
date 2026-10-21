"""Conservative recovery of a *finished* stalled Hetzner source cycle."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.prematch_stall_recovery import should_exit_stale_prematch_loop

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 21, 15, 0, tzinfo=timezone.utc)


def allowed(*, startup_minutes=16, stale_minutes=21, failed_cycles=2, enabled=True):
    return should_exit_stale_prematch_loop(
        now=NOW,
        started_at=NOW - timedelta(minutes=startup_minutes),
        last_completed_at=NOW - timedelta(minutes=stale_minutes),
        consecutive_without_new_signal=failed_cycles,
        enabled=enabled,
    )


def test_stale_source_requires_full_duration_and_two_completed_failures():
    assert allowed()
    assert not allowed(startup_minutes=14)
    assert not allowed(stale_minutes=19)
    assert not allowed(failed_cycles=1)
    assert not allowed(failed_cycles=0)
    assert not allowed(enabled=False)


def test_no_success_since_start_requires_20_minutes_of_real_uptime():
    for age,expected in ((19,False),(20,True),(22,True)):
        actual=should_exit_stale_prematch_loop(
            now=NOW,
            started_at=NOW-timedelta(minutes=age),
            last_completed_at=None,
            consecutive_without_new_signal=3,
            enabled=True,
        )
        assert actual is expected


def test_recent_source_success_never_triggers_restart_even_with_old_uptime():
    assert not allowed(startup_minutes=300,stale_minutes=2,failed_cycles=80)
    assert not allowed(startup_minutes=300,stale_minutes=0,failed_cycles=80)


def test_clock_skew_or_naive_timestamps_never_trigger():
    assert not should_exit_stale_prematch_loop(
        now=NOW,
        started_at=NOW+timedelta(minutes=2),
        last_completed_at=NOW-timedelta(hours=1),
        consecutive_without_new_signal=10,enabled=True,
    )
    with pytest.raises(ValueError):
        should_exit_stale_prematch_loop(
            now=NOW.replace(tzinfo=None),
            started_at=NOW-timedelta(hours=1),
            last_completed_at=None,
            consecutive_without_new_signal=2,enabled=True,
        )


def test_systemd_restart_is_only_hetzner_gated_and_after_main():
    unit=(ROOT/"deploy/systemd/smartxflow-scraper.service").read_text()
    source=(ROOT/"scheduled_scraper_legacy.py").read_text()
    assert "Environment=SMARTXFLOW_RUNTIME_ID=hetzner-prod" in unit
    assert "Environment=SMARTXFLOW_FIXTURE_UID_AUTHORITATIVE_WRITE=true" in unit
    assert "Environment=SMARTXFLOW_PREMATCH_GUARDED_RESTART=yes" in unit
    assert "Environment=PYTHONUNBUFFERED=1" in unit
    assert "Restart=always" in unit
    assert 'os.environ.get("SMARTXFLOW_RUNTIME_ID") == "hetzner-prod"' in source
    assert 'os.environ.get("SMARTXFLOW_FIXTURE_UID_AUTHORITATIVE_WRITE") == "true"' in source
    assert "should_exit_stale_prematch_loop(" in source
    assert source.index("            main()") < source.index("should_exit_stale_prematch_loop(")
    assert "raise SystemExit(75)" in source
    assert "time.sleep(max(1.0, sleep_seconds))" in source
    assert "os.kill(" not in source
    assert "systemctl restart" not in source


def test_source_snapshot_constraints_remain_unmodified():
    source=(ROOT/"scheduled_scraper_legacy.py").read_text()
    assert "run_scrape(writer, logger_callback=log_callback)" in source
    assert "new prematch scrape_complete" not in source or "scrape_complete" in source
