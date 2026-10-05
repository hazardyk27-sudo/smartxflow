from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Iterable

import requests

from .settlement import SettlementError, normalize_score


class ResultSourceError(RuntimeError):
    pass


@dataclass(frozen=True)
class MatchResult:
    match_id_hash: str
    final_score: str
    status: str
    observed_at: str
    source: str = "SmartXFlow live_fixtures"


def _config() -> tuple[str, str]:
    url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        or os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
        or os.environ.get("SUPABASE_KEY", "").strip()
    )
    if not url or not key:
        raise ResultSourceError("SUPABASE_URL and a service-role credential are required for result lookup")
    return url, key


def _session() -> requests.Session:
    _, key = _config()
    session = requests.Session()
    session.headers.update({
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
        "User-Agent": "smartxflow-learning-archive-settlement",
    })
    return session


def _normalize_hashes(match_id_hashes: Iterable[str]) -> list[str]:
    hashes: list[str] = []
    seen: set[str] = set()
    for value in match_id_hashes:
        match_hash = str(value or "").strip().lower()
        if not match_hash:
            raise ResultSourceError("match_id_hash is required")
        if match_hash not in seen:
            hashes.append(match_hash)
            seen.add(match_hash)
    return hashes


def _result_from_row(row: dict[str, Any], match_hash: str) -> MatchResult | None:
    status = str(row.get("status") or "").strip().lower()
    minute = str(row.get("minute") or "").strip().upper()
    if status not in {"ft", "finished", "fulltime", "full_time"} and minute != "FT":
        return None
    observed_at = str(row.get("updated_at") or "").strip()
    if not observed_at:
        raise ResultSourceError(f"finished live_fixtures row is missing updated_at for {match_hash}")
    try:
        score = normalize_score(str(row.get("score") or ""))
    except SettlementError as exc:
        raise ResultSourceError(f"finished live_fixtures row has invalid score for {match_hash}: {exc}") from exc
    return MatchResult(
        match_id_hash=match_hash,
        final_score=score,
        status="ft",
        observed_at=observed_at,
    )


def fetch_finished_results(
    match_id_hashes: Iterable[str],
    *,
    session: requests.Session | None = None,
) -> dict[str, MatchResult | None]:
    """Fetch many finished results with one Supabase REST request.

    The return mapping includes every requested hash. Missing or not-yet-finished
    fixtures map to ``None``. Duplicate live rows fail closed.
    """
    hashes = _normalize_hashes(match_id_hashes)
    if not hashes:
        return {}

    url, _ = _config()
    sess = session or _session()
    response = sess.get(
        f"{url}/rest/v1/live_fixtures",
        params={
            "select": "match_id_hash,score,status,minute,updated_at",
            "match_id_hash": f"in.({','.join(hashes)})",
            "limit": str(max(2, len(hashes) * 2)),
        },
        timeout=20,
    )
    if response.status_code != 200:
        raise ResultSourceError(f"live_fixtures batch result lookup failed ({response.status_code})")
    payload: Any = response.json()
    if not isinstance(payload, list):
        raise ResultSourceError("live_fixtures batch result lookup returned invalid payload")

    rows_by_hash: dict[str, list[dict[str, Any]]] = {match_hash: [] for match_hash in hashes}
    for row in payload:
        if not isinstance(row, dict):
            raise ResultSourceError("live_fixtures result row is invalid")
        row_hash = str(row.get("match_id_hash") or "").strip().lower()
        if row_hash not in rows_by_hash:
            raise ResultSourceError(f"live_fixtures returned unexpected match_id_hash {row_hash!r}")
        rows_by_hash[row_hash].append(row)

    results: dict[str, MatchResult | None] = {}
    for match_hash in hashes:
        rows = rows_by_hash[match_hash]
        if len(rows) > 1:
            raise ResultSourceError(f"live_fixtures returned duplicate rows for {match_hash}")
        results[match_hash] = None if not rows else _result_from_row(rows[0], match_hash)
    return results


def fetch_finished_result(match_id_hash: str, *, session: requests.Session | None = None) -> MatchResult | None:
    match_hash = str(match_id_hash or "").strip().lower()
    return fetch_finished_results([match_hash], session=session)[match_hash]
