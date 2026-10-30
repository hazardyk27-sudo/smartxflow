from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import gzip
import io
import json
import re
from typing import Any


ARCHIVE_SCHEMA = "SXF_SIGNAL_PERFORMANCE_DAY_V1"
_SCORE = re.compile(r"^(\d{1,2})\s*-\s*(\d{1,2})$")


class SignalArchiveError(RuntimeError):
    pass


def _json_line(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _signal_event(item: dict[str, Any]) -> dict[str, Any]:
    event_id = item.get("id")
    if type(event_id) is not int or event_id <= 0:
        raise SignalArchiveError("signal event is missing a valid source event id")
    day = item.get("day")
    if not isinstance(day, str) or not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", day):
        raise SignalArchiveError("signal event has an invalid local kickoff day")
    required = ("uid", "engine", "market", "selection", "kickoff_utc", "recorded_at")
    if any(not isinstance(item.get(key), str) or not item[key].strip() for key in required):
        raise SignalArchiveError("signal event is missing required identity or timing data")
    return {
        "event": "SIGNAL_RECORDED",
        "event_id": event_id,
        "fixture_uid": item["uid"],
        "day": day,
        "kickoff_utc": item["kickoff_utc"],
        "home": str(item.get("home") or "")[:100],
        "away": str(item.get("away") or "")[:100],
        "league": str(item.get("league") or "")[:100],
        "engine": item["engine"],
        "market": item["market"],
        "selection": item["selection"],
        "kind": str(item.get("kind") or ""),
        "ruleset_version": str(item.get("ruleset_version") or ""),
        "family": str(item.get("family") or ""),
        "checkpoint_hours": item.get("checkpoint"),
        "source_checkpoint_hours": item.get("source_checkpoint"),
        "recorded_at": item["recorded_at"],
        "observed_at": item.get("observed_at"),
        "delivery_timing": item.get("delivery_timing"),
        "odds": item.get("odds"),
        "amount": item.get("amount"),
        "share": item.get("share"),
        "shadow": True,
    }


def _status_event(item: dict[str, Any], archived_at: str) -> dict[str, Any]:
    return {
        "event": "SIGNAL_STATUS_OBSERVED",
        "event_id": item["id"],
        "archived_at": archived_at,
        "stage_status": item.get("stage_status"),
        "selection_status": item.get("selection_status"),
        "review_state": item.get("review_state"),
        "valid_on_time": item.get("valid_on_time") is True,
        "retention_status": (item.get("retention") or {}).get("status")
        if isinstance(item.get("retention"), dict) else None,
    }


def _grade(engine: str, market: str, selection: str, score: str) -> str | None:
    match = _SCORE.fullmatch(score)
    if not match:
        return None
    home, away = map(int, match.groups())
    if home > 30 or away > 30:
        return None
    if engine == "SURPRISE_TEAM" and market == "1X2" and selection in ("1", "2"):
        # The frozen research contract grades SURPRISE as team non-loss.
        won = home >= away if selection == "1" else away >= home
        return "WIN" if won else "LOSS"
    if market == "1X2" and selection in ("1", "X", "2"):
        result = "1" if home > away else "2" if away > home else "X"
        return "WIN" if selection == result else "LOSS"
    if market == "OU25" and selection in ("O", "U"):
        return "WIN" if ((home + away > 2) == (selection == "O")) else "LOSS"
    if market == "BTTS" and selection in ("Y", "N"):
        both = home > 0 and away > 0
        return "WIN" if (both == (selection == "Y")) else "LOSS"
    return None


def _settlement_event(item: dict[str, Any], archived_at: str) -> dict[str, Any] | None:
    if item.get("result_state") != "FT":
        return None
    score = str(item.get("final_score") or "")
    match = _SCORE.fullmatch(score)
    if not match:
        return None
    outcome = _grade(str(item.get("engine") or ""), str(item.get("market") or ""),
                     str(item.get("selection") or ""), score)
    return {
        "event": "SETTLEMENT_RECORDED",
        "event_id": item["id"],
        "settled_at": archived_at,
        "score_90m": score,
        "outcome": outcome or "UNGRADABLE",
        "result_source": "live_fixtures exact fixture/match/kickoff identity; FT only",
        "grading_rule": "SURPRISE_TEAM_NONLOSS" if item.get("engine") == "SURPRISE_TEAM" else "NATIVE_MARKET_SELECTION",
    }


def decode_day(payload: bytes) -> list[dict[str, Any]]:
    if not payload:
        return []
    try:
        raw = gzip.decompress(payload)
        rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SignalArchiveError("stored signal day archive is malformed") from exc
    if any(not isinstance(row, dict) for row in rows):
        raise SignalArchiveError("stored signal day archive contains an invalid record")
    return rows


def encode_day(events: list[dict[str, Any]]) -> bytes:
    raw = b"".join(_json_line(event) for event in events)
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode="wb", filename="", mtime=0, compresslevel=9) as gz:
        gz.write(raw)
    return out.getvalue()


def merge_feed_day(day: str, items: list[dict[str, Any]], previous: list[dict[str, Any]], *, archived_at: str | None = None) -> tuple[list[dict[str, Any]], bool]:
    """Append first signal, changed source-status, and first/corrected settlement events."""
    archived_at = archived_at or _utc_now()
    events = list(previous)
    signal_by_id: dict[int, dict[str, Any]] = {}
    status_by_id: dict[int, dict[str, Any]] = {}
    settlement_by_id: dict[int, dict[str, Any]] = {}
    for event in events:
        eid = event.get("event_id")
        if type(eid) is not int:
            raise SignalArchiveError("stored archive event has invalid source id")
        if event.get("event") == "SIGNAL_RECORDED":
            if eid in signal_by_id and signal_by_id[eid] != event:
                raise SignalArchiveError("duplicate immutable signal source id")
            signal_by_id[eid] = event
        elif event.get("event") == "SIGNAL_STATUS_OBSERVED":
            status_by_id[eid] = event
        elif event.get("event") in ("SETTLEMENT_RECORDED", "SETTLEMENT_CORRECTED"):
            settlement_by_id[eid] = event

    for item in sorted((row for row in items if row.get("day") == day), key=lambda row: row.get("id", 0)):
        signal = _signal_event(item)
        existing_signal = signal_by_id.get(signal["event_id"])
        if existing_signal is None:
            events.append(signal)
            signal_by_id[signal["event_id"]] = signal
        elif any(existing_signal.get(key) != value for key, value in signal.items()
                 if key not in ("event", "event_id")):
            raise SignalArchiveError("immutable signal source fields changed; refusing silent rewrite")

        status = _status_event(item, archived_at)
        previous_status = status_by_id.get(status["event_id"])
        if previous_status is None or any(previous_status.get(key) != value for key, value in status.items()
                                          if key not in ("event", "event_id", "archived_at")):
            events.append(status)
            status_by_id[status["event_id"]] = status

        settlement = _settlement_event(item, archived_at)
        if settlement:
            previous_settlement = settlement_by_id.get(settlement["event_id"])
            if previous_settlement is None:
                events.append(settlement)
                settlement_by_id[settlement["event_id"]] = settlement
            elif any(previous_settlement.get(key) != value for key, value in settlement.items()
                     if key not in ("event", "event_id", "settled_at")):
                corrected = {**settlement, "event": "SETTLEMENT_CORRECTED",
                             "previous_score_90m": previous_settlement.get("score_90m"),
                             "previous_outcome": previous_settlement.get("outcome")}
                events.append(corrected)
                settlement_by_id[settlement["event_id"]] = corrected

    events.sort(key=lambda event: (str(event.get("archived_at") or event.get("settled_at") or event.get("recorded_at") or ""),
                                   event.get("event_id", 0), event.get("event", "")))
    return events, events != previous


def summarize_day(day: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    signals = {row["event_id"]: row for row in events if row.get("event") == "SIGNAL_RECORDED"}
    statuses = {row["event_id"]: row for row in events if row.get("event") == "SIGNAL_STATUS_OBSERVED"}
    settlements = {row["event_id"]: row for row in events if row.get("event") in ("SETTLEMENT_RECORDED", "SETTLEMENT_CORRECTED")}
    # Performance counts one first, on-time, eligible signal for each engine and fixture.
    canonical: dict[tuple[str, str], dict[str, Any]] = {}
    for eid, signal in signals.items():
        status = statuses.get(eid, {})
        if (status.get("valid_on_time") is not True or status.get("selection_status") != "ELIGIBLE"
                or status.get("review_state") != "VALID_PREMATCH_RECORD"
                or status.get("stage_status") == "T8_HISTORICAL"
                or status.get("retention_status") == "BROKEN"):
            continue
        key = (str(signal.get("engine") or ""), str(signal.get("fixture_uid") or ""))
        old = canonical.get(key)
        if old is None or (signal.get("recorded_at", ""), eid) < (old.get("recorded_at", ""), old["event_id"]):
            canonical[key] = signal
    engines: dict[str, dict[str, int | float | None]] = defaultdict(lambda: {
        "signals": 0, "settled": 0, "wins": 0, "losses": 0, "pending": 0, "unverified": 0, "hit_rate_pct": None,
    })
    for (engine, _fixture), signal in canonical.items():
        metric = engines[engine]
        metric["signals"] += 1
        settlement = settlements.get(signal["event_id"])
        if not settlement:
            metric["pending"] += 1
        elif settlement.get("outcome") == "WIN":
            metric["settled"] += 1
            metric["wins"] += 1
        elif settlement.get("outcome") == "LOSS":
            metric["settled"] += 1
            metric["losses"] += 1
        else:
            metric["unverified"] += 1
    for metric in engines.values():
        settled = metric["settled"]
        metric["hit_rate_pct"] = round(metric["wins"] * 100 / settled, 2) if settled else None
    by_engine = {name: engines[name] for name in sorted(engines)}
    return {
        "date": day,
        "status": "ARCHIVED",
        "source_complete": False,
        "logged_events": len(signals),
        "settled_signals": sum(v["settled"] for v in by_engine.values()),
        "pending_signals": sum(v["pending"] for v in by_engine.values()),
        "hit_rate_basis": "unique on-time eligible engine/fixture signals; settled WIN+LOSS only",
        "engines": by_engine,
    }

