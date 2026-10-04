from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
from typing import Any

import requests

_TABLE = "learning_archive_capture_outbox"


class CaptureOutboxError(RuntimeError):
    pass


def load_dotenv_literal(path: str) -> None:
    with open(path, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key.startswith("export "):
                key = key[7:].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            if key:
                os.environ[key] = value


def _config() -> tuple[str, str]:
    url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        or os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
        or os.environ.get("SUPABASE_KEY", "").strip()
    )
    if not url or not key:
        raise CaptureOutboxError(
            "SUPABASE_URL and a service-role credential are required for capture outbox"
        )
    return url, key


def _session() -> requests.Session:
    _, key = _config()
    session = requests.Session()
    session.headers.update(
        {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "smartxflow-learning-archive-outbox",
        }
    )
    return session


def event_id(case_id: str, observed_at: str) -> str:
    raw = f"{case_id}\n{observed_at}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def capture_event_row(item: dict[str, Any], observed_at: str) -> dict[str, Any]:
    case = item.get("case") if isinstance(item, dict) else None
    if not isinstance(case, dict):
        raise CaptureOutboxError("capture item is missing case")
    case_id = str(case.get("case_id") or "").strip()
    match = case.get("match") if isinstance(case.get("match"), dict) else {}
    prediction = case.get("prediction") if isinstance(case.get("prediction"), dict) else {}
    match_id_hash = str(match.get("match_id_hash") or "").strip().lower()
    kickoff_at = str(match.get("kickoff_at") or "").strip()
    prediction_at = str(prediction.get("prediction_at") or "").strip()
    if not case_id or not match_id_hash or not kickoff_at or not prediction_at or not observed_at:
        raise CaptureOutboxError("capture event is missing immutable identity/timestamp fields")
    return {
        "event_id": event_id(case_id, observed_at),
        "case_id": case_id,
        "match_id_hash": match_id_hash,
        "observed_at": observed_at,
        "kickoff_at": kickoff_at,
        "prediction_at": prediction_at,
        "status": "PENDING",
    }


def enqueue_capture_events(captures: list[dict[str, Any]], observed_at: str) -> list[str]:
    if not captures:
        return []
    rows = [capture_event_row(item, observed_at) for item in captures]
    url, _ = _config()
    session = _session()
    response = session.post(
        f"{url}/rest/v1/{_TABLE}",
        params={"on_conflict": "event_id"},
        headers={"Prefer": "resolution=ignore-duplicates,return=minimal"},
        json=rows,
        timeout=30,
    )
    if response.status_code not in (200, 201, 204):
        raise CaptureOutboxError(f"capture outbox insert failed ({response.status_code})")

    ids = [row["event_id"] for row in rows]
    for eid in ids:
        check = session.get(
            f"{url}/rest/v1/{_TABLE}",
            params={"select": "event_id,status", "event_id": f"eq.{eid}", "limit": "1"},
            timeout=15,
        )
        if check.status_code != 200:
            raise CaptureOutboxError("capture outbox verification failed")
        payload = check.json()
        if not isinstance(payload, list) or not payload:
            raise CaptureOutboxError("capture outbox row missing after insert")
        if payload[0].get("status") not in ("PENDING", "MIRRORED"):
            raise CaptureOutboxError("capture outbox row has invalid status")
    return ids


def fetch_pending_capture_events(limit: int = 1000) -> list[dict[str, Any]]:
    url, _ = _config()
    session = _session()
    response = session.get(
        f"{url}/rest/v1/{_TABLE}",
        params={
            "select": "event_id,case_id,match_id_hash,observed_at,kickoff_at,prediction_at,status",
            "status": "eq.PENDING",
            "order": "observed_at.asc,event_id.asc",
            "limit": str(limit),
        },
        timeout=30,
    )
    if response.status_code != 200:
        raise CaptureOutboxError(f"capture outbox read failed ({response.status_code})")
    rows = response.json()
    if not isinstance(rows, list):
        raise CaptureOutboxError("capture outbox read returned invalid payload")
    return rows


def outbox_requests(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, set[str]] = {}
    for row in rows:
        observed_at = str(row.get("observed_at") or "").strip()
        case_id = str(row.get("case_id") or "").strip()
        if not observed_at or not case_id:
            raise CaptureOutboxError("pending outbox row is missing observed_at/case_id")
        grouped.setdefault(observed_at, set()).add(case_id)
    return [
        {"observed_at": observed_at, "case_ids": sorted(case_ids)}
        for observed_at, case_ids in sorted(grouped.items())
    ]


def mark_capture_events_mirrored(event_ids: list[str]) -> None:
    clean = sorted({str(value or "").strip() for value in event_ids if str(value or "").strip()})
    if not clean:
        return
    url, _ = _config()
    session = _session()
    mirrored_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    for eid in clean:
        response = session.patch(
            f"{url}/rest/v1/{_TABLE}",
            params={"event_id": f"eq.{eid}", "status": "eq.PENDING"},
            headers={"Prefer": "return=minimal"},
            json={"status": "MIRRORED", "mirrored_at": mirrored_at, "last_error": None},
            timeout=15,
        )
        if response.status_code not in (200, 204):
            raise CaptureOutboxError(f"capture outbox mirror update failed ({response.status_code})")
