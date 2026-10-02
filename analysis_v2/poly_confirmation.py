"""Analysis V2 Part 7: Polymarket confirmation.

Part 7 is an independent confirmation/risk layer. It never creates the primary
Betwatch direction and never replaces Part 3/4/5/6 evidence.

The handoff contract has three components:
1. general Polymarket 1X2 direction,
2. big prematch trades,
3. consensus among historically successful tracked wallets.

Only exact Polymarket event_id reads are supported here. Team-name fuzzy event
resolution is intentionally outside this module.
"""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

import requests

from .market_selector import normalize_direction


POLY_CONFIRMATION_VERSION = "analysis-v2-part7-1.0.0"

DRAW_ALIASES = {
    "x",
    "draw",
    "beraberlik",
    "tie",
}

COMPONENT_SUPPORT = "SUPPORT"
COMPONENT_CONFLICT = "CONFLICT"
COMPONENT_NEUTRAL = "NEUTRAL"
COMPONENT_UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class PolyConfirmationConfig:
    general_min_volume_usdc: float = 10000.0
    general_lead_share_pct: float = 55.0
    general_min_margin_pct: float = 10.0

    big_trade_min_usdc: float = 5000.0
    big_trade_min_net_margin_usdc: float = 5000.0

    successful_wallet_min_win_rate_pct: float = 55.0
    successful_wallet_min_resolved_bets: int = 10
    successful_wallet_min_bet_usdc: float = 1000.0
    successful_wallet_min_consensus_wallets: int = 2
    successful_wallet_consensus_ratio: float = 2.0 / 3.0

    final_min_component_confirmations: int = 2
    final_min_component_conflicts: int = 2


def _number(value: Any) -> Optional[float]:
    if value in (None, "", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value or "").strip()
        if not raw:
            raise ValueError("timestamp is required")
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"invalid ISO timestamp: {raw}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _normalize_text(value: Any) -> str:
    text = str(value or "").strip().casefold()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _selection_direction(
    selection: Any,
    *,
    home_team: str,
    away_team: str,
) -> Optional[str]:
    normalized = _normalize_text(selection)
    if not normalized:
        return None
    if normalized in DRAW_ALIASES:
        return "X"
    if normalized == _normalize_text(home_team):
        return "1"
    if normalized == _normalize_text(away_team):
        return "2"
    return None


def _trade_action(row: Mapping[str, Any]) -> str:
    action = str(row.get("action") or "").strip().lower()
    if action in {"buy", "sell"}:
        return action
    side = str(row.get("side") or "").strip().lower()
    if side in {"buy", "sell"}:
        return side
    return ""


def _is_direct_yes_buy(row: Mapping[str, Any]) -> bool:
    if str(row.get("market_type") or "").strip().lower() != "1x2":
        return False
    if _trade_action(row) != "buy":
        return False
    outcome = str(row.get("outcome_raw") or "").strip().lower()
    return outcome == "yes"


def _direct_buy_totals(
    rows: Iterable[Mapping[str, Any]],
    *,
    home_team: str,
    away_team: str,
    min_trade_usdc: float = 0.0,
) -> Tuple[Dict[str, float], int]:
    totals = {"1": 0.0, "X": 0.0, "2": 0.0}
    accepted = 0
    for row in rows:
        if not _is_direct_yes_buy(row):
            continue
        amount = _number(row.get("amount_usdc"))
        if amount is None or amount < min_trade_usdc:
            continue
        direction = _selection_direction(
            row.get("selection"),
            home_team=home_team,
            away_team=away_team,
        )
        if direction is None:
            continue
        totals[direction] += amount
        accepted += 1
    return totals, accepted


def _leader(totals: Mapping[str, float]) -> Tuple[Optional[str], float, float]:
    ranked = sorted(
        ((direction, float(amount or 0.0)) for direction, amount in totals.items()),
        key=lambda item: item[1],
        reverse=True,
    )
    if not ranked or ranked[0][1] <= 0:
        return None, 0.0, 0.0
    lead_direction, lead_amount = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0.0
    return lead_direction, lead_amount, runner_up


def evaluate_general_poly_direction(
    target_direction: str,
    trades: Iterable[Mapping[str, Any]],
    *,
    home_team: str,
    away_team: str,
    config: Optional[PolyConfirmationConfig] = None,
) -> Dict[str, Any]:
    cfg = config or PolyConfirmationConfig()
    target = normalize_direction(target_direction)
    totals, trade_count = _direct_buy_totals(
        trades,
        home_team=home_team,
        away_team=away_team,
    )
    total = sum(totals.values())
    leader, lead_amount, runner_up = _leader(totals)

    if total < cfg.general_min_volume_usdc or leader is None:
        state = COMPONENT_UNAVAILABLE if total <= 0 else COMPONENT_NEUTRAL
        return {
            "component": "GENERAL_DIRECTION",
            "state": state,
            "reason_codes": ["INSUFFICIENT_POLY_1X2_VOLUME"],
            "direct_buy_volume_usdc": totals,
            "total_direct_buy_volume_usdc": total,
            "trade_count": trade_count,
            "leader": leader,
            "leader_share_pct": None,
            "leader_margin_pct": None,
        }

    lead_share = lead_amount / total * 100.0
    runner_share = runner_up / total * 100.0
    margin = lead_share - runner_share
    clear = (
        lead_share >= cfg.general_lead_share_pct
        and margin >= cfg.general_min_margin_pct
    )

    if not clear:
        state = COMPONENT_NEUTRAL
        reasons = ["POLY_DIRECTION_NOT_DECISIVE"]
    elif leader == target:
        state = COMPONENT_SUPPORT
        reasons = ["GENERAL_POLY_DIRECTION_SUPPORTS"]
    else:
        state = COMPONENT_CONFLICT
        reasons = ["GENERAL_POLY_DIRECTION_OPPOSES"]

    return {
        "component": "GENERAL_DIRECTION",
        "state": state,
        "reason_codes": reasons,
        "direct_buy_volume_usdc": totals,
        "total_direct_buy_volume_usdc": total,
        "trade_count": trade_count,
        "leader": leader,
        "leader_share_pct": round(lead_share, 4),
        "leader_margin_pct": round(margin, 4),
    }


def evaluate_big_trades(
    target_direction: str,
    trades: Iterable[Mapping[str, Any]],
    *,
    home_team: str,
    away_team: str,
    config: Optional[PolyConfirmationConfig] = None,
) -> Dict[str, Any]:
    cfg = config or PolyConfirmationConfig()
    target = normalize_direction(target_direction)
    totals, trade_count = _direct_buy_totals(
        trades,
        home_team=home_team,
        away_team=away_team,
        min_trade_usdc=cfg.big_trade_min_usdc,
    )
    leader, lead_amount, runner_up = _leader(totals)

    if trade_count == 0 or leader is None:
        return {
            "component": "BIG_TRADES",
            "state": COMPONENT_UNAVAILABLE,
            "reason_codes": ["NO_QUALIFYING_BIG_TRADES"],
            "big_trade_volume_usdc": totals,
            "qualifying_trade_count": 0,
            "leader": None,
            "net_margin_usdc": None,
        }

    margin = lead_amount - runner_up
    if margin < cfg.big_trade_min_net_margin_usdc:
        state = COMPONENT_NEUTRAL
        reasons = ["BIG_TRADES_MIXED"]
    elif leader == target:
        state = COMPONENT_SUPPORT
        reasons = ["BIG_TRADES_SUPPORT"]
    else:
        state = COMPONENT_CONFLICT
        reasons = ["BIG_TRADES_OPPOSE"]

    return {
        "component": "BIG_TRADES",
        "state": state,
        "reason_codes": reasons,
        "big_trade_volume_usdc": totals,
        "qualifying_trade_count": trade_count,
        "leader": leader,
        "net_margin_usdc": round(margin, 2),
    }


def _qualified_wallets(
    wallet_stats: Iterable[Mapping[str, Any]],
    config: PolyConfirmationConfig,
) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for row in wallet_stats:
        wallet = str(row.get("wallet") or "").strip().lower()
        if not wallet:
            continue
        win_rate = _number(
            row.get("win_rate_pct")
            if row.get("win_rate_pct") is not None
            else row.get("win_rate")
        )
        resolved = int(_number(row.get("resolved_total")) or 0)
        if (
            win_rate is None
            or win_rate < config.successful_wallet_min_win_rate_pct
            or resolved < config.successful_wallet_min_resolved_bets
        ):
            continue
        result[wallet] = {
            "win_rate_pct": win_rate,
            "resolved_total": resolved,
        }
    return result


def evaluate_successful_wallet_consensus(
    target_direction: str,
    wallet_activity: Iterable[Mapping[str, Any]],
    wallet_stats: Iterable[Mapping[str, Any]],
    *,
    home_team: str,
    away_team: str,
    config: Optional[PolyConfirmationConfig] = None,
) -> Dict[str, Any]:
    cfg = config or PolyConfirmationConfig()
    target = normalize_direction(target_direction)
    qualified = _qualified_wallets(wallet_stats, cfg)

    wallet_totals: Dict[str, Dict[str, float]] = {}
    for row in wallet_activity:
        wallet = str(row.get("wallet") or "").strip().lower()
        if wallet not in qualified or not _is_direct_yes_buy(row):
            continue
        amount = _number(row.get("amount_usdc"))
        if amount is None or amount < cfg.successful_wallet_min_bet_usdc:
            continue
        direction = _selection_direction(
            row.get("selection"),
            home_team=home_team,
            away_team=away_team,
        )
        if direction is None:
            continue
        wallet_totals.setdefault(
            wallet,
            {"1": 0.0, "X": 0.0, "2": 0.0},
        )[direction] += amount

    wallet_votes = {"1": 0, "X": 0, "2": 0}
    wallet_exposure = {"1": 0.0, "X": 0.0, "2": 0.0}
    ambiguous_wallets = 0

    for totals in wallet_totals.values():
        leader, lead_amount, runner_up = _leader(totals)
        if leader is None or lead_amount <= runner_up:
            ambiguous_wallets += 1
            continue
        wallet_votes[leader] += 1
        wallet_exposure[leader] += lead_amount

    voting_wallets = sum(wallet_votes.values())
    leader, lead_votes, runner_votes = _leader(wallet_votes)
    consensus_ratio = (
        lead_votes / voting_wallets if voting_wallets > 0 else 0.0
    )
    decisive = (
        leader is not None
        and lead_votes >= cfg.successful_wallet_min_consensus_wallets
        and consensus_ratio >= cfg.successful_wallet_consensus_ratio
    )

    if voting_wallets == 0:
        state = COMPONENT_UNAVAILABLE
        reasons = ["NO_QUALIFIED_WALLET_ACTIVITY"]
    elif not decisive:
        state = COMPONENT_NEUTRAL
        reasons = ["SUCCESSFUL_WALLETS_NO_CONSENSUS"]
    elif leader == target:
        state = COMPONENT_SUPPORT
        reasons = ["SUCCESSFUL_WALLETS_SUPPORT"]
    else:
        state = COMPONENT_CONFLICT
        reasons = ["SUCCESSFUL_WALLETS_OPPOSE"]

    return {
        "component": "SUCCESSFUL_WALLET_CONSENSUS",
        "state": state,
        "reason_codes": reasons,
        "qualified_wallet_count": len(qualified),
        "active_qualified_wallet_count": len(wallet_totals),
        "voting_wallet_count": voting_wallets,
        "ambiguous_wallet_count": ambiguous_wallets,
        "wallet_votes": wallet_votes,
        "wallet_exposure_usdc": wallet_exposure,
        "leader": leader,
        "leader_vote_count": int(lead_votes),
        "consensus_ratio": round(consensus_ratio, 4),
    }


def evaluate_poly_confirmation(
    target_direction: str,
    *,
    home_team: str,
    away_team: str,
    general_trades: Iterable[Mapping[str, Any]],
    wallet_activity: Iterable[Mapping[str, Any]] = (),
    wallet_stats: Iterable[Mapping[str, Any]] = (),
    config: Optional[PolyConfirmationConfig] = None,
) -> Dict[str, Any]:
    cfg = config or PolyConfirmationConfig()
    target = normalize_direction(target_direction)

    general = evaluate_general_poly_direction(
        target,
        general_trades,
        home_team=home_team,
        away_team=away_team,
        config=cfg,
    )
    big = evaluate_big_trades(
        target,
        general_trades,
        home_team=home_team,
        away_team=away_team,
        config=cfg,
    )
    wallets = evaluate_successful_wallet_consensus(
        target,
        wallet_activity,
        wallet_stats,
        home_team=home_team,
        away_team=away_team,
        config=cfg,
    )

    components = {
        "general_direction": general,
        "big_trades": big,
        "successful_wallet_consensus": wallets,
    }
    support = [
        key for key, item in components.items()
        if item["state"] == COMPONENT_SUPPORT
    ]
    conflict = [
        key for key, item in components.items()
        if item["state"] == COMPONENT_CONFLICT
    ]
    unavailable = [
        key for key, item in components.items()
        if item["state"] == COMPONENT_UNAVAILABLE
    ]

    if len(unavailable) == len(components):
        status = "POLY_UNAVAILABLE"
        reasons = ["NO_POLY_EVIDENCE"]
    elif support and conflict:
        status = "POLY_MIXED"
        reasons = ["POLY_COMPONENTS_DISAGREE"]
    elif len(support) >= cfg.final_min_component_confirmations:
        status = "POLY_CONFIRMED"
        reasons = ["MULTI_COMPONENT_POLY_SUPPORT"]
    elif len(conflict) >= cfg.final_min_component_conflicts:
        status = "POLY_CONFLICT"
        reasons = ["MULTI_COMPONENT_POLY_CONFLICT"]
    else:
        status = "POLY_NEUTRAL"
        reasons = ["POLY_NOT_DECISIVE"]

    risk_flags = []
    if conflict:
        risk_flags.append("POLY_OPPOSING_EVIDENCE")
    if status == "POLY_MIXED":
        risk_flags.append("POLY_INTERNAL_DISAGREEMENT")

    return {
        "poly_confirmation_version": POLY_CONFIRMATION_VERSION,
        "direction": target,
        "status": status,
        "reason_codes": reasons,
        "risk_flags": risk_flags,
        "supporting_components": support,
        "conflicting_components": conflict,
        "unavailable_components": unavailable,
        "components": components,
        "config_snapshot": asdict(cfg),
    }


def apply_poly_to_trigger(
    trigger_payload: Mapping[str, Any],
    poly_result: Mapping[str, Any],
) -> Dict[str, Any]:
    """Persist Poly evidence without changing the primary recommendation."""
    payload = dict(trigger_payload)
    poly = dict(poly_result)

    engine_reason = dict(payload.get("engine_reason") or {})
    engine_reason["poly_confirmation"] = {
        "status": poly.get("status"),
        "reason_codes": list(poly.get("reason_codes") or []),
        "risk_flags": list(poly.get("risk_flags") or []),
        "supporting_components": list(
            poly.get("supporting_components") or []
        ),
        "conflicting_components": list(
            poly.get("conflicting_components") or []
        ),
    }
    payload["engine_reason"] = engine_reason

    config_snapshot = dict(payload.get("config_snapshot") or {})
    config_snapshot["poly_confirmation"] = dict(
        poly.get("config_snapshot") or {}
    )
    payload["config_snapshot"] = config_snapshot

    features = dict(payload.get("features") or {})
    features["poly_confirmation"] = {
        "poly_confirmation_version": poly.get(
            "poly_confirmation_version"
        ),
        "status": poly.get("status"),
        "components": poly.get("components") or {},
    }
    payload["features"] = features
    return payload


class PolyConfirmationClient:
    """Read existing Polymarket/tracked-wallet tables by exact event_id."""

    def __init__(
        self,
        supabase_url: Optional[str] = None,
        read_key: Optional[str] = None,
        *,
        session=None,
        timeout: int = 20,
        page_size: int = 1000,
        max_pages: int = 20,
    ):
        self.url = (
            supabase_url or os.environ.get("SUPABASE_URL", "")
        ).rstrip("/")
        self.key = (
            read_key
            or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
            or os.environ.get("SUPABASE_ANON_KEY", "")
        )
        self.session = session or requests
        self.timeout = int(timeout)
        self.page_size = int(page_size)
        self.max_pages = int(max_pages)
        if not self.url or not self.key:
            raise ValueError(
                "SUPABASE_URL and a read key are required"
            )

    def _headers(self) -> Dict[str, str]:
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }

    def _get(
        self,
        table: str,
        params: Mapping[str, Any],
        *,
        range_start: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        headers = self._headers()
        if range_start is not None:
            headers["Range"] = (
                f"{range_start}-"
                f"{range_start + self.page_size - 1}"
            )
        response = self.session.get(
            f"{self.url}/rest/v1/{table}",
            headers=headers,
            params=dict(params),
            timeout=self.timeout,
        )
        if response.status_code not in (200, 206):
            raise RuntimeError(
                f"{table} read failed: HTTP {response.status_code} "
                f"{(response.text or '')[:300]}"
            )
        data = response.json()
        return data if isinstance(data, list) else []

    def _get_all(
        self,
        table: str,
        params: Mapping[str, Any],
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for page in range(self.max_pages):
            chunk = self._get(
                table,
                params,
                range_start=page * self.page_size,
            )
            rows.extend(chunk)
            if len(chunk) < self.page_size:
                return rows
        raise RuntimeError(
            f"{table} pagination limit reached"
        )

    def fetch_event_payload(
        self,
        event_id: str,
        *,
        as_of: Any,
    ) -> Dict[str, Any]:
        event_id = str(event_id or "").strip()
        if not event_id:
            raise ValueError("exact Polymarket event_id is required")
        cutoff = _timestamp(as_of)

        match_rows = self._get(
            "polymarket_matches",
            {
                "select": "event_id,slug,home,away,kickoff_utc",
                "event_id": f"eq.{event_id}",
                "limit": "1",
            },
        )
        if not match_rows:
            return {
                "found": False,
                "event_id": event_id,
                "as_of": _iso(cutoff),
                "data_cutoff": _iso(cutoff),
                "match": None,
                "general_trades": [],
                "wallet_activity": [],
                "wallet_stats": [],
            }

        match = match_rows[0]
        effective_cutoff = cutoff
        kickoff_raw = match.get("kickoff_utc")
        if kickoff_raw:
            try:
                kickoff = _timestamp(kickoff_raw)
                if kickoff < effective_cutoff:
                    effective_cutoff = kickoff
            except ValueError:
                pass
        cutoff_iso = _iso(effective_cutoff)

        general_trades = self._get_all(
            "polymarket_trades",
            {
                "select": (
                    "wallet,market_type,selection,side,outcome_raw,"
                    "amount_usdc,price,traded_at"
                ),
                "event_id": f"eq.{event_id}",
                "match_phase": "eq.prematch",
                "market_type": "eq.1x2",
                "traded_at": f"lte.{cutoff_iso}",
                "order": "traded_at.asc,id.asc",
            },
        )

        wallet_activity = self._get_all(
            "tracked_wallet_activity",
            {
                "select": (
                    "wallet,market_type,selection,side,action,outcome_raw,"
                    "amount_usdc,price,traded_at"
                ),
                "event_id": f"eq.{event_id}",
                "market_type": "eq.1x2",
                "traded_at": f"lte.{cutoff_iso}",
                "order": "traded_at.asc,id.asc",
            },
        )

        wallet_stats = self._get_all(
            "tracked_wallets",
            {
                "select": (
                    "wallet,win_rate,resolved_total,last_synced_at"
                ),
                "last_synced_at": f"lte.{cutoff_iso}",
                "order": "created_at.asc",
            },
        )

        return {
            "found": True,
            "event_id": event_id,
            "as_of": _iso(cutoff),
            "data_cutoff": cutoff_iso,
            "match": match,
            "general_trades": general_trades,
            "wallet_activity": wallet_activity,
            "wallet_stats": wallet_stats,
        }

    def evaluate(
        self,
        *,
        event_id: str,
        target_direction: str,
        as_of: Any,
        config: Optional[PolyConfirmationConfig] = None,
    ) -> Dict[str, Any]:
        payload = self.fetch_event_payload(event_id, as_of=as_of)
        if not payload["found"]:
            return {
                "poly_confirmation_version": POLY_CONFIRMATION_VERSION,
                "direction": normalize_direction(target_direction),
                "status": "POLY_UNAVAILABLE",
                "reason_codes": ["POLY_EVENT_NOT_FOUND"],
                "risk_flags": [],
                "supporting_components": [],
                "conflicting_components": [],
                "unavailable_components": [
                    "general_direction",
                    "big_trades",
                    "successful_wallet_consensus",
                ],
                "components": {},
                "config_snapshot": asdict(
                    config or PolyConfirmationConfig()
                ),
                "poly_event_id": str(event_id),
                "as_of": payload.get("as_of"),
                "data_cutoff": payload.get("data_cutoff"),
            }

        match = payload["match"]
        result = evaluate_poly_confirmation(
            target_direction,
            home_team=str(match.get("home") or ""),
            away_team=str(match.get("away") or ""),
            general_trades=payload["general_trades"],
            wallet_activity=payload["wallet_activity"],
            wallet_stats=payload["wallet_stats"],
            config=config,
        )
        result["poly_event_id"] = str(event_id)
        result["poly_slug"] = match.get("slug")
        result["as_of"] = payload.get("as_of")
        result["data_cutoff"] = payload.get("data_cutoff")
        return result
