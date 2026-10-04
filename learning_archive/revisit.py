from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class RevisitCaptureError(ValueError):
    pass


_TIMESTAMP_KEYS = (
    "scraped_at_utc",
    "scraped_at",
    "snapshot_at",
    "observed_at",
    "created_at",
)


def _parse_utc(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise RevisitCaptureError(f"{field} must be a non-empty ISO-8601 datetime")
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise RevisitCaptureError(f"{field} must be a valid ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RevisitCaptureError(f"{field} must include timezone")
    return parsed.astimezone(timezone.utc)


def snapshot_timestamp(snapshot: dict[str, Any]) -> datetime:
    for key in _TIMESTAMP_KEYS:
        value = snapshot.get(key)
        if value not in (None, ""):
            return _parse_utc(value, f"snapshot.{key}")
    raise RevisitCaptureError("snapshot is missing an observed timestamp")


def prepare_revisit_snapshots(
    case: dict[str, Any],
    snapshots: list[dict[str, Any]],
    observed_at: str,
) -> list[dict[str, Any]]:
    """Return only stored SXF rows that existed at a valid prematch revisit cutoff.

    This is deliberately fail-closed: a revisit must be later than the immutable
    prediction cutoff, strictly before kickoff, and every retained source row must
    have a real timestamp no later than the requested observed_at. This prevents a
    delayed/backfill execution from leaking later or post-kickoff data into PRE.
    """
    if not isinstance(case, dict):
        raise RevisitCaptureError("case must be an object")
    if not isinstance(snapshots, list) or not snapshots:
        raise RevisitCaptureError("revisit requires non-empty stored SXF history")

    try:
        prediction_at_raw = case["prediction"]["prediction_at"]
        kickoff_at_raw = case["match"]["kickoff_at"]
    except (KeyError, TypeError) as exc:
        raise RevisitCaptureError("case is missing prediction_at or kickoff_at") from exc

    cutoff = _parse_utc(observed_at, "observed_at")
    prediction_at = _parse_utc(prediction_at_raw, "prediction.prediction_at")
    kickoff_at = _parse_utc(kickoff_at_raw, "match.kickoff_at")

    if cutoff <= prediction_at:
        raise RevisitCaptureError("revisit observed_at must be later than prediction_at")
    if cutoff >= kickoff_at:
        raise RevisitCaptureError("revisit observed_at must be strictly before kickoff_at")

    retained: list[tuple[datetime, int, dict[str, Any]]] = []
    for index, snapshot in enumerate(snapshots):
        if not isinstance(snapshot, dict):
            raise RevisitCaptureError(f"snapshots[{index}] must be an object")
        ts = snapshot_timestamp(snapshot)
        if ts <= cutoff:
            retained.append((ts, index, snapshot))

    if not retained:
        raise RevisitCaptureError("no stored SXF history exists at or before revisit observed_at")

    retained.sort(key=lambda item: (
        item[0],
        str(item[2].get("_archive_source_table") or item[2].get("market") or ""),
        item[1],
    ))
    return [snapshot for _, _, snapshot in retained]
