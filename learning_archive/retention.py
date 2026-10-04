from __future__ import annotations

from datetime import datetime, timezone
import os

import requests

_TRUE = {"1", "true", "yes", "on"}
_TABLE = "learning_archive_retention_holds"


class RetentionHoldError(RuntimeError):
    pass


def retention_holds_enabled() -> bool:
    """Retention protection is mandatory by default.

    The production migration now exists, so retention must no longer depend on
    an opt-in flag that can be forgotten. Only an explicit emergency-disable
    switch can turn the guard off.
    """
    emergency_disable = os.environ.get(
        "SMARTXFLOW_LEARNING_ARCHIVE_RETENTION_EMERGENCY_DISABLE", ""
    ).strip().lower()
    return emergency_disable not in _TRUE


def _config() -> tuple[str, str]:
    url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    # The retention-control table is intentionally restricted to service_role.
    # Prefer the explicit service-role credential used by production. Keep the
    # legacy aliases only as backwards-compatible fallbacks for environments
    # where SUPABASE_KEY itself is already the service-role key.
    key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        or os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
        or os.environ.get("SUPABASE_KEY", "").strip()
    )
    if not url or not key:
        raise RetentionHoldError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (or a service-role legacy alias) "
            "are required for Learning Archive retention holds"
        )
    return url, key


def _session() -> requests.Session:
    _, key = _config()
    session = requests.Session()
    session.headers.update({
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "smartxflow-learning-archive-retention",
    })
    return session


def create_retention_hold(case_id: str, match_id_hash: str, prediction_at: str) -> None:
    if not retention_holds_enabled():
        raise RetentionHoldError("Learning Archive retention holds are emergency-disabled")
    url, _ = _config()
    session = _session()
    response = session.post(
        f"{url}/rest/v1/{_TABLE}",
        params={"on_conflict": "case_id"},
        headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
        json={
            "case_id": case_id,
            "match_id_hash": match_id_hash,
            "prediction_at": prediction_at,
            "status": "PENDING",
            "finalized_at": None,
            "archive_reference": None,
            "checksum_summary": None,
        },
        timeout=30,
    )
    if response.status_code not in (200, 201, 204):
        raise RetentionHoldError(f"could not create retention hold ({response.status_code})")


def release_retention_hold(case_id: str, archive_reference: str, checksum_summary: str) -> None:
    if not retention_holds_enabled():
        return
    url, _ = _config()
    session = _session()
    finalized_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    response = session.patch(
        f"{url}/rest/v1/{_TABLE}",
        params={"case_id": f"eq.{case_id}", "status": "eq.PENDING"},
        headers={"Prefer": "return=representation"},
        json={
            "status": "FINALIZED",
            "finalized_at": finalized_at,
            "archive_reference": archive_reference,
            "checksum_summary": checksum_summary,
        },
        timeout=30,
    )
    if response.status_code != 200:
        raise RetentionHoldError(f"could not release retention hold ({response.status_code})")
    rows = response.json()
    if not isinstance(rows, list) or not rows:
        # Idempotent reruns are allowed when the row is already finalized.
        check = session.get(
            f"{url}/rest/v1/{_TABLE}",
            params={"select": "status,checksum_summary", "case_id": f"eq.{case_id}", "limit": "1"},
            timeout=30,
        )
        if check.status_code != 200:
            raise RetentionHoldError("retention hold release could not be verified")
        existing = check.json()
        if not existing or existing[0].get("status") != "FINALIZED" or existing[0].get("checksum_summary") != checksum_summary:
            raise RetentionHoldError("retention hold release verification failed")


def has_pending_retention_holds() -> bool:
    """Fail-safe query used by cleanup guard. Errors are raised so caller can block cleanup."""
    if not retention_holds_enabled():
        return False
    url, _ = _config()
    session = _session()
    response = session.get(
        f"{url}/rest/v1/{_TABLE}",
        params={"select": "case_id", "status": "eq.PENDING", "limit": "1"},
        timeout=15,
    )
    if response.status_code != 200:
        raise RetentionHoldError(f"could not verify retention holds ({response.status_code})")
    rows = response.json()
    if not isinstance(rows, list):
        raise RetentionHoldError("retention hold query returned invalid payload")
    return bool(rows)
