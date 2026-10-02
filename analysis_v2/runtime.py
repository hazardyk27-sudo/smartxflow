"""Analysis V2 runtime orchestration.

This module is the guarded bridge from stored Betwatch snapshots to the
immutable V2 ledger. It composes Parts 3-8 without changing any V1 engine.

Runtime activation is intentionally external/feature-flagged. Importing this
module has no side effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from .classification import (
    SUPPORTIVE_CLASSES if False else ClassificationConfig,
)
from .classification import (
    classification_to_signal_metadata,
    classify_market_movement,
)
from .cross_market import (
    STRUCTURAL_SELECTIONS,
    apply_cross_market_to_trigger,
    evaluate_cross_market,
    reconcile_market_selection,
)
from .explainable_confidence import (
    apply_explainable_confidence_to_trigger,
    build_explainable_confidence,
)
from .market_movement import (
    SnapshotHistoryClient,
    build_market_movement,
    movement_to_signal_fields,
)
from .market_selector import (
    SUPPORTIVE_CLASSES,
    apply_market_selection_to_trigger,
    direction_market_selection,
    select_direction_market,
)
from .poly_confirmation import (
    apply_poly_to_trigger,
    evaluate_poly_confirmation,
)
from .signal_store import SignalStore


RUNTIME_VERSION = "analysis-v2-runtime-1.0.0"

SOURCE_DIRECTION = {
    ("1X2", "1"): "1",
    ("1X2", "X"): "X",
    ("1X2", "2"): "2",
    ("DNB", "1"): "1",
    ("DNB", "2"): "2",
    ("DC", "1X"): "1",
    ("DC", "X2"): "2",
}

ENGINE_VERSIONS = {
    "confirmed_money_v2": "2.0.0",
    "underdog_pressure_v2": "2.0.0",
    "early_money_lock_v2": "2.0.0",
    "price_money_divergence_v2": "2.0.0",
    "late_steam_v2": "2.0.0",
    "anomalous_money_v2": "2.0.0",
    "double_chance_pressure_v2": "2.0.0",
}


@dataclass(frozen=True)
class RuntimeConfig:
    underdog_min_odds: float = 2.90
    min_source_market_volume: float = 5000.0
    min_source_selection_amount: float = 500.0
    anchor_tolerance_minutes: int = 60
    current_tolerance_minutes: int = 60


def _number(value: Any) -> Optional[float]:
    if value in (None, "", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _merge_metadata(
    payload: Mapping[str, Any],
    addition: Mapping[str, Any],
) -> Dict[str, Any]:
    result = dict(payload)
    for key, value in addition.items():
        if key in {"engine_reason", "features", "config_snapshot"}:
            merged = dict(result.get(key) or {})
            if isinstance(value, Mapping):
                merged.update(dict(value))
            result[key] = merged
        else:
            result[key] = value
    return result


def source_direction(market_key: str, selection_code: str) -> Optional[str]:
    return SOURCE_DIRECTION.get(
        (
            str(market_key or "").strip().upper(),
            str(selection_code or "").strip().upper(),
        )
    )


def _build_view(
    rows: Iterable[Dict[str, Any]],
    *,
    match_id_hash: str,
    market_key: str,
    selection_code: str,
    as_of: Any,
    kickoff_utc: Any,
    runtime_config: RuntimeConfig,
) -> Dict[str, Any]:
    features = build_market_movement(
        rows,
        match_id_hash=match_id_hash,
        market_key=market_key,
        selection_code=selection_code,
        as_of=as_of,
        kickoff_utc=kickoff_utc,
        anchor_tolerance_minutes=runtime_config.anchor_tolerance_minutes,
        current_tolerance_minutes=runtime_config.current_tolerance_minutes,
    )
    return {
        "selection_code": selection_code,
        "features": features,
        "classification": classify_market_movement(features),
    }


def build_runtime_views(
    rows: Iterable[Dict[str, Any]],
    *,
    match_id_hash: str,
    direction: str,
    as_of: Any,
    kickoff_utc: Any,
    runtime_config: Optional[RuntimeConfig] = None,
) -> Dict[str, Any]:
    cfg = runtime_config or RuntimeConfig()
    materialized = list(rows)
    views: Dict[str, Any] = {}

    for market_key, selection_code in direction_market_selection(direction).items():
        views[market_key] = _build_view(
            materialized,
            match_id_hash=match_id_hash,
            market_key=market_key,
            selection_code=selection_code,
            as_of=as_of,
            kickoff_utc=kickoff_utc,
            runtime_config=cfg,
        )

    for market_key, selections in STRUCTURAL_SELECTIONS.items():
        views[market_key] = {
            selection_code: _build_view(
                materialized,
                match_id_hash=match_id_hash,
                market_key=market_key,
                selection_code=selection_code,
                as_of=as_of,
                kickoff_utc=kickoff_utc,
                runtime_config=cfg,
            )
            for selection_code in selections
        }

    return views


def _source_view(
    views: Mapping[str, Any],
    *,
    source_market: str,
    source_selection: str,
) -> Optional[Dict[str, Any]]:
    market = str(source_market or "").strip().upper()
    selection = str(source_selection or "").strip().upper()
    direct = views.get(market)
    if isinstance(direct, Mapping) and direct.get("features"):
        if str(direct.get("selection_code") or "").upper() == selection:
            return dict(direct)
    if isinstance(direct, Mapping):
        nested = direct.get(selection)
        if isinstance(nested, Mapping):
            return dict(nested)
    return None


def choose_engine_key(
    *,
    source_market: str,
    source_selection: str,
    classification: Mapping[str, Any],
    source_features: Mapping[str, Any],
    config: Optional[RuntimeConfig] = None,
) -> Optional[str]:
    """Choose one primary engine identity to avoid duplicate UI cards."""
    cfg = config or RuntimeConfig()
    primary = str(classification.get("primary_class") or "NO_EDGE").upper()

    if primary == "PRICE_MONEY_DIVERGENCE":
        return "price_money_divergence_v2"
    if primary == "ANOMALOUS_MONEY":
        return "anomalous_money_v2"
    if primary == "LATE_STEAM":
        return "late_steam_v2"
    if primary == "EARLY_POSITION":
        return "early_money_lock_v2"

    if primary not in SUPPORTIVE_CLASSES:
        return None

    market = str(source_market or "").strip().upper()
    selection = str(source_selection or "").strip().upper()
    current = source_features.get("current") or {}
    current_odds = _number(current.get("odds"))

    if (
        market == "1X2"
        and selection in {"1", "2"}
        and current_odds is not None
        and current_odds >= cfg.underdog_min_odds
    ):
        return "underdog_pressure_v2"

    if market == "DC" and selection in {"1X", "X2"}:
        return "double_chance_pressure_v2"

    return "confirmed_money_v2"


def _poly_unavailable(
    direction: str,
    *,
    home_team: str,
    away_team: str,
) -> Dict[str, Any]:
    return evaluate_poly_confirmation(
        direction,
        home_team=home_team,
        away_team=away_team,
        general_trades=[],
        wallet_activity=[],
        wallet_stats=[],
    )


def evaluate_source_candidate(
    rows: Iterable[Dict[str, Any]],
    *,
    match_id_hash: str,
    home_team: str,
    away_team: str,
    league: str,
    kickoff_utc: Any,
    source_market: str,
    source_selection: str,
    as_of: Any,
    poly_result: Optional[Mapping[str, Any]] = None,
    runtime_config: Optional[RuntimeConfig] = None,
) -> Optional[Dict[str, Any]]:
    """Compose Parts 3-8 for one exact source market/selection."""
    cfg = runtime_config or RuntimeConfig()
    direction = source_direction(source_market, source_selection)
    if direction is None:
        return None

    views = build_runtime_views(
        rows,
        match_id_hash=match_id_hash,
        direction=direction,
        as_of=as_of,
        kickoff_utc=kickoff_utc,
        runtime_config=cfg,
    )
    source = _source_view(
        views,
        source_market=source_market,
        source_selection=source_selection,
    )
    if not source:
        return None

    source_features = source.get("features") or {}
    current = source_features.get("current") or {}
    current_volume = _number(current.get("market_volume"))
    current_amount = _number(current.get("amount"))
    if (
        current_volume is None
        or current_volume < cfg.min_source_market_volume
        or current_amount is None
        or current_amount < cfg.min_source_selection_amount
    ):
        return None

    classification = source.get("classification") or {}
    engine_key = choose_engine_key(
        source_market=source_market,
        source_selection=source_selection,
        classification=classification,
        source_features=source_features,
        config=cfg,
    )
    if engine_key is None:
        return None

    selector = select_direction_market(
        direction,
        views,
        source_market=source_market,
    )
    cross = evaluate_cross_market(
        direction,
        views,
        source_market=source_market,
    )
    selector = reconcile_market_selection(selector, cross)

    poly = (
        dict(poly_result)
        if isinstance(poly_result, Mapping)
        else _poly_unavailable(
            direction,
            home_team=home_team,
            away_team=away_team,
        )
    )

    confidence = build_explainable_confidence(
        movement_features=source_features,
        classification=classification,
        selector_result=selector,
        cross_market_result=cross,
        poly_result=poly,
    )

    payload: Dict[str, Any] = {
        "engine_key": engine_key,
        "engine_version": ENGINE_VERSIONS[engine_key],
        "match_id_hash": match_id_hash,
        "home_team": home_team,
        "away_team": away_team,
        "league": league,
        "kickoff_utc": kickoff_utc,
        "market_key": str(source_market).upper(),
        "selection_code": str(source_selection).upper(),
        "trigger_at": as_of,
        "raw_trigger": {
            "runtime_version": RUNTIME_VERSION,
            "direction": direction,
            "source_market": str(source_market).upper(),
            "source_selection": str(source_selection).upper(),
        },
    }
    payload = _merge_metadata(
        payload,
        movement_to_signal_fields(source_features),
    )
    payload = _merge_metadata(
        payload,
        classification_to_signal_metadata(classification),
    )
    payload = apply_market_selection_to_trigger(payload, selector)
    payload = apply_cross_market_to_trigger(payload, cross)
    payload = apply_poly_to_trigger(payload, poly)
    payload = apply_explainable_confidence_to_trigger(payload, confidence)

    features = dict(payload.get("features") or {})
    features["runtime"] = {
        "runtime_version": RUNTIME_VERSION,
        "direction": direction,
        "primary_engine": engine_key,
        "source_market": str(source_market).upper(),
        "source_selection": str(source_selection).upper(),
    }
    payload["features"] = features
    return payload


def _latest_cycle_candidates(
    current_snapshot_rows: Iterable[Mapping[str, Any]],
    *,
    max_matches: int,
    config: RuntimeConfig,
) -> List[Tuple[str, str, str]]:
    """Return (match_hash, source_market, selection) candidates by real volume."""
    rows = [dict(row) for row in current_snapshot_rows if isinstance(row, Mapping)]
    match_volume: Dict[str, float] = {}
    grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}

    for row in rows:
        match_hash = str(row.get("match_id_hash") or "").strip().lower()
        market = str(row.get("market") or "").strip().upper()
        if not match_hash or market not in {"1X2", "DC"}:
            continue
        grouped.setdefault((match_hash, market), []).append(row)
        if market == "1X2":
            match_volume[match_hash] = match_volume.get(match_hash, 0.0) + (
                _number(row.get("volume")) or 0.0
            )

    selected_matches = {
        match_hash
        for match_hash, _volume in sorted(
            match_volume.items(),
            key=lambda item: item[1],
            reverse=True,
        )[: max(1, int(max_matches))]
    }

    candidates: List[Tuple[str, str, str]] = []
    for (match_hash, market), market_rows in grouped.items():
        if match_hash not in selected_matches:
            continue
        total = sum(_number(row.get("volume")) or 0.0 for row in market_rows)
        if total < config.min_source_market_volume:
            continue
        allowed = {"1", "X", "2"} if market == "1X2" else {"1X", "X2"}
        for row in market_rows:
            selection = str(row.get("selection") or "").strip().upper()
            amount = _number(row.get("volume"))
            if (
                selection in allowed
                and amount is not None
                and amount >= config.min_source_selection_amount
            ):
                candidates.append((match_hash, market, selection))
    return candidates


def run_runtime_batch(
    *,
    snapshot_client: SnapshotHistoryClient,
    signal_store: SignalStore,
    fixtures: Mapping[str, Mapping[str, Any]],
    current_snapshot_rows: Iterable[Mapping[str, Any]],
    as_of: Any,
    max_matches: int = 120,
    runtime_config: Optional[RuntimeConfig] = None,
    logger=None,
) -> Dict[str, Any]:
    """Evaluate a bounded post-scrape batch and persist immutable triggers."""
    cfg = runtime_config or RuntimeConfig()
    log = logger or (lambda _message: None)
    candidates = _latest_cycle_candidates(
        current_snapshot_rows,
        max_matches=max_matches,
        config=cfg,
    )

    rows_cache: Dict[str, List[Dict[str, Any]]] = {}
    created: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []

    for match_hash, market, selection in candidates:
        fixture = fixtures.get(match_hash) or {}
        if not fixture:
            continue
        try:
            if match_hash not in rows_cache:
                rows_cache[match_hash] = snapshot_client.fetch_match_rows(
                    match_id_hash=match_hash,
                    as_of=as_of,
                )
            payload = evaluate_source_candidate(
                rows_cache[match_hash],
                match_id_hash=match_hash,
                home_team=str(fixture.get("home_team") or ""),
                away_team=str(fixture.get("away_team") or ""),
                league=str(fixture.get("league") or ""),
                kickoff_utc=fixture.get("kickoff_utc"),
                source_market=market,
                source_selection=selection,
                as_of=as_of,
                runtime_config=cfg,
            )
            if payload is None:
                continue
            stored = signal_store.create_signal_once(payload)
            created.append(stored)
        except Exception as exc:
            errors.append(
                {
                    "match_id_hash": match_hash,
                    "market": market,
                    "selection": selection,
                    "error": str(exc),
                }
            )
            log(
                f"[AnalysisV2] {match_hash} {market}/{selection} "
                f"runtime error: {exc}"
            )

    return {
        "runtime_version": RUNTIME_VERSION,
        "candidate_count": len(candidates),
        "signal_count": len(created),
        "signals": created,
        "error_count": len(errors),
        "errors": errors,
    }
