"""Conservative scraper recovery at a *completed* loop boundary.

No process can be restarted in the middle of an unknown Supabase write:
callers evaluate this predicate ONLY after the whole scrape attempt has
returned and the cross-host lease guard released the local writer lock.
"""
from __future__ import annotations
from datetime import datetime, timezone


def should_exit_stale_prematch_loop(
    *, now: datetime, started_at: datetime, last_completed_at: datetime | None,
    consecutive_without_new_signal: int, enabled: bool,
    source_stale_seconds: int = 1200, min_uptime_seconds: int = 900,
) -> bool:
    if not enabled or consecutive_without_new_signal < 2:
        return False
    if now.tzinfo is None or started_at.tzinfo is None or (
        last_completed_at is not None and last_completed_at.tzinfo is None
    ):
        raise ValueError("prematch recovery requires timezone-aware timestamps")
    now = now.astimezone(timezone.utc)
    started_at = started_at.astimezone(timezone.utc)
    anchor = (last_completed_at or started_at).astimezone(timezone.utc)
    # Fail closed for nonsensical timestamps or not-yet-proven long stalls.
    return (0 <= (now - started_at).total_seconds()
            and (now - started_at).total_seconds() >= min_uptime_seconds
            and (now - anchor).total_seconds() >= source_stale_seconds)
