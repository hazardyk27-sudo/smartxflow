#!/usr/bin/env python3
"""Append verified historical SXF timelines to legacy Learning Archive cases.

This is append-only. Existing finalized case/evidence/settlement/checksum files are
never rewritten. Historical rows are read from the existing SmartXFlow Supabase
history tables using a separately verified canonical fixture hash.
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
    return _parse_utc(str(row.get("scraped_at") or row.get("scraped_at_utc") or ""), "snapshot timestamp")


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
        key, value = key.strip(), value.strip()
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
        self.api = f"https://api.github.com/repos/{REPOSITORY}"
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "smartxflow-learning-archive-hydration",
        })

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        last: requests.Response | None = None
        for attempt in range(4):
            last = self.session.request(method, url, timeout=45, **kwargs)
            if last.status_code not in {409, 429, 500, 502, 503, 504}:
                return last
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
        response = self._request("PUT", f"{self.api}/contents/{encoded}", json={
            "message": message,
            "content": base64.b64encode(payload).decode("ascii"),
            "branch": ARCHIVE_BRANCH,
        })
        if response.status_code not in {200, 201}:
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
        self.session.headers.update({"apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json"})

    def _get(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        last: requests.Response | None = None
        for attempt in range(4):
            last = self.session.get(f"{self.base}/rest/v1/{table}", params=params, timeout=45)
            if last.status_code == 200:
                payload = last.json()
                if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
                    raise HydrationError(f"Supabase {table} returned invalid payload")
                return payload
            if last.status_code not in {429, 500, 502, 503, 504}:
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

    def table_history(self, table: str, timestamp_field: str, match_hash: str, kickoff_at: datetime) -> list[dict[str, Any]]:
        """Read all rows for the canonical hash, then apply UTC cutoff in Python.

        Legacy history timestamp columns are TEXT and contain offset-aware values such
        as 2026-10-03T16:08:37+03:00. PostgREST lt.<UTC-Z> on a TEXT column performs
        lexical comparison, which can incorrectly drop valid rows around prediction/
        kickoff. Filtering after ISO parsing is therefore required for correct history.
        """
        rows: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = self._get(table, {
                "select": "*",
                "match_id_hash": f"eq.{match_hash}",
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
        prematch = [row for row in rows if _row_timestamp(row) < kickoff_at]
        prematch.sort(key=lambda row: (_row_timestamp(row), str(row.get("id") or "")))
        return prematch


def _validate_request(payload: Any) -> tuple[str, str, list[dict[str, Any]]]:
    if not isinstance(payload, dict) or payload.get("operation") != "HISTORICAL_SXF_HYDRATION":
        raise HydrationError("operation must be HISTORICAL_SXF_HYDRATION")
    request_id = str(payload.get("request_id") or "").strip()
    backfill_at = str(payload.get("backfill_at") or "").strip()
    cases = payload.get("cases")
    if not request_id:
        raise HydrationError("request_id is required")
    _parse_utc(backfill_at, "backfill_at")
    if not isinstance(cases, list) or not cases:
        raise HydrationError("cases must be a non-empty array")
    required = {"case_id","case_hash","canonical_hash","prediction_at","kickoff_at","canonical_home","canonical_away","canonical_league"}
    seen: set[str] = set()
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
        if _parse_utc(str(item["prediction_at"]), f"{case_id}.prediction_at") >= _parse_utc(str(item["kickoff_at"]), f"{case_id}.kickoff_at"):
            raise HydrationError(f"{case_id}: prediction_at must be before kickoff_at")
    return request_id, backfill_at, cases


def _supabase_key() -> str:
    return (os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip() or os.environ.get("SUPABASE_ANON_KEY", "").strip() or os.environ.get("SUPABASE_KEY", "").strip())


def hydrate(request_path: Path) -> dict[str, Any]:
    request_id, backfill_at, cases = _validate_request(json.loads(request_path.read_text(encoding="utf-8")))
    supabase = SupabaseSource(os.environ.get("SUPABASE_URL", ""), _supabase_key())
    github = GitHubWriter(os.environ.get("GITHUB_TOKEN", "") or os.environ.get("GH_TOKEN", ""))

    prepared: list[dict[str, Any]] = []
    for item in cases:
        case_id = str(item["case_id"]).strip()
        case_hash = str(item["case_hash"]).strip().lower()
        canonical_hash = str(item["canonical_hash"]).strip().lower()
        prediction_at = _parse_utc(str(item["prediction_at"]), f"{case_id}.prediction_at")
        kickoff_at = _parse_utc(str(item["kickoff_at"]), f"{case_id}.kickoff_at")
        case_path = f"{ARCHIVE_ROOT}/cases/{kickoff_at.strftime('%Y/%m/%d')}/{case_id}"

        existing = github.read(f"{case_path}/case.json")
        if existing is None:
            raise HydrationError(f"{case_id}: archived case.json missing")
        case_doc = json.loads(existing[0].decode("utf-8"))
        archived_match = case_doc.get("match") or {}
        archived_prediction = case_doc.get("prediction") or {}
        if str(case_doc.get("case_id") or "") != case_id:
            raise HydrationError(f"{case_id}: archived case_id mismatch")
        if str(archived_match.get("match_id_hash") or "").lower() != case_hash:
            raise HydrationError(f"{case_id}: archived case hash mismatch")
        if _parse_utc(str(archived_match.get("kickoff_at") or ""), f"{case_id}.archive kickoff") != kickoff_at:
            raise HydrationError(f"{case_id}: archived kickoff mismatch")
        if _parse_utc(str(archived_prediction.get("prediction_at") or ""), f"{case_id}.archive prediction") != prediction_at:
            raise HydrationError(f"{case_id}: archived prediction timestamp mismatch")

        fixture = supabase.fixture(canonical_hash)
        expected = (str(item["canonical_home"]), str(item["canonical_away"]), str(item["canonical_league"]), kickoff_at)
        actual = (str(fixture.get("home_team") or ""), str(fixture.get("away_team") or ""), str(fixture.get("league") or ""), _parse_utc(str(fixture.get("kickoff_utc") or ""), f"{case_id}.fixture kickoff"))
        if actual != expected:
            raise HydrationError(f"{case_id}: canonical fixture identity mismatch; expected={expected[:3]} actual={actual[:3]}")

        flattened: list[dict[str, Any]] = []
        table_stats: dict[str, Any] = {}
        for table, ts_field in SOURCE_TABLES:
            rows = supabase.table_history(table, ts_field, canonical_hash, kickoff_at)
            if not rows:
                raise HydrationError(f"{case_id}: {table} has no prematch history")
            pre_rows = [r for r in rows if _row_timestamp(r) <= prediction_at]
            post_rows = [r for r in rows if prediction_at < _row_timestamp(r) < kickoff_at]
            if not pre_rows or not post_rows:
                raise HydrationError(f"{case_id}: {table} incomplete around prediction_at (pre={len(pre_rows)}, post={len(post_rows)})")
            for row in rows:
                if str(row.get("match_id_hash") or "").strip().lower() != canonical_hash:
                    raise HydrationError(f"{case_id}: {table} source hash mismatch")
                copied = dict(row)
                copied["_archive_source_table"] = table
                copied["_archive_identity_kind"] = "CANONICAL_HASH_RESOLVED"
                flattened.append(copied)
            table_stats[table] = {
                "rows": len(rows),
                "rows_at_or_before_prediction": len(pre_rows),
                "rows_after_prediction_before_kickoff": len(post_rows),
                "first_snapshot_at": _iso(min(_row_timestamp(r) for r in rows)),
                "last_snapshot_at": _iso(max(_row_timestamp(r) for r in rows)),
            }

        flattened.sort(key=lambda r: (_row_timestamp(r), str(r.get("_archive_source_table") or ""), str(r.get("id") or "")))
        snapshots = _deterministic_gzip(flattened)
        digest = _sha256(snapshots)
        checksum = f"{digest}  historical_sxf_snapshots.json.gz\n".encode("utf-8")
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
                "canonical_fixture": {"home": fixture.get("home_team"), "away": fixture.get("away_team"), "league": fixture.get("league"), "kickoff_at": _iso(kickoff_at)},
            },
            "timeline": {
                "prediction_at": _iso(prediction_at),
                "kickoff_at": _iso(kickoff_at),
                "rows_total": len(flattened),
                "tables_required": [name for name, _ in SOURCE_TABLES],
                "table_stats": table_stats,
                "coverage_gate": "PASS",
            },
            "artifact": {"path": "historical_sxf_snapshots.json.gz", "sha256": digest, "encoding": "canonical-json + deterministic-gzip(mtime=0)"},
            "provenance": {"source": "SmartXFlow production Supabase historical tables", "backfill_kind": "HISTORICAL_BACKFILL", "append_only": True, "original_finalized_files_rewritten": False},
        }
        prepared.append({"case_id":case_id,"case_path":case_path,"snapshots":snapshots,"checksum":checksum,"metadata":_canonical_json_bytes(metadata),"sha256":digest,"rows":len(flattened),"table_stats":table_stats})

    receipts: list[dict[str, Any]] = []
    for pkg in prepared:
        files = {
            "historical_sxf_snapshots.json.gz": pkg["snapshots"],
            "historical_sxf_snapshots.sha256": pkg["checksum"],
            "addenda/historical_sxf_backfill.json": pkg["metadata"],
        }
        created: list[str] = []
        for name, content in files.items():
            if github.create_immutable(f"{pkg['case_path']}/{name}", content, f"Hydrate {pkg['case_id']}: {name}"):
                created.append(name)
        for name, content in files.items():
            remote = github.read(f"{pkg['case_path']}/{name}")
            if remote is None or remote[0] != content:
                raise HydrationError(f"{pkg['case_id']}: post-write verification failed for {name}")
        receipts.append({"case_id":pkg["case_id"],"status":"HYDRATED","rows":pkg["rows"],"sha256":pkg["sha256"],"created":created,"table_stats":pkg["table_stats"]})

    return {"status":"HYDRATED","request_id":request_id,"requested":len(cases),"hydrated":len(receipts),"verified":len(receipts),"receipts":receipts}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("request")
    parser.add_argument("--dotenv", default="/opt/smartxflow/.env")
    args = parser.parse_args()
    try:
        _load_dotenv_literal(args.dotenv)
        result = hydrate(Path(args.request))
    except (OSError, ValueError, json.JSONDecodeError, requests.RequestException, HydrationError) as exc:
        print(json.dumps({"status":"FAILED","error":str(exc)}, ensure_ascii=False), flush=True)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
