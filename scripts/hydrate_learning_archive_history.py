#!/usr/bin/env python3
"""Append verified historical SXF timelines to finalized Learning Archive cases.

The legacy case package is immutable. This utility only adds:
- historical_sxf_snapshots.json.gz
- historical_sxf_snapshots.sha256
- addenda/historical_sxf_backfill.json

All source tables are read from SmartXFlow Supabase using a separately verified
canonical fixture hash. Every table must contain data on both sides of prediction_at
and all rows are cut strictly before kickoff_at. Writes are immutable and verified by
readback so partial/incorrect history can never be reported as complete.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any
from urllib.parse import quote

import requests

REPOSITORY = "hazardyk27-sudo/smartxflow"
ARCHIVE_BRANCH = "learning-archive"
ARCHIVE_ROOT = "learning_archive_data"
SOURCE_TABLES: tuple[tuple[str, str], ...] = (
    ("moneyway_1x2_history", "scraped_at"),
    ("moneyway_ou25_history", "scraped_at"),
    ("moneyway_btts_history", "scraped_at"),
    ("dropping_1x2_history", "scraped_at"),
    ("dropping_ou25_history", "scraped_at"),
    ("dropping_btts_history", "scraped_at"),
    ("moneyway_snapshots", "scraped_at_utc"),
)
PAGE_SIZE = 1000
MAX_ROWS_PER_TABLE = 50_000


class HydrationError(RuntimeError):
    pass


def _parse_utc(value: str, field: str) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        raise HydrationError(f"{field} is required")
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise HydrationError(f"{field} must be ISO-8601: {value}") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise HydrationError(f"{field} must include timezone")
    return dt.astimezone(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _row_timestamp(row: dict[str, Any]) -> datetime:
    raw = row.get("scraped_at") or row.get("scraped_at_utc")
    return _parse_utc(str(raw or ""), "snapshot timestamp")


def _canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _deterministic_gzip(value: Any) -> bytes:
    return gzip.compress(_canonical_json_bytes(value), compresslevel=9, mtime=0)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _load_dotenv_literal(path: str | Path) -> None:
    dotenv = Path(path)
    if not dotenv.exists():
        raise HydrationError(f"dotenv not found: {dotenv}")
    for raw in dotenv.read_text(encoding="utf-8").splitlines():
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
        if key and key not in os.environ:
            os.environ[key] = value


class GitHubWriter:
    def __init__(self, token: str) -> None:
        if not token:
            raise HydrationError("GITHUB_TOKEN/GH_TOKEN is required")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "smartxflow-learning-archive-hydration",
        })
        self.api = f"https://api.github.com/repos/{REPOSITORY}"

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        last: requests.Response | None = None
        for attempt in range(4):
            response = self.session.request(method, url, timeout=45, **kwargs)
            last = response
            if response.status_code not in {409, 429, 500, 502, 503, 504}:
                return response
            time.sleep(1.0 + attempt)
        assert last is not None
        return last

    def read(self, path: str) -> tuple[bytes, str] | None:
        encoded = quote(path.lstrip("/"), safe="/")
        response = self._request("GET", f"{self.api}/contents/{encoded}", params={"ref": ARCHIVE_BRANCH})
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise HydrationError(f"GitHub read failed for {path}: HTTP {response.status_code}")
        body = response.json()
        sha = str(body.get("sha") or "")
        content = body.get("content")
        if isinstance(content, str) and content:
            return base64.b64decode(content), sha
        if not sha:
            raise HydrationError(f"GitHub read returned no blob SHA for {path}")
        blob = self._request("GET", f"{self.api}/git/blobs/{sha}")
        if blob.status_code != 200:
            raise HydrationError(f"GitHub blob read failed for {path}: HTTP {blob.status_code}")
        blob_content = blob.json().get("content")
        if not isinstance(blob_content, str):
            raise HydrationError(f"GitHub blob payload missing for {path}")
        return base64.b64decode(blob_content), sha

    def create_immutable(self, path: str, payload: bytes, message: str) -> bool:
        current = self.read(path)
        if current is not None:
            if current[0] != payload:
                raise HydrationError(f"append-only conflict at {path}")
            return False
        encoded = quote(path.lstrip("/"), safe="/")
        response = self._request(
            "PUT",
            f"{self.api}/contents/{encoded}",
            json={
                "message": message,
                "content": base64.b64encode(payload).decode("ascii"),
                "branch": ARCHIVE_BRANCH,
            },
        )
        if response.status_code not in {200, 201}:
            # A concurrent/idempotent retry may have created the exact file.
            current = self.read(path)
            if current is not None and current[0] == payload:
                return False
            raise HydrationError(f"GitHub create failed for {path}: HTTP {response.status_code} {response.text[:300]}")
        return True


class SupabaseSource:
    def __init__(self, url: str, key: str) -> None:
        self.base = url.rstrip("/")
        if not self.base or not key:
            raise HydrationError("Supabase URL/key are required")
        self.session = requests.Session()
        self.session.headers.update({
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
        })

    def _get(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        last: requests.Response | None = None
        for attempt in range(4):
            response = self.session.get(f"{self.base}/rest/v1/{table}", params=params, timeout=45)
            last = response
            if response.status_code == 200:
                payload = response.json()
                if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
                    raise HydrationError(f"Supabase {table} returned invalid payload")
                return payload
            if response.status_code not in {429, 500, 502, 503, 504}:
                break
            time.sleep(1.0 + attempt)
        assert last is not None
        raise HydrationError(f"Supabase {table} read failed: HTTP {last.status_code} {last.text[:300]}")

    def fixture(self, match_hash: str) -> dict[str, Any]:
        rows = self._get("fixtures", {
            "select": "match_id_hash,league,home_team,away_team,kickoff_utc",
            "match_id_hash": f"eq.{match_hash}",
            "limit": "2",
        })
        if len(rows) != 1:
            raise HydrationError(f"canonical fixture lookup for {match_hash} returned {len(rows)} rows")
        return rows[0]

    def table_history(
        self,
        table: str,
        timestamp_field: str,
        match_hash: str,
        kickoff_at: datetime,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = self._get(table, {
                "select": "*",
                "match_id_hash": f"eq.{match_hash}",
                timestamp_field: f"lt.{_iso(kickoff_at)}",
                "order": f"{timestamp_field}.asc,id.asc",
                "limit": str(PAGE_SIZE),
                "offset": str(offset),
            })
            rows.extend(page)
            if len(rows) > MAX_ROWS_PER_TABLE:
                raise HydrationError(f"{table} exceeded safety row limit for {match_hash}")
            if len(page) < PAGE_SIZE:
                break
            offset += PAGE_SIZE
        return rows


def _validate_request(payload: Any) -> tuple[str, str, list[dict[str, Any]]]:
    if not isinstance(payload, dict):
        raise HydrationError("request must be an object")
    if payload.get("operation") != "HISTORICAL_SXF_HYDRATION":
        raise HydrationError("operation must be HISTORICAL_SXF_HYDRATION")
    request_id = str(payload.get("request_id") or "").strip()
    backfill_at = str(payload.get("backfill_at") or "").strip()
    cases = payload.get("cases")
    if not request_id:
        raise HydrationError("request_id is required")
    _parse_utc(backfill_at, "backfill_at")
    if not isinstance(cases, list) or not cases:
        raise HydrationError("cases must be a non-empty array")
    seen: set[str] = set()
    required = {
        "case_id", "case_hash", "canonical_hash", "prediction_at", "kickoff_at",
        "canonical_home", "canonical_away", "canonical_league",
    }
    for index, item in enumerate(cases):
        if not isinstance(item, dict):
            raise HydrationError(f"cases[{index}] must be an object")
        missing = sorted(required - set(item))
        if missing:
            raise HydrationError(f"cases[{index}] missing fields: {', '.join(missing)}")
        case_id = str(item["case_id"]).strip()
        if not case_id or case_id in seen:
            raise HydrationError(f"invalid/duplicate case_id: {case_id}")
        seen.add(case_id)
        prediction = _parse_utc(str(item["prediction_at"]), f"{case_id}.prediction_at")
        kickoff = _parse_utc(str(item["kickoff_at"]), f"{case_id}.kickoff_at")
        if prediction >= kickoff:
            raise HydrationError(f"{case_id}: prediction_at must be before kickoff_at")
    return request_id, backfill_at, cases


def _supabase_key() -> str:
    return (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        or os.environ.get("SUPABASE_ANON_KEY", "").strip()
        or os.environ.get("SUPABASE_KEY", "").strip()
    )


def hydrate(request_path: Path) -> dict[str, Any]:
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    request_id, backfill_at, cases = _validate_request(payload)

    supabase = SupabaseSource(os.environ.get("SUPABASE_URL", ""), _supabase_key())
    github = GitHubWriter(os.environ.get("GITHUB_TOKEN", "") or os.environ.get("GH_TOKEN", ""))

    # Preflight every case and build every deterministic package before the first write.
    prepared: list[dict[str, Any]] = []
    for item in cases:
        case_id = str(item["case_id"]).strip()
        case_hash = str(item["case_hash"]).strip().lower()
        canonical_hash = str(item["canonical_hash"]).strip().lower()
        prediction_at = _parse_utc(str(item["prediction_at"]), f"{case_id}.prediction_at")
        kickoff_at = _parse_utc(str(item["kickoff_at"]), f"{case_id}.kickoff_at")
        date_path = kickoff_at.strftime("%Y/%m/%d")
        case_path = f"{ARCHIVE_ROOT}/cases/{date_path}/{case_id}"

        existing_case = github.read(f"{case_path}/case.json")
        if existing_case is None:
            raise HydrationError(f"{case_id}: archived case.json missing")
        case_doc = json.loads(existing_case[0].decode("utf-8"))
        if str(case_doc.get("case_id") or "") != case_id:
            raise HydrationError(f"{case_id}: archived case_id mismatch")
        archived_match = case_doc.get("match") or {}
        archived_prediction = case_doc.get("prediction") or {}
        if str(archived_match.get("match_id_hash") or "").lower() != case_hash:
            raise HydrationError(f"{case_id}: archived case hash mismatch")
        if _parse_utc(str(archived_match.get("kickoff_at") or ""), f"{case_id}.archive kickoff") != kickoff_at:
            raise HydrationError(f"{case_id}: archived kickoff mismatch")
        if _parse_utc(str(archived_prediction.get("prediction_at") or ""), f"{case_id}.archive prediction") != prediction_at:
            raise HydrationError(f"{case_id}: archived prediction timestamp mismatch")

        fixture = supabase.fixture(canonical_hash)
        expected_fixture = (
            str(item["canonical_home"]), str(item["canonical_away"]),
            str(item["canonical_league"]), kickoff_at,
        )
        actual_fixture = (
            str(fixture.get("home_team") or ""), str(fixture.get("away_team") or ""),
            str(fixture.get("league") or ""),
            _parse_utc(str(fixture.get("kickoff_utc") or ""), f"{case_id}.fixture kickoff"),
        )
        if actual_fixture != expected_fixture:
            raise HydrationError(
                f"{case_id}: canonical fixture identity mismatch; expected={expected_fixture[:3]} actual={actual_fixture[:3]}"
            )

        flattened: list[dict[str, Any]] = []
        table_stats: dict[str, Any] = {}
        for table, timestamp_field in SOURCE_TABLES:
            rows = supabase.table_history(table, timestamp_field, canonical_hash, kickoff_at)
            if not rows:
                raise HydrationError(f"{case_id}: {table} has no prematch history")
            pre = 0
            post = 0
            first_ts: datetime | None = None
            last_ts: datetime | None = None
            for row in rows:
                row_hash = str(row.get("match_id_hash") or "").strip().lower()
                if row_hash != canonical_hash:
                    raise HydrationError(f"{case_id}: {table} source hash mismatch")
                ts = _row_timestamp(row)
                if ts >= kickoff_at:
                    raise HydrationError(f"{case_id}: {table} contains post-kickoff row")
                if ts <= prediction_at:
                    pre += 1
                else:
                    post += 1
                first_ts = ts if first_ts is None or ts < first_ts else first_ts
                last_ts = ts if last_ts is None or ts > last_ts else last_ts
                copied = dict(row)
                copied["_archive_source_table"] = table
                copied["_archive_identity_kind"] = "CANONICAL_HASH_RESOLVED"
                flattened.append(copied)
            if pre == 0 or post == 0:
                raise HydrationError(
                    f"{case_id}: {table} incomplete around prediction_at (pre={pre}, post={post})"
                )
            table_stats[table] = {
                "rows": len(rows),
                "rows_at_or_before_prediction": pre,
                "rows_after_prediction_before_kickoff": post,
                "first_snapshot_at": _iso(first_ts),
                "last_snapshot_at": _iso(last_ts),
            }

        flattened.sort(key=lambda row: (
            _row_timestamp(row),
            str(row.get("_archive_source_table") or ""),
            str(row.get("id") or ""),
        ))
        if not flattened:
            raise HydrationError(f"{case_id}: no prematch history after validation")

        snapshots_payload = _deterministic_gzip(flattened)
        snapshots_sha = _sha256(snapshots_payload)
        checksum_payload = f"{snapshots_sha}  historical_sxf_snapshots.json.gz\n".encode("utf-8")
        metadata = {
            "archive_schema_version": 1,
            "kind": "HISTORICAL_SXF_BACKFILL",
            "request_id": request_id,
            "backfill_at": backfill_at,
            "case_id": case_id,
            "identity_resolution": {
                "archived_case_hash": case_hash,
                "canonical_source_hash": canonical_hash,
                "method": "exact_fixture_home_away_league_kickoff_verified",
                "canonical_fixture": {
                    "home": fixture.get("home_team"),
                    "away": fixture.get("away_team"),
                    "league": fixture.get("league"),
                    "kickoff_at": _iso(kickoff_at),
                },
            },
            "timeline": {
                "prediction_at": _iso(prediction_at),
                "kickoff_at": _iso(kickoff_at),
                "rows_total": len(flattened),
                "tables_required": [name for name, _ in SOURCE_TABLES],
                "table_stats": table_stats,
                "coverage_gate": "PASS",
            },
            "artifact": {
                "path": "historical_sxf_snapshots.json.gz",
                "sha256": snapshots_sha,
                "encoding": "canonical-json + deterministic-gzip(mtime=0)",
            },
            "provenance": {
                "source": "SmartXFlow production Supabase historical tables",
                "backfill_kind": "HISTORICAL_BACKFILL",
                "append_only": True,
                "original_finalized_files_rewritten": False,
            },
        }
        prepared.append({
            "case_id": case_id,
            "case_path": case_path,
            "snapshots": snapshots_payload,
            "checksum": checksum_payload,
            "metadata": _canonical_json_bytes(metadata),
            "sha256": snapshots_sha,
            "rows": len(flattened),
            "table_stats": table_stats,
        })

    receipts: list[dict[str, Any]] = []
    for package in prepared:
        case_id = package["case_id"]
        case_path = package["case_path"]
        files = {
            "historical_sxf_snapshots.json.gz": package["snapshots"],
            "historical_sxf_snapshots.sha256": package["checksum"],
            "addenda/historical_sxf_backfill.json": package["metadata"],
        }
        created: list[str] = []
        for name, content in files.items():
            if github.create_immutable(
                f"{case_path}/{name}", content, f"Hydrate {case_id}: {name}"
            ):
                created.append(name)
        # Mandatory post-write byte-for-byte verification.
        for name, content in files.items():
            remote = github.read(f"{case_path}/{name}")
            if remote is None or remote[0] != content:
                raise HydrationError(f"{case_id}: post-write verification failed for {name}")
        receipts.append({
            "case_id": case_id,
            "status": "HYDRATED",
            "rows": package["rows"],
            "sha256": package["sha256"],
            "created": created,
            "table_stats": package["table_stats"],
        })

    return {
        "status": "HYDRATED",
        "request_id": request_id,
        "requested": len(cases),
        "hydrated": len(receipts),
        "verified": len(receipts),
        "receipts": receipts,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("request", help="Historical hydration request JSON")
    parser.add_argument("--dotenv", default="/opt/smartxflow/.env")
    args = parser.parse_args()
    try:
        _load_dotenv_literal(args.dotenv)
        result = hydrate(Path(args.request))
    except (OSError, ValueError, json.JSONDecodeError, requests.RequestException, HydrationError) as exc:
        print(json.dumps({"status": "FAILED", "error": str(exc)}, ensure_ascii=False), flush=True)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
