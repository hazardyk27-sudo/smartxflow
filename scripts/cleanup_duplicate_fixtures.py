#!/usr/bin/env python3
"""Conservative cleanup/audit for stale duplicate fixture rows.

Identity and canonical hash calculation are delegated to `core.hash_utils`.
Dry-run is the default. A stale fixture is deletable only when no known table
still references its hash. This script deliberately does NOT remap references;
that requires a separate reviewed migration because several alarm tables have
unique constraints that can collide during stale->canonical updates.
"""

from __future__ import annotations

import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote, urlparse

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.hash_utils import make_fixture_identity_key, make_match_id_hash

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
EXPECTED_PROJECT_REF = os.environ.get("SMARTXFLOW_SUPABASE_PROJECT_REF", "pswdvnmqjjnjodwzkmkp").strip()
APPLY = os.environ.get("FIXTURE_DUPLICATE_APPLY", "0") == "1"
MAX_DELETE = int(os.environ.get("FIXTURE_DUPLICATE_MAX_DELETE", "200"))
PAGE_SIZE = 1000

REFERENCE_TABLES = (
    "analyses", "bigmoney_alarms", "dropping_1x2_history", "dropping_alarms",
    "dropping_btts_history", "dropping_ou25_history", "free_matches",
    "insider_alarms", "live_fixtures", "live_snapshots", "matchbook_1x2_history",
    "matchbook_btts_history", "matchbook_fixtures", "matchbook_ou25_history",
    "mim_alarms", "moneyway_1x2_history", "moneyway_btts_history",
    "moneyway_ou25_history", "moneyway_snapshots", "publicmove_alarms",
    "sharp_alarms", "telegram_sent_log", "volume_leader_alarms",
    "volumeshock_alarms",
)


def _headers(prefer: str | None = None) -> dict[str, str]:
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def _validate_target() -> None:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise SystemExit("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY missing")
    host = (urlparse(SUPABASE_URL).hostname or "").lower()
    expected_host = f"{EXPECTED_PROJECT_REF}.supabase.co".lower()
    if host != expected_host:
        raise SystemExit(f"REFUSE_WRONG_SUPABASE_TARGET host={host or 'missing'} expected={expected_host}")


def canonical_hash(row: dict) -> str:
    return make_match_id_hash(
        row.get("home_team", ""), row.get("away_team", ""),
        row.get("league", ""), row.get("kickoff_utc", ""),
    )


def identity_key(row: dict):
    return make_fixture_identity_key(
        row.get("home_team", ""), row.get("away_team", ""),
        row.get("league", ""), row.get("kickoff_utc", ""),
    )


def fetch_all_fixtures() -> list[dict]:
    rows: list[dict] = []
    offset = 0
    while True:
        url = (
            f"{SUPABASE_URL}/rest/v1/fixtures"
            "?select=match_id_hash,home_team,away_team,league,kickoff_utc,fixture_date"
            f"&limit={PAGE_SIZE}&offset={offset}"
        )
        response = requests.get(url, headers=_headers(), timeout=30)
        response.raise_for_status()
        page = response.json()
        if not isinstance(page, list):
            raise RuntimeError("fixtures response is not a list")
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        if offset > 100_000:
            raise RuntimeError("fixture pagination safety limit exceeded")
    return rows


def _missing_table_or_column(response: requests.Response) -> bool:
    if response.status_code not in (400, 404):
        return False
    text = (response.text or "").lower()
    return any(token in text for token in ("pgrst205", "pgrst204", "does not exist", "could not find"))


def build_reference_map(match_hashes: list[str]) -> tuple[dict[str, list[str]], list[str]]:
    refs: dict[str, list[str]] = {h: [] for h in match_hashes}
    errors: list[str] = []
    if not match_hashes:
        return refs, errors

    safe_hashes = [h for h in match_hashes if re.fullmatch(r"[0-9a-f]{12}", h)]
    if len(safe_hashes) != len(match_hashes):
        return refs, ["candidate_hash_validation_failed"]

    in_filter = ",".join(safe_hashes)
    for table in REFERENCE_TABLES:
        url = (
            f"{SUPABASE_URL}/rest/v1/{table}"
            f"?select=match_id_hash&match_id_hash=in.({in_filter})&limit=1000"
        )
        try:
            response = requests.get(url, headers=_headers(), timeout=30)
        except Exception as exc:
            errors.append(f"{table}:request:{type(exc).__name__}")
            continue
        if response.status_code == 200:
            try:
                for row in response.json() or []:
                    h = str(row.get("match_id_hash") or "")
                    if h in refs and table not in refs[h]:
                        refs[h].append(table)
            except Exception:
                errors.append(f"{table}:json")
        elif not _missing_table_or_column(response):
            errors.append(f"{table}:http{response.status_code}")
    return refs, errors


def delete_fixture(match_hash: str) -> bool:
    encoded = quote(match_hash, safe="")
    url = f"{SUPABASE_URL}/rest/v1/fixtures?match_id_hash=eq.{encoded}"
    response = requests.delete(url, headers=_headers("return=representation"), timeout=20)
    if response.status_code not in (200, 204):
        print(f"DELETE_SKIP hash={match_hash} status={response.status_code}")
        return False
    try:
        returned = response.json() if response.text else []
    except Exception:
        returned = []
    if response.status_code == 200 and not returned:
        print(f"DELETE_SKIP hash={match_hash} status=200 reason=no_row_returned")
        return False
    return True


def main() -> int:
    _validate_target()
    fixtures = fetch_all_fixtures()
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in fixtures:
        key = identity_key(row)
        if key:
            groups[key].append(row)

    duplicate_groups = [rows for rows in groups.values() if len(rows) > 1]
    candidates: list[tuple[str, str]] = []
    ambiguous = 0
    for rows in duplicate_groups:
        canonical_rows = [row for row in rows if str(row.get("match_id_hash") or "") == canonical_hash(row)]
        if len(canonical_rows) != 1:
            ambiguous += 1
            continue
        keep_hash = str(canonical_rows[0].get("match_id_hash") or "")
        for row in rows:
            stale_hash = str(row.get("match_id_hash") or "")
            if stale_hash and stale_hash != keep_hash:
                candidates.append((stale_hash, keep_hash))

    reference_map, reference_errors = build_reference_map([stale for stale, _ in candidates])
    deleted = referenced = failed_closed = dry_run_ready = 0

    if reference_errors:
        print("FIXTURE_DUPLICATE_REFERENCE_CHECK_FAILED errors=" + ",".join(reference_errors[:8]))
        failed_closed = len(candidates)
    else:
        for stale_hash, keep_hash in candidates:
            refs = reference_map.get(stale_hash, [])
            if refs:
                referenced += 1
                print(f"FIXTURE_DUPLICATE_KEEP hash={stale_hash} canonical={keep_hash} references={','.join(refs)}")
                continue
            dry_run_ready += 1
            if not APPLY:
                print(f"FIXTURE_DUPLICATE_DRY_RUN hash={stale_hash} canonical={keep_hash}")
                continue
            if deleted >= MAX_DELETE:
                failed_closed += 1
                print("FIXTURE_DUPLICATE_STOP max delete safety limit reached")
                break
            if delete_fixture(stale_hash):
                deleted += 1
                print(f"FIXTURE_DUPLICATE_DELETED hash={stale_hash} canonical={keep_hash}")
            else:
                failed_closed += 1

    print(
        "FIXTURE_DUPLICATE_RESULT "
        f"fixtures={len(fixtures)} duplicate_groups={len(duplicate_groups)} "
        f"ambiguous_groups={ambiguous} candidates={len(candidates)} "
        f"referenced_kept={referenced} safe_candidates={dry_run_ready} "
        f"deleted={deleted} failed_closed={failed_closed} apply={int(APPLY)}"
    )
    return 0 if failed_closed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
