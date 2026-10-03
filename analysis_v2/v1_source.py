"""Read-only adapters from existing Analyses V1 signal tables into V2.

The new V2 does not discover matches here. It reads triggers already produced by
V1 engines and converts them to the engine-first candidate contract. The old
Confirmed Money V2 table is deliberately excluded because its historical rule
performed worse than Confirmed Money V1 and must not be treated as a trusted
source engine.

This module performs GET requests only. It never writes, updates or deletes V1
signals.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional
from urllib.parse import quote

import requests

from core.hash_utils import make_match_id_hash
from .engine_first import (
    EngineCandidate,
    candidate_from_v1_signal,
    canonical_engine_key,
)


V1_SOURCE_VERSION = "analysis-v2-v1-source-1.0.0"

V1_TABLES = {
    "underdog_pressure_v1": "underdog_signals",
    "confirmed_money_v1": "confirmed_money_signals",
    "early_money_lock_v1": "early_money_lock_signals",
    "price_money_divergence_v1": "fake_sharp_signals",
}


@dataclass(frozen=True)
class SourceBatch:
    source_engine: str
    table: str
    row_count: int
    candidate_count: int
    skipped_count: int
    candidates: List[EngineCandidate]
    errors: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "v1_source_version": V1_SOURCE_VERSION,
            "source_engine": self.source_engine,
            "table": self.table,
            "row_count": self.row_count,
            "candidate_count": self.candidate_count,
            "skipped_count": self.skipped_count,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "errors": list(self.errors),
        }


def canonical_match_hash(row: Mapping[str, Any]) -> str:
    existing = str(row.get("match_id_hash") or "").strip().lower()
    if len(existing) == 12 and all(ch in "0123456789abcdef" for ch in existing):
        return existing

    home = str(row.get("home_team") or row.get("home") or "").strip()
    away = str(row.get("away_team") or row.get("away") or "").strip()
    league = str(row.get("league") or "").strip()
    if not home or not away or not league:
        return ""
    return make_match_id_hash(home, away, league)


def normalize_v1_row(engine_key: str, row: Mapping[str, Any]) -> Dict[str, Any]:
    canonical = canonical_engine_key(engine_key)
    payload = dict(row)
    payload["match_id_hash"] = canonical_match_hash(payload)
    payload["source_engine"] = canonical

    if canonical == "underdog_pressure_v1":
        payload.setdefault("trigger_odds", payload.get("odds"))
        payload.setdefault("trigger_pct", payload.get("pct"))
        payload.setdefault("trigger_amount", payload.get("amt"))
        payload.setdefault("trigger_volume", payload.get("volume"))
    elif canonical == "confirmed_money_v1":
        payload.setdefault("trigger_odds", payload.get("odds_now"))
        payload.setdefault("trigger_pct", payload.get("pct_now"))
        payload.setdefault("trigger_amount", payload.get("amt_now"))
        payload.setdefault("trigger_volume", payload.get("volume_now"))
    elif canonical == "early_money_lock_v1":
        # Historical EML rows do not reliably contain trigger odds. Do not
        # invent an odds value from current state; persistence_gate will mark
        # such rows incomplete until a real trigger price is available.
        payload.setdefault("trigger_pct", payload.get("pct_now"))
        payload.setdefault("trigger_amount", payload.get("amt_now"))
        payload.setdefault("trigger_volume", payload.get("volume_now"))
    elif canonical == "price_money_divergence_v1":
        payload.setdefault("trigger_odds", payload.get("odds_now"))
        payload.setdefault("trigger_pct", payload.get("pct_now"))
        payload.setdefault("trigger_amount", payload.get("amt_now"))
        payload.setdefault("trigger_volume", payload.get("volume_now"))

    return payload


class V1SignalSource:
    """Read-only PostgREST source for existing V1 signal tables."""

    def __init__(
        self,
        supabase_url: str,
        supabase_key: str,
        *,
        session: Optional[Any] = None,
        timeout_seconds: float = 12.0,
    ):
        self.supabase_url = str(supabase_url or "").rstrip("/")
        self.supabase_key = str(supabase_key or "")
        self.session = session or requests.Session()
        self.timeout_seconds = float(timeout_seconds)

    @property
    def available(self) -> bool:
        return bool(self.supabase_url and self.supabase_key)

    def _headers(self) -> Dict[str, str]:
        return {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Accept": "application/json",
        }

    def fetch_rows(
        self,
        engine_key: str,
        *,
        since: Optional[str] = None,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        if not self.available:
            raise RuntimeError("V1_SOURCE_UNAVAILABLE")

        canonical = canonical_engine_key(engine_key)
        table = V1_TABLES[canonical]
        safe_limit = max(1, min(int(limit), 5000))
        params = ["select=*", "order=created_at.desc", f"limit={safe_limit}"]
        if since:
            params.append(f"created_at=gte.{quote(str(since), safe=':+-TZ.')}")
        url = f"{self.supabase_url}/rest/v1/{table}?{'&'.join(params)}"
        response = self.session.get(
            url,
            headers=self._headers(),
            timeout=self.timeout_seconds,
        )
        if response.status_code != 200:
            raise RuntimeError(f"V1_SOURCE_HTTP_{response.status_code}:{table}")
        data = response.json()
        if not isinstance(data, list):
            raise RuntimeError(f"V1_SOURCE_INVALID_PAYLOAD:{table}")
        return [dict(row) for row in data if isinstance(row, Mapping)]

    def fetch_candidates(
        self,
        engine_key: str,
        *,
        since: Optional[str] = None,
        limit: int = 500,
        engine_version: str = "v1-legacy",
    ) -> SourceBatch:
        canonical = canonical_engine_key(engine_key)
        table = V1_TABLES[canonical]
        rows = self.fetch_rows(canonical, since=since, limit=limit)
        candidates: List[EngineCandidate] = []
        errors: List[str] = []

        for row in rows:
            normalized = normalize_v1_row(canonical, row)
            try:
                candidate = candidate_from_v1_signal(
                    canonical,
                    normalized,
                    match_id_hash=normalized.get("match_id_hash"),
                    engine_version=engine_version,
                )
                candidates.append(candidate)
            except Exception as exc:
                row_id = str(row.get("id") or "unknown")
                errors.append(f"{row_id}:{type(exc).__name__}:{exc}")

        return SourceBatch(
            source_engine=canonical,
            table=table,
            row_count=len(rows),
            candidate_count=len(candidates),
            skipped_count=len(rows) - len(candidates),
            candidates=candidates,
            errors=errors,
        )


def fetch_all_v1_candidates(
    source: V1SignalSource,
    *,
    since: Optional[str] = None,
    limit_per_engine: int = 500,
) -> Dict[str, SourceBatch]:
    """Load each supported V1 engine independently; failure stays isolated."""

    result: Dict[str, SourceBatch] = {}
    for engine_key, table in V1_TABLES.items():
        try:
            result[engine_key] = source.fetch_candidates(
                engine_key,
                since=since,
                limit=limit_per_engine,
            )
        except Exception as exc:
            result[engine_key] = SourceBatch(
                source_engine=engine_key,
                table=table,
                row_count=0,
                candidate_count=0,
                skipped_count=0,
                candidates=[],
                errors=[f"{type(exc).__name__}:{exc}"],
            )
    return result
