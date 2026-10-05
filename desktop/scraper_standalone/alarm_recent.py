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
- Overlapping incremental history windows are fetched from Supabase once per
  signal cycle and then served from an in-memory raw-row cache.
"""

from datetime import timedelta

import alarm_recent_base as _base
import alarm_recent_part2 as _part2
import alarm_recent_part3 as _part3
from alarm_recent_shared import fetch_shared_snapshot_window, make_cached_get

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
_ORIGINAL_RUN_ALL_INCREMENTAL = _part3._run_all_incremental

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


def _shared_window_bounds(calculator):
    """Return the superset time range needed by all six incremental motors."""
    signal = getattr(calculator, "_active_signal", None)
    if not isinstance(signal, dict):
        return None
    current_dt = _base._dt(signal.get("created_at"))
    if current_dt is None:
        return None

    previous = _load_previous_scrape_complete_signals(calculator, signal, count=21)
    previous_times = [_base._dt(row.get("created_at")) for row in previous]
    previous_times = [value for value in previous_times if value is not None]

    # Sharp needs up to the previous 21 scrape cycles. On a brand-new source
    # where no prior signal exists, preserve its existing four-hour fallback.
    if previous_times:
        sharp_start = min(previous_times) - timedelta(minutes=_base.SIGNAL_PAD_MINUTES)
    else:
        sharp_start = current_dt - timedelta(hours=4)

    # Dropping is time-based rather than cycle-count based.
    config = _part3._effective_config(calculator, "dropping")
    persistence = _part3._legacy.parse_float(config.get("persistence_minutes"))
    dropping_lookback = max(60.0, float(persistence) + 30.0)
    dropping_start = current_dt - timedelta(minutes=dropping_lookback)

    # Part2 falls back to 90 minutes if there are no previous signals.
    part2_start = current_dt - timedelta(minutes=90)
    return min(sharp_start, dropping_start, part2_start), current_dt


def _prepare_shared_snapshot_window(calculator, original_get):
    bounds = _shared_window_bounds(calculator)
    if bounds is None:
        return None
    start_dt, end_dt = bounds
    window = fetch_shared_snapshot_window(
        original_get,
        start_dt,
        end_dt,
        page_size=_base.PAGE_SIZE,
        max_rows=INCREMENTAL_MAX_ROWS,
        logger=_base._legacy.log,
    )
    if window.truncated:
        _base._legacy.log(
            f"[SharedAlarmWindow] hard cap reached ({INCREMENTAL_MAX_ROWS}); "
            "shared cache disabled, per-motor fail-closed guards remain active"
        )
        return None
    return window


def _run_all_incremental_shared(calculator):
    """Run the canonical six engines with one shared Supabase history fetch."""
    original_get = getattr(calculator, "_get", None)
    if not callable(original_get):
        # Unit/legacy compatibility objects without the REST client keep the
        # original runner behavior.
        return _ORIGINAL_RUN_ALL_INCREMENTAL(calculator)

    window = None
    try:
        try:
            window = _prepare_shared_snapshot_window(calculator, original_get)
        except Exception as exc:
            _base._legacy.log(f"[SharedAlarmWindow] preload failed; fallback enabled: {exc}")
            window = None

        if window is not None:
            calculator._get = make_cached_get(window, original_get)
            calculator._shared_alarm_snapshot_window = window
        return _ORIGINAL_RUN_ALL_INCREMENTAL(calculator)
    finally:
        calculator._get = original_get
        if hasattr(calculator, "_shared_alarm_snapshot_window"):
            try:
                delattr(calculator, "_shared_alarm_snapshot_window")
            except Exception:
                calculator._shared_alarm_snapshot_window = None


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
_part3._run_all_incremental = _run_all_incremental_shared


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
