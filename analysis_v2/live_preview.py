"""Read-only Analysis V2 live fallback for preview environments.

This module computes V2 cards from existing Moneyway snapshot/history tables
without creating or mutating the immutable V2 ledger. It is intended for
preview/testing when production and preview share the same Supabase project and
DB migrations are intentionally forbidden.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from .market_movement import SnapshotHistoryClient
from .presenter import present_signal
from .runtime import RuntimeConfig, evaluate_source_candidate


LIVE_PREVIEW_VERSION = "analysis-v2-live-preview-1.0.0"


def _num(value: Any) -> Optional[float]:
    if value in (None, "", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fixture(row: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "match_id_hash": str(row.get("match_id_hash") or ""),
        "home_team": str(row.get("home_team") or ""),
        "away_team": str(row.get("away_team") or ""),
        "league": str(row.get("league") or ""),
        "kickoff_utc": row.get("kickoff_utc") or row.get("match_date"),
    }


def _current_cycle_rows(rows: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Keep the latest scrape timestamp per exact match+market+selection."""
    latest: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for raw in rows:
        if not isinstance(raw, Mapping):
            continue
        row = dict(raw)
        key = (
            str(row.get("match_id_hash") or "").lower(),
            str(row.get("market") or "").upper(),
            str(row.get("selection") or "").upper(),
        )
        if not all(key):
            continue
        prev = latest.get(key)
        if prev is None or str(row.get("scraped_at_utc") or "") > str(prev.get("scraped_at_utc") or ""):
            latest[key] = row
    return list(latest.values())


def _rank_matches(current_rows: Iterable[Mapping[str, Any]], limit: int) -> List[str]:
    totals: Dict[str, float] = defaultdict(float)
    for row in current_rows:
        if str(row.get("market") or "").upper() != "1X2":
            continue
        match_hash = str(row.get("match_id_hash") or "").lower()
        if not match_hash:
            continue
        totals[match_hash] += _num(row.get("volume")) or 0.0
    return [
        match_hash
        for match_hash, _ in sorted(
            totals.items(), key=lambda item: item[1], reverse=True
        )[: max(1, int(limit))]
    ]


def compute_live_cards(
    *,
    snapshot_client: SnapshotHistoryClient,
    fixtures: Mapping[str, Mapping[str, Any]],
    recent_snapshot_rows: Iterable[Mapping[str, Any]],
    as_of: Any,
    max_matches: int = 24,
    runtime_config: Optional[RuntimeConfig] = None,
) -> Dict[str, Any]:
    """Compute presentable V2 cards without any DB writes."""
    cfg = runtime_config or RuntimeConfig()
    current_rows = _current_cycle_rows(recent_snapshot_rows)
    selected_matches = set(_rank_matches(current_rows, max_matches))

    by_match: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in current_rows:
        match_hash = str(row.get("match_id_hash") or "").lower()
        if match_hash in selected_matches:
            by_match[match_hash].append(dict(row))

    cards: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []

    for match_hash in selected_matches:
        fixture = dict(fixtures.get(match_hash) or {})
        if not fixture or not fixture.get("kickoff_utc"):
            continue
        try:
            history_rows = snapshot_client.fetch_match_rows(
                match_id_hash=match_hash,
                as_of=as_of,
            )
            for source_market, allowed in (
                ("1X2", {"1", "X", "2"}),
                ("DC", {"1X", "X2"}),
            ):
                source_rows = [
                    row for row in by_match.get(match_hash, [])
                    if str(row.get("market") or "").upper() == source_market
                    and str(row.get("selection") or "").upper() in allowed
                ]
                for source in source_rows:
                    selection = str(source.get("selection") or "").upper()
                    payload = evaluate_source_candidate(
                        history_rows,
                        match_id_hash=match_hash,
                        home_team=str(fixture.get("home_team") or ""),
                        away_team=str(fixture.get("away_team") or ""),
                        league=str(fixture.get("league") or ""),
                        kickoff_utc=fixture.get("kickoff_utc"),
                        source_market=source_market,
                        source_selection=selection,
                        as_of=as_of,
                        runtime_config=cfg,
                    )
                    if payload is None:
                        continue

                    # Presenters expect a ledger-like row. Live preview rows are
                    # explicitly marked and never get settlement/history claims.
                    payload = dict(payload)
                    payload["signal_id"] = (
                        "live_" + match_hash[:12] + "_" + source_market.lower() + "_" + selection.lower()
                    )
                    payload["current_state"] = "LIVE_PREVIEW"
                    payload["features"] = dict(payload.get("features") or {})
                    payload["features"]["live_preview"] = {
                        "version": LIVE_PREVIEW_VERSION,
                        "read_only": True,
                        "ephemeral": True,
                    }
                    card = present_signal(payload)
                    card["live_preview"] = True
                    cards.append(card)
        except Exception as exc:
            errors.append({"match_id_hash": match_hash, "error": str(exc)})

    # Deduplicate by match+recommended expression, preferring the strongest
    # user-facing state then the newest trigger.
    priority = {"FIRSAT": 3, "IZLE": 2, "UZAK_DUR": 1, "UNKNOWN": 0}
    dedup: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for card in cards:
        reco = card.get("recommendation") or {}
        key = (
            str(card.get("match") or ""),
            str(reco.get("market") or card.get("details", {}).get("source_market") or ""),
            str(reco.get("selection") or card.get("details", {}).get("source_selection") or ""),
        )
        prev = dedup.get(key)
        if prev is None or priority.get(card.get("state"), 0) > priority.get(prev.get("state"), 0):
            dedup[key] = card

    final_cards = sorted(
        dedup.values(),
        key=lambda card: (
            priority.get(card.get("state"), 0),
            card.get("trigger_at") or "",
        ),
        reverse=True,
    )
    counts = {"FIRSAT": 0, "IZLE": 0, "UZAK_DUR": 0, "UNKNOWN": 0}
    for card in final_cards:
        state = card.get("state") if card.get("state") in counts else "UNKNOWN"
        counts[state] += 1

    return {
        "available": True,
        "mode": "live_preview",
        "live_preview_version": LIVE_PREVIEW_VERSION,
        "read_only": True,
        "history_available": False,
        "settlement_available": False,
        "generated_at": _iso_now(),
        "signals": final_cards,
        "count": len(final_cards),
        "counts": counts,
        "error_count": len(errors),
        "errors": errors[:10],
    }
