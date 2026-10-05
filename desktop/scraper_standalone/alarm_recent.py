"""Combined incremental alarm overrides used by Alarm Engine.

Part 1: BigMoney + MIM.
Part 2: VolumeLeader + VolumeShock.
Part 3: Sharp + Dropping + no-prefetch six-alarm runner.

Shared guards installed here keep every incremental alarm on the same contract:
- Previous-window boundaries come only from prematch ``scrape_complete`` signals.
- A fixture must still be prematch at the active signal timestamp.
- Snapshot windows have capacity for a 5-minute high-volume schedule.
- Hitting the snapshot safety cap fails closed instead of calculating on a
  silently truncated window.
"""

import alarm_recent_base as _base
import alarm_recent_part2 as _part2
import alarm_recent_part3 as _part3

for _name in dir(_base):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_base, _name)

_install_part1_alarm_overrides = _base.install_recent_alarm_overrides
_clear_part1_alarm_cache = _base.clear_recent_alarm_cache
_install_part2_alarm_overrides = _part2.install_part2_alarm_overrides
_clear_part2_alarm_cache = _part2.clear_part2_alarm_cache

_ORIGINAL_LOAD_FIXTURES = _base._load_fixtures
_ORIGINAL_BASE_WINDOW = _base._fetch_recent_snapshot_window
_ORIGINAL_PART2_WINDOW = _part2._fetch_part2_snapshot_window
_ORIGINAL_SHARP_WINDOW = _part3._fetch_sharp_window
_ORIGINAL_DROPPING_WINDOW = _part3._fetch_dropping_window

# 5-minute cadence capacity contract:
# 4,000 snapshot rows/cycle * 30 cycles for the default 150-minute Dropping
# lookback = 120,000 rows. 150k leaves a 25% buffer while remaining bounded.
INCREMENTAL_MAX_ROWS = 150_000
_base.MAX_ROWS = INCREMENTAL_MAX_ROWS
_part2.MAX_ROWS = INCREMENTAL_MAX_ROWS
_part3.MAX_ROWS = INCREMENTAL_MAX_ROWS


def _load_previous_scrape_complete_signals(calculator, signal, count=2):
    """Load prior prematch cycles only; ignore heartbeats or future signal types."""
    signal_id = signal.get("id")
    if signal_id is None:
        return []
    source = str(signal.get("source") or "replit")
    rows = calculator._get(
        "scraper_signal",
        f"select=id,created_at,source&id=lt.{int(signal_id)}"
        f"&source=eq.{source}&signal_type=eq.scrape_complete"
        f"&order=id.desc&limit={int(count)}",
    ) or []
    return rows


def _load_active_prematch_fixtures(calculator, hashes):
    """Return fixtures whose kickoff is strictly after the active signal time.

    Missing/invalid kickoff is fail-closed in incremental mode. Legacy callers
    without an active scraper signal retain the original fixture behavior.
    """
    fixtures = _ORIGINAL_LOAD_FIXTURES(calculator, hashes)
    signal = getattr(calculator, "_active_signal", None)
    if not isinstance(signal, dict):
        return fixtures

    signal_dt = _base._dt(signal.get("created_at"))
    if signal_dt is None:
        _base._legacy.log("[RecentAlarm Guard] invalid active signal timestamp; fixtures rejected")
        return {}

    active = {}
    missing_kickoff = 0
    started = 0
    for match_hash, fixture in fixtures.items():
        kickoff_dt = _base._dt(fixture.get("kickoff_utc"))
        if kickoff_dt is None:
            missing_kickoff += 1
            continue
        if kickoff_dt <= signal_dt:
            started += 1
            continue
        active[match_hash] = fixture

    if missing_kickoff or started:
        _base._legacy.log(
            f"[RecentAlarm Guard] fixture_filter active={len(active)} "
            f"started={started} missing_kickoff={missing_kickoff}"
        )
    return active


def _require_complete_window(name, payload):
    """Reject a window that reached the hard row cap.

    Reaching the cap cannot prove whether the final page was complete, so this
    is deliberately conservative. A skipped alarm cycle is safer than alarms
    calculated from a truncated recent-history window.
    """
    rows_loaded = int((payload or {}).get("rows_loaded") or 0)
    if rows_loaded >= INCREMENTAL_MAX_ROWS:
        message = (
            f"{name} snapshot window reached hard cap "
            f"({rows_loaded}/{INCREMENTAL_MAX_ROWS}); calculation aborted"
        )
        _base._legacy.log(f"[RecentAlarm Guard] {message}")
        raise RuntimeError(message)
    return payload


def _fetch_base_window_guarded(calculator):
    return _require_complete_window("Part1", _ORIGINAL_BASE_WINDOW(calculator))


def _fetch_part2_window_guarded(calculator):
    return _require_complete_window("Part2", _ORIGINAL_PART2_WINDOW(calculator))


def _fetch_sharp_window_guarded(calculator):
    return _require_complete_window("Sharp", _ORIGINAL_SHARP_WINDOW(calculator))


def _fetch_dropping_window_guarded(calculator, persistence_minutes):
    return _require_complete_window(
        "Dropping",
        _ORIGINAL_DROPPING_WINDOW(calculator, persistence_minutes),
    )


# Part modules import these helpers by name, so update every module-level alias.
_base._load_previous_signals = _load_previous_scrape_complete_signals
_part2._load_previous_signals = _load_previous_scrape_complete_signals
_part3._load_previous_signals = _load_previous_scrape_complete_signals
_base._load_fixtures = _load_active_prematch_fixtures
_part2._load_fixtures = _load_active_prematch_fixtures
_part3._load_fixtures = _load_active_prematch_fixtures
_base._fetch_recent_snapshot_window = _fetch_base_window_guarded
_part2._fetch_part2_snapshot_window = _fetch_part2_window_guarded
_part3._fetch_sharp_window = _fetch_sharp_window_guarded
_part3._fetch_dropping_window = _fetch_dropping_window_guarded


def install_recent_alarm_overrides(calculator_cls):
    _install_part1_alarm_overrides(calculator_cls)
    _install_part2_alarm_overrides(calculator_cls)
    # Force the first active-signal cycle to run expired-alarm cleanup once.
    # Later cycles are throttled to the normal one-hour interval by part 3.
    calculator_cls._incremental_cleanup_at = -_part3.CLEANUP_INTERVAL_SECONDS
    _part3.install_part3_alarm_overrides(calculator_cls)


def clear_recent_alarm_cache(calculator):
    _clear_part1_alarm_cache(calculator)
    _clear_part2_alarm_cache(calculator)
    _part3.clear_part3_alarm_cache(calculator)
