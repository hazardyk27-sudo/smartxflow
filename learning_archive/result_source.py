from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any

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


def fetch_finished_result(match_id_hash: str, *, session: requests.Session | None = None) -> MatchResult | None:
    match_hash = str(match_id_hash or "").strip().lower()
    if not match_hash:
        raise ResultSourceError("match_id_hash is required")
    url, _ = _config()
    sess = session or _session()
    response = sess.get(
        f"{url}/rest/v1/live_fixtures",
        params={
            "select": "match_id_hash,score,status,minute,updated_at",
            "match_id_hash": f"eq.{match_hash}",
            "limit": "2",
        },
        timeout=20,
    )
    if response.status_code != 200:
        raise ResultSourceError(f"live_fixtures result lookup failed ({response.status_code})")
    payload: Any = response.json()
    if not isinstance(payload, list):
        raise ResultSourceError("live_fixtures result lookup returned invalid payload")
    if not payload:
        return None
    if len(payload) != 1:
        raise ResultSourceError(f"live_fixtures returned duplicate rows for {match_hash}")
    row = payload[0]
    if not isinstance(row, dict):
        raise ResultSourceError("live_fixtures result row is invalid")
    status = str(row.get("status") or "").strip().lower()
    minute = str(row.get("minute") or "").strip().upper()
    if status not in {"ft", "finished", "fulltime", "full_time"} and minute != "FT":
        return None
    observed_at = str(row.get("updated_at") or "").strip()
    if not observed_at:
        raise ResultSourceError("finished live_fixtures row is missing updated_at")
    try:
        score = normalize_score(str(row.get("score") or ""))
    except SettlementError as exc:
        raise ResultSourceError(f"finished live_fixtures row has invalid score: {exc}") from exc
    return MatchResult(
        match_id_hash=match_hash,
        final_score=score,
        status="ft",
        observed_at=observed_at,
    )
