"""Analysis V2 Part 9: reproducible backtest laboratory.

The lab consumes immutable trigger/settlement rows. It never relabels old
signals or deletes failures. Closing prices are used only for post-trigger CLV.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from statistics import median
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import requests

from .entry_price import flat_stake_pnl_units, resolve_entry_odds_with_source


BACKTEST_LAB_VERSION = "analysis-v2-part9-1.0.0"
VALID_OUTCOMES = {"WIN", "LOSS", "PUSH", "VOID", "UNKNOWN"}
STAKE_OUTCOMES = {"WIN", "LOSS", "PUSH"}
COMPONENT_NAMES = (
    "price_confirmation",
    "money_flow",
    "timing",
    "cross_market",
    "poly",
    "risk",
)


@dataclass(frozen=True)
class BacktestConfig:
    small_sample_n: int = 30
    closing_line_max_age_minutes: int = 180


def _number(value: Any) -> Optional[float]:
    if value in (None, "", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _timestamp(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(
                str(value).strip().replace("Z", "+00:00")
            )
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _json_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _user_state(row: Mapping[str, Any]) -> str:
    features = _json_dict(row.get("features"))
    confidence = _json_dict(features.get("explainable_confidence"))
    state = confidence.get("user_state")
    if state:
        return str(state).upper()
    reason = _json_dict(row.get("engine_reason"))
    confidence_reason = _json_dict(reason.get("explainable_confidence"))
    return str(
        confidence_reason.get("user_state") or "UNKNOWN"
    ).upper()


def _primary_class(row: Mapping[str, Any]) -> str:
    reason = _json_dict(row.get("engine_reason"))
    if reason.get("primary_class"):
        return str(reason["primary_class"]).upper()
    features = _json_dict(row.get("features"))
    classification = _json_dict(features.get("classification"))
    return str(
        classification.get("primary_class") or "UNKNOWN"
    ).upper()


def _component_levels(row: Mapping[str, Any]) -> Dict[str, str]:
    features = _json_dict(row.get("features"))
    confidence = _json_dict(features.get("explainable_confidence"))
    components = _json_dict(confidence.get("components"))
    return {
        name: str(
            _json_dict(components.get(name)).get("level")
            or "UNKNOWN"
        ).upper()
        for name in COMPONENT_NAMES
    }


def _config_fingerprint(row: Mapping[str, Any]) -> str:
    payload = _json_dict(row.get("config_snapshot"))
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()[:12]


def _clv_pct(
    entry_odds: Optional[float],
    closing_odds: Optional[float],
) -> Optional[float]:
    if (
        entry_odds is None
        or closing_odds is None
        or entry_odds <= 1
        or closing_odds <= 1
    ):
        return None
    return (
        entry_odds / closing_odds - 1.0
    ) * 100.0


def prepare_backtest_records(
    rows: Iterable[Mapping[str, Any]],
    *,
    closing_odds_by_signal: Optional[Mapping[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Normalize immutable ledger rows without trusting bad legacy prices."""
    closing_map = dict(closing_odds_by_signal or {})
    records: List[Dict[str, Any]] = []

    for raw in rows:
        row = dict(raw)
        signal_id = str(row.get("signal_id") or "").strip()
        outcome = str(
            row.get("outcome") or ""
        ).strip().upper()
        if not signal_id or outcome not in VALID_OUTCOMES:
            continue

        expected_entry, expected_source = (
            resolve_entry_odds_with_source(row)
        )
        settlement_entry = _number(row.get("entry_odds"))
        price_mismatch = (
            settlement_entry is not None
            and (
                expected_entry is None
                or not math.isclose(
                    settlement_entry,
                    expected_entry,
                    rel_tol=1e-12,
                    abs_tol=1e-12,
                )
            )
        )
        entry_odds = (
            settlement_entry
            if settlement_entry is not None
            and not price_mismatch
            else expected_entry
        )
        entry_source = (
            "settlement_entry_odds"
            if settlement_entry is not None
            and not price_mismatch
            else expected_source
        )

        pnl = _number(row.get("pnl_units"))
        calculated = flat_stake_pnl_units(entry_odds, outcome)
        pnl_mismatch = (
            price_mismatch
            or (
                pnl is not None
                and calculated is not None
                and not math.isclose(
                    pnl,
                    calculated,
                    rel_tol=1e-9,
                    abs_tol=1e-9,
                )
            )
        )
        if price_mismatch or pnl is None or pnl_mismatch:
            pnl = calculated

        close = _number(
            closing_map.get(
                signal_id,
                row.get("closing_odds"),
            )
        )
        market = str(
            row.get("recommended_market")
            or row.get("market_key")
            or ""
        ).strip().upper()
        selection = str(
            row.get("recommended_selection")
            or row.get("selection_code")
            or ""
        ).strip().upper()

        quality_flags = []
        if expected_entry is None:
            quality_flags.append("ENTRY_ODDS_MISSING")
        if price_mismatch:
            quality_flags.append(
                "SETTLEMENT_ENTRY_ODDS_MISMATCH"
            )
        if pnl_mismatch:
            quality_flags.append(
                "SETTLEMENT_PNL_MISMATCH"
            )

        records.append(
            {
                **row,
                "signal_id": signal_id,
                "outcome": outcome,
                "backtest_entry_odds": entry_odds,
                "backtest_entry_odds_source": entry_source,
                "backtest_pnl_units": pnl,
                "closing_odds": close,
                "clv_pct": _clv_pct(
                    entry_odds,
                    close,
                ),
                "recommended_market": market,
                "recommended_selection": selection,
                "user_state": _user_state(row),
                "primary_class": _primary_class(row),
                "component_levels": _component_levels(row),
                "config_fingerprint": _config_fingerprint(row),
                "quality_flags": quality_flags,
                "_settled_dt": _timestamp(
                    row.get("settled_at")
                ),
                "_trigger_dt": _timestamp(
                    row.get("trigger_at")
                ),
            }
        )

    return records


def _max_drawdown(
    records: Sequence[Mapping[str, Any]],
) -> Tuple[float, float]:
    minimum = datetime.min.replace(
        tzinfo=timezone.utc
    )
    ordered = sorted(
        records,
        key=lambda row: (
            row.get("_settled_dt")
            or row.get("_trigger_dt")
            or minimum,
            row.get("_trigger_dt") or minimum,
            str(row.get("signal_id") or ""),
        ),
    )
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for row in ordered:
        pnl = _number(
            row.get("backtest_pnl_units")
        )
        if (
            pnl is None
            or row.get("outcome") not in STAKE_OUTCOMES
        ):
            continue
        equity += pnl
        peak = max(peak, equity)
        max_drawdown = max(
            max_drawdown,
            peak - equity,
        )
    return max_drawdown, equity


def calculate_metrics(
    records: Sequence[Mapping[str, Any]],
    *,
    config: Optional[BacktestConfig] = None,
) -> Dict[str, Any]:
    cfg = config or BacktestConfig()
    rows = list(records)

    wins = sum(
        1 for row in rows
        if row.get("outcome") == "WIN"
    )
    losses = sum(
        1 for row in rows
        if row.get("outcome") == "LOSS"
    )
    pushes = sum(
        1 for row in rows
        if row.get("outcome") == "PUSH"
    )
    voids = sum(
        1 for row in rows
        if row.get("outcome") == "VOID"
    )
    unknown = sum(
        1 for row in rows
        if row.get("outcome") == "UNKNOWN"
    )

    resolved = wins + losses
    stake_rows = [
        row
        for row in rows
        if (
            row.get("outcome") in STAKE_OUTCOMES
            and _number(
                row.get("backtest_pnl_units")
            ) is not None
        )
    ]
    priced_rows = [
        row
        for row in stake_rows
        if _number(
            row.get("backtest_entry_odds")
        ) is not None
    ]

    profit = sum(
        float(row["backtest_pnl_units"])
        for row in stake_rows
    )
    stake_units = float(len(stake_rows))
    hit_rate = (
        wins / resolved * 100.0
        if resolved
        else None
    )
    avg_odds = (
        sum(
            float(row["backtest_entry_odds"])
            for row in priced_rows
        )
        / len(priced_rows)
        if priced_rows
        else None
    )
    roi = (
        profit / stake_units * 100.0
        if stake_units
        else None
    )

    max_drawdown, ending_equity = (
        _max_drawdown(rows)
    )

    clv_values = [
        float(row["clv_pct"])
        for row in rows
        if _number(row.get("clv_pct"))
        is not None
    ]
    avg_clv = (
        sum(clv_values) / len(clv_values)
        if clv_values
        else None
    )
    median_clv = (
        median(clv_values)
        if clv_values
        else None
    )
    positive_clv = (
        sum(
            1 for value in clv_values
            if value > 0
        )
        / len(clv_values)
        * 100.0
        if clv_values
        else None
    )

    implied_rows = [
        row
        for row in rows
        if (
            row.get("outcome")
            in {"WIN", "LOSS"}
            and row.get("recommended_market")
            != "DNB"
            and _number(
                row.get("backtest_entry_odds")
            ) is not None
        )
    ]
    avg_implied = None
    implied_hit = None
    implied_gap = None
    if implied_rows:
        avg_implied = (
            sum(
                1.0
                / float(
                    row["backtest_entry_odds"]
                )
                for row in implied_rows
            )
            / len(implied_rows)
            * 100.0
        )
        implied_hit = (
            sum(
                1 for row in implied_rows
                if row.get("outcome") == "WIN"
            )
            / len(implied_rows)
            * 100.0
        )
        implied_gap = (
            implied_hit - avg_implied
        )

    quality: Dict[str, int] = {}
    for row in rows:
        for flag in (
            row.get("quality_flags") or []
        ):
            quality[flag] = (
                quality.get(flag, 0) + 1
            )

    warnings = []
    if len(stake_rows) < cfg.small_sample_n:
        warnings.append("SMALL_SAMPLE")
    for flag in (
        "ENTRY_ODDS_MISSING",
        "SETTLEMENT_ENTRY_ODDS_MISMATCH",
        "SETTLEMENT_PNL_MISMATCH",
    ):
        if quality.get(flag):
            warnings.append(flag)

    return {
        "n_rows": len(rows),
        "n_staked": len(stake_rows),
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "voids": voids,
        "unknown": unknown,
        "hit_rate_pct": hit_rate,
        "avg_odds": avg_odds,
        "profit_units": profit,
        "stake_units": stake_units,
        "roi_pct": roi,
        "max_drawdown_units": max_drawdown,
        "ending_equity_units": ending_equity,
        "clv_n": len(clv_values),
        "avg_clv_pct": avg_clv,
        "median_clv_pct": median_clv,
        "positive_clv_rate_pct": positive_clv,
        "market_implied_calibration": {
            "n": len(implied_rows),
            "avg_market_implied_pct": avg_implied,
            "observed_hit_rate_pct": implied_hit,
            "observed_minus_implied_pp": implied_gap,
            "note": (
                "DNB excluded because pushes make raw "
                "1/odds comparison non-equivalent."
            ),
        },
        "quality_flags": quality,
        "warnings": warnings,
    }


def _group(
    records: Sequence[Mapping[str, Any]],
    key_fn,
    *,
    config: BacktestConfig,
) -> Dict[str, Dict[str, Any]]:
    buckets: Dict[
        str,
        List[Mapping[str, Any]],
    ] = {}
    for row in records:
        key = str(
            key_fn(row) or "UNKNOWN"
        )
        buckets.setdefault(
            key,
            [],
        ).append(row)
    return {
        key: calculate_metrics(
            items,
            config=config,
        )
        for key, items
        in sorted(buckets.items())
    }


def _component_calibration(
    records: Sequence[Mapping[str, Any]],
    *,
    config: BacktestConfig,
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    return {
        component: _group(
            records,
            lambda row, name=component: (
                row.get("component_levels")
                or {}
            ).get(name, "UNKNOWN"),
            config=config,
        )
        for component in COMPONENT_NAMES
    }


def run_backtest(
    rows: Iterable[Mapping[str, Any]],
    *,
    closing_odds_by_signal: Optional[
        Mapping[str, Any]
    ] = None,
    config: Optional[
        BacktestConfig
    ] = None,
) -> Dict[str, Any]:
    """Run the Part 9 report over immutable ledger rows."""
    cfg = config or BacktestConfig()
    records = prepare_backtest_records(
        rows,
        closing_odds_by_signal=(
            closing_odds_by_signal
        ),
    )
    firsat = [
        row
        for row in records
        if row.get("user_state") == "FIRSAT"
    ]

    return {
        "backtest_lab_version": (
            BACKTEST_LAB_VERSION
        ),
        "config_snapshot": asdict(cfg),
        "overall": calculate_metrics(
            records,
            config=cfg,
        ),
        "firsat_only": calculate_metrics(
            firsat,
            config=cfg,
        ),
        "by_user_state": _group(
            records,
            lambda row: row.get(
                "user_state"
            ),
            config=cfg,
        ),
        "by_engine": _group(
            records,
            lambda row: (
                f"{row.get('engine_key','UNKNOWN')}"
                f"@{row.get('engine_version','UNKNOWN')}"
            ),
            config=cfg,
        ),
        "by_market": _group(
            records,
            lambda row: row.get(
                "recommended_market"
            ),
            config=cfg,
        ),
        "by_primary_class": _group(
            records,
            lambda row: row.get(
                "primary_class"
            ),
            config=cfg,
        ),
        "by_config_fingerprint": _group(
            records,
            lambda row: row.get(
                "config_fingerprint"
            ),
            config=cfg,
        ),
        "component_calibration": (
            _component_calibration(
                records,
                config=cfg,
            )
        ),
        "records": records,
    }


def period_report(
    rows: Iterable[Mapping[str, Any]],
    periods: Mapping[
        str,
        Tuple[Any, Any],
    ],
    *,
    closing_odds_by_signal: Optional[
        Mapping[str, Any]
    ] = None,
    config: Optional[
        BacktestConfig
    ] = None,
) -> Dict[str, Dict[str, Any]]:
    """Compare chronological cohorts by immutable trigger time."""
    prepared = prepare_backtest_records(
        rows,
        closing_odds_by_signal=(
            closing_odds_by_signal
        ),
    )
    cfg = config or BacktestConfig()
    output = {}
    for label, (
        start,
        end,
    ) in periods.items():
        start_dt = _timestamp(start)
        end_dt = _timestamp(end)
        cohort = []
        for row in prepared:
            trigger = row.get(
                "_trigger_dt"
            )
            if trigger is None:
                continue
            if (
                start_dt is not None
                and trigger < start_dt
            ):
                continue
            if (
                end_dt is not None
                and trigger >= end_dt
            ):
                continue
            cohort.append(row)
        output[label] = (
            calculate_metrics(
                cohort,
                config=cfg,
            )
        )
    return output


class BacktestDataClient:
    """Read immutable V2 rows and real pre-kickoff closing snapshots."""

    def __init__(
        self,
        supabase_url: Optional[str] = None,
        read_key: Optional[str] = None,
        *,
        session=None,
        timeout: int = 20,
        page_size: int = 1000,
        max_pages: int = 50,
    ):
        self.url = (
            supabase_url
            or os.environ.get(
                "SUPABASE_URL",
                "",
            )
        ).rstrip("/")
        self.key = (
            read_key
            or os.environ.get(
                "SUPABASE_SERVICE_ROLE_KEY"
            )
            or os.environ.get(
                "SUPABASE_ANON_KEY",
                "",
            )
        )
        self.session = session or requests
        self.timeout = int(timeout)
        self.page_size = int(page_size)
        self.max_pages = int(max_pages)
        if not self.url or not self.key:
            raise ValueError(
                "SUPABASE_URL and a read key "
                "are required"
            )

    def _headers(
        self,
        range_start: Optional[int] = None,
    ) -> Dict[str, str]:
        headers = {
            "apikey": self.key,
            "Authorization": (
                f"Bearer {self.key}"
            ),
            "Content-Type": (
                "application/json"
            ),
        }
        if range_start is not None:
            headers["Range"] = (
                f"{range_start}-"
                f"{range_start + self.page_size - 1}"
            )
        return headers

    def _get(
        self,
        table: str,
        params: Mapping[str, Any],
        *,
        range_start: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        response = self.session.get(
            f"{self.url}/rest/v1/{table}",
            headers=self._headers(
                range_start
            ),
            params=dict(params),
            timeout=self.timeout,
        )
        if response.status_code not in (
            200,
            206,
        ):
            raise RuntimeError(
                f"{table} read failed: "
                f"HTTP {response.status_code} "
                f"{(response.text or '')[:300]}"
            )
        data = response.json()
        return (
            data
            if isinstance(data, list)
            else []
        )

    def _get_all(
        self,
        table: str,
        params: Mapping[str, Any],
    ) -> List[Dict[str, Any]]:
        rows = []
        for page in range(
            self.max_pages
        ):
            chunk = self._get(
                table,
                params,
                range_start=(
                    page * self.page_size
                ),
            )
            rows.extend(chunk)
            if len(chunk) < self.page_size:
                return rows
        raise RuntimeError(
            f"{table} pagination "
            "limit reached"
        )

    def fetch_settled_signals(
        self,
        *,
        engine_key: Optional[str] = None,
        engine_version: Optional[
            str
        ] = None,
        trigger_from: Any = None,
        trigger_to: Any = None,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {
            "select": "*",
            "settlement_id": (
                "not.is.null"
            ),
            "order": (
                "trigger_at.asc,id.asc"
            ),
        }
        if engine_key:
            params["engine_key"] = (
                "eq."
                + str(engine_key)
                .strip()
                .lower()
            )
        if engine_version:
            params["engine_version"] = (
                "eq."
                + str(engine_version)
                .strip()
            )

        clauses = []
        start = _timestamp(
            trigger_from
        )
        end = _timestamp(
            trigger_to
        )
        if start:
            clauses.append(
                "trigger_at.gte."
                + _iso(start)
            )
        if end:
            clauses.append(
                "trigger_at.lt."
                + _iso(end)
            )
        if clauses:
            params["and"] = (
                "("
                + ",".join(clauses)
                + ")"
            )

        return self._get_all(
            "analysis_v2_signal_current",
            params,
        )

    def fetch_closing_odds(
        self,
        signal: Mapping[str, Any],
        *,
        max_age_minutes: int = 180,
    ) -> Optional[float]:
        kickoff = _timestamp(
            signal.get("kickoff_utc")
        )
        if kickoff is None:
            return None

        market = str(
            signal.get(
                "recommended_market"
            )
            or signal.get("market_key")
            or ""
        ).strip().upper()
        selection = str(
            signal.get(
                "recommended_selection"
            )
            or signal.get(
                "selection_code"
            )
            or ""
        ).strip().upper()
        match_hash = str(
            signal.get("match_id_hash")
            or ""
        ).strip().lower()

        if (
            not market
            or not selection
            or not match_hash
        ):
            return None

        rows = self._get(
            "moneyway_snapshots",
            {
                "select": (
                    "odds,scraped_at_utc"
                ),
                "match_id_hash": (
                    f"eq.{match_hash}"
                ),
                "market": f"eq.{market}",
                "selection": (
                    f"eq.{selection}"
                ),
                "scraped_at_utc": (
                    f"lt.{_iso(kickoff)}"
                ),
                "order": (
                    "scraped_at_utc.desc,"
                    "id.desc"
                ),
                "limit": "1",
            },
        )
        if not rows:
            return None

        at = _timestamp(
            rows[0].get(
                "scraped_at_utc"
            )
        )
        if at is None:
            return None

        age_minutes = (
            kickoff - at
        ).total_seconds() / 60.0
        if (
            age_minutes < 0
            or age_minutes
            > max_age_minutes
        ):
            return None

        odds = _number(
            rows[0].get("odds")
        )
        return (
            odds
            if odds is not None
            and odds > 1
            else None
        )

    def closing_odds_map(
        self,
        signals: Iterable[
            Mapping[str, Any]
        ],
        *,
        max_age_minutes: int = 180,
    ) -> Dict[str, float]:
        output: Dict[str, float] = {}
        cache: Dict[
            Tuple[str, str, str, str],
            Optional[float],
        ] = {}

        for signal in signals:
            signal_id = str(
                signal.get("signal_id")
                or ""
            )
            kickoff = str(
                signal.get("kickoff_utc")
                or ""
            )
            market = str(
                signal.get(
                    "recommended_market"
                )
                or signal.get(
                    "market_key"
                )
                or ""
            ).strip().upper()
            selection = str(
                signal.get(
                    "recommended_selection"
                )
                or signal.get(
                    "selection_code"
                )
                or ""
            ).strip().upper()
            match_hash = str(
                signal.get(
                    "match_id_hash"
                )
                or ""
            ).strip().lower()
            key = (
                match_hash,
                market,
                selection,
                kickoff,
            )
            if key not in cache:
                cache[key] = (
                    self.fetch_closing_odds(
                        signal,
                        max_age_minutes=(
                            max_age_minutes
                        ),
                    )
                )
            if (
                cache[key] is not None
                and signal_id
            ):
                output[signal_id] = (
                    float(cache[key])
                )
        return output
