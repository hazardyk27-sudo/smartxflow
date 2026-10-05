from __future__ import annotations

from datetime import datetime, timezone
import re
import unicodedata
from typing import Any

from .revisit import RevisitCaptureError, snapshot_timestamp


class SettlementError(ValueError):
    pass


_SCORE_RE = re.compile(r"^\s*(\d+)\s*[-:]\s*(\d+)\s*$")


def _parse_utc(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise SettlementError(f"{field} must be a non-empty ISO-8601 datetime")
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise SettlementError(f"{field} must be a valid ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SettlementError(f"{field} must include timezone")
    return parsed.astimezone(timezone.utc)


def parse_final_score(score: str) -> tuple[int, int]:
    if not isinstance(score, str):
        raise SettlementError("final score must be text")
    match = _SCORE_RE.match(score)
    if not match:
        raise SettlementError(f"unsupported final score format: {score!r}")
    return int(match.group(1)), int(match.group(2))


def normalize_score(score: str) -> str:
    home, away = parse_final_score(score)
    return f"{home}-{away}"


def _norm(value: Any) -> str:
    raw = unicodedata.normalize("NFKD", str(value or ""))
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "", raw.lower())


def _selection_outcome(case: dict[str, Any], final_score: str) -> str:
    prediction = case.get("prediction") or {}
    match = case.get("match") or {}
    market = str(prediction.get("market") or "").strip()
    selection = str(prediction.get("selection") or "").strip()
    if not market or not selection:
        raise SettlementError("market/selection are required to settle a priced selection")

    home_goals, away_goals = parse_final_score(final_score)
    total = home_goals + away_goals
    market_norm = _norm(market)
    selection_norm = _norm(selection)
    home_norm = _norm(match.get("home"))
    away_norm = _norm(match.get("away"))

    if market_norm in {"1x2", "matchodds", "fulltimeresult"}:
        if selection_norm in {"1", "home", home_norm}:
            return "WIN" if home_goals > away_goals else "LOSS"
        if selection_norm in {"x", "draw"}:
            return "WIN" if home_goals == away_goals else "LOSS"
        if selection_norm in {"2", "away", away_norm}:
            return "WIN" if away_goals > home_goals else "LOSS"
        raise SettlementError(f"unsupported 1X2 selection: {selection!r}")

    if "doublechance" in market_norm or market_norm in {"dc", "1xx2"}:
        code = selection.upper().replace(" ", "")
        if code == "1X":
            return "WIN" if home_goals >= away_goals else "LOSS"
        if code == "X2":
            return "WIN" if away_goals >= home_goals else "LOSS"
        if code == "12":
            return "WIN" if home_goals != away_goals else "LOSS"
        raise SettlementError(f"unsupported Double Chance selection: {selection!r}")

    if "btts" in market_norm or "bothteamstoscore" in market_norm or "kg" in market_norm:
        both = home_goals > 0 and away_goals > 0
        yes = selection_norm in {"yes", "var", "bttsyes", "kgvar"}
        no = selection_norm in {"no", "yok", "bttsno", "kgyok"}
        if not yes and not no:
            raise SettlementError(f"unsupported BTTS selection: {selection!r}")
        return "WIN" if both == yes else "LOSS"

    if "25" in market_norm or "overunder" in market_norm or market_norm.startswith("ou"):
        over = selection_norm in {"over", "over25", "25over", "ust", "25ust"} or "over" in selection_norm or "ust" in selection_norm
        under = selection_norm in {"under", "under25", "25under", "alt", "25alt"} or "under" in selection_norm or "alt" in selection_norm
        if not over and not under:
            raise SettlementError(f"unsupported O/U selection: {selection!r}")
        if total == 2.5:
            return "VOID"
        if over:
            return "WIN" if total > 2.5 else "LOSS"
        return "WIN" if total < 2.5 else "LOSS"

    raise SettlementError(f"unsupported market: {market!r}")


def build_settlement(
    case: dict[str, Any],
    *,
    final_score: str,
    result_source: str,
    result_observed_at: str,
    source_status: str = "ft",
) -> dict[str, Any]:
    decision = str((case.get("prediction") or {}).get("decision") or "").upper()
    score = normalize_score(final_score)
    _parse_utc(result_observed_at, "result_observed_at")

    settlement: dict[str, Any] = {
        "status": "NO_BET" if decision in {"WATCH", "PASS"} else "PENDING",
        "final_score": score,
        "ht_score": None,
        "closing_odds": None,
        "clv": None,
        "pnl_units": None,
        "roi": None,
        "result_source": str(result_source or "").strip(),
        "result_observed_at": result_observed_at,
        "source_status": str(source_status or "").strip().lower(),
        "hypothetical_result": None,
        "postmortem_class": None,
        "postmortem": None,
    }
    if not settlement["result_source"]:
        raise SettlementError("result_source is required")

    if decision == "BET":
        outcome = _selection_outcome(case, score)
        settlement["status"] = outcome
        odds = (case.get("prediction") or {}).get("entry_odds")
        if outcome == "WIN" and isinstance(odds, (int, float)) and not isinstance(odds, bool):
            settlement["pnl_units"] = round(float(odds) - 1.0, 6)
        elif outcome == "LOSS":
            settlement["pnl_units"] = -1.0
        elif outcome == "VOID":
            settlement["pnl_units"] = 0.0
        settlement["postmortem_class"] = "BET_RESULT_WIN" if outcome == "WIN" else "BET_RESULT_LOSS" if outcome == "LOSS" else "BET_RESULT_VOID"
        settlement["postmortem"] = f"Final score {score}; original BET settled {outcome}."
    elif decision == "WATCH":
        hypothetical = _selection_outcome(case, score)
        settlement["hypothetical_result"] = hypothetical
        settlement["postmortem_class"] = f"WATCH_WOULD_{hypothetical}"
        settlement["postmortem"] = f"Final score {score}; original decision remained WATCH. The watched selection would have settled {hypothetical}."
    elif decision == "PASS":
        settlement["postmortem_class"] = "PASS_NO_BET"
        settlement["postmortem"] = f"Final score {score}; original PASS is preserved and no wager outcome is assigned."
    else:
        raise SettlementError(f"unsupported prediction decision: {decision!r}")

    return settlement


def prepare_final_snapshots(case: dict[str, Any], snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(snapshots, list) or not snapshots:
        raise SettlementError("finalization requires non-empty stored SXF history")
    try:
        kickoff = _parse_utc(case["match"]["kickoff_at"], "match.kickoff_at")
    except (KeyError, TypeError) as exc:
        raise SettlementError("case is missing kickoff_at") from exc

    retained: list[tuple[datetime, int, dict[str, Any]]] = []
    for index, snapshot in enumerate(snapshots):
        if not isinstance(snapshot, dict):
            raise SettlementError(f"snapshots[{index}] must be an object")
        try:
            observed = snapshot_timestamp(snapshot)
        except RevisitCaptureError as exc:
            raise SettlementError(str(exc)) from exc
        if observed < kickoff:
            retained.append((observed, index, snapshot))

    if not retained:
        raise SettlementError("no stored SXF history exists strictly before kickoff")
    retained.sort(key=lambda item: (
        item[0],
        str(item[2].get("_archive_source_table") or item[2].get("market") or ""),
        item[1],
    ))
    return [snapshot for _, _, snapshot in retained]
