#!/usr/bin/env python3
"""Append verified historical SXF timelines to finalized Learning Archive cases.

This utility is intentionally append-only. It never rewrites case.json, evidence.json,
settlement.json, checksums.sha256, or the original finalized sxf_snapshots.json.gz.
It is meant for legacy cases that were created before full automatic prematch history
capture existed.
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
        for attempt in range(3):
            response = self.session.request(method, url, timeout=30, **kwargs)
            last = response
            if response.status_code not in {429, 500, 502, 503, 504}:
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
            raise HydrationError(f"GitHub create failed for {path}: HTTP {response.status_code} {response.text[:300]}")
        return True

    def append_manifest_entries(self, entries: list[dict[str, Any]]) -> None:
        path = f"{ARCHIVE_ROOT}/manifest.jsonl"
        for attempt in range(4):
            current = self.read(path)
            if current is None:
                raise HydrationError("archive manifest.jsonl is missing")
            raw, sha = current
            parsed: list[dict[str, Any]] = []
            for lineno, line in enumerate(raw.decode("utf-8").splitlines(), 1):
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise HydrationError(f"archive manifest line {lineno} is invalid") from exc
                if not isinstance(item, dict):
                    raise HydrationError(f"archive manifest line {lineno} is not an object")
                parsed.append(item)

            changed = False
            for entry in entries:
                key = (entry["case_id"], entry["event"], entry["event_key"])
                matches = [
                    item for item in parsed
                    if (item.get("case_id"), item.get("event"), item.get("event_key")) == key
                ]
                if matches:
                    if matches[0] != entry:
                        raise HydrationError(f"manifest conflict for {entry['case_id']} {entry['event_key']}")
                    continue
                parsed.append(entry)
                changed = True
            if not changed:
                return

            updated = "".join(
                json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
                for item in parsed
            ).encode("utf-8")
            encoded = quote(path, safe="/")
            response = self._request(
                "PUT",
                f"{self.api}/contents/{encoded}",
                json={
                    "message": "Index historical SXF hydration batch",
                    "content": base64.b64encode(updated).decode("ascii"),
                    "sha": sha,
                    "branch": ARCHIVE_BRANCH,
                },
            )
            if response.status_code == 200:
                return
            if response.status_code in {409, 422} and attempt < 3:
                time.sleep(1.0 + attempt)
                continue
            raise HydrationError(f"manifest update failed: HTTP {response.status_code} {response.text[:300]}")
        raise HydrationError("manifest update exhausted retries")


class SupabaseSource:
    def __init__(self, url: str, key: str) -> None:
        self.base = url.rstrip("/")
        if not self.base or not key:
            raise HydrationError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
        self.session = requests.Session()
        self.session.headers.update({
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
        })

    def _get(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        response = self.session.get(f"{self.base}/rest/v1/{table}", params=params, timeout=30)
        if response.status_code != 200:
            raise HydrationError(f"Supabase {table} read failed: HTTP {response.status_code} {response.text[:300]}")
        payload = response.json()
        if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
            raise HydrationError(f"Supabase {table} returned invalid payload")
        return payload

    def fixture(self, match_hash: str) -> dict[str, Any]:
        rows = self._get("fixtures", {
            "select": "match_id_hash,league,home_team,away_team,kickoff_utc",
            "match_id_hash": f"eq.{match_hash}",
            "limit": "2",
        })
        if len(rows) != 1:
            raise HydrationError(f"canonical fixture lookup for {match_hash} returned {len(rows)} rows")
        return rows[0]

    def table_history(self, table: str, timestamp_field: str, match_hash: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = self._get(table, {
                "select": "*",
                "match_id_hash": f"eq.{match_hash}",
                "order": f"{timestamp_field}.asc",
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


def hydrate(request_path: Path) -> dict[str, Any]:
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    request_id, backfill_at, cases = _validate_request(payload)

    supabase = SupabaseSource(
        os.environ.get("SUPABASE_URL", ""),
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""),
    )
    github = GitHubWriter(os.environ.get("GITHUB_TOKEN", "") or os.environ.get("GH_TOKEN", ""))

    receipts: list[dict[str, Any]] = []
    manifest_entries: list[dict[str, Any]] = []

    for item in cases:
        case_id = str(item["case_id"]).strip()
        case_hash = str(item["case_hash"]).strip().lower()
        canonical_hash = str(item["canonical_hash"]).strip().lower()
        prediction_at = _parse_utc(str(item["prediction_at"]), f"{case_id}.prediction_at")
        kickoff_at = _parse_utc(str(item["kickoff_at"]), f"{case_id}.kickoff_at")

        case_path = f"{ARCHIVE_ROOT}/cases/2026/10/03/{case_id}"
        existing_case = github.read(f"{case_path}/case.json")
        if existing_case is None:
            raise HydrationError(f"{case_id}: archived case.json missing")
        case_doc = json.loads(existing_case[0].decode("utf-8"))
        if str(case_doc.get("case_id") or "") != case_id:
            raise HydrationError(f"{case_id}: archived case_id mismatch")
        if str((case_doc.get("match") or {}).get("match_id_hash") or "").lower() != case_hash:
            raise HydrationError(f"{case_id}: archived case hash mismatch")
        if _parse_utc(str((case_doc.get("match") or {}).get("kickoff_at") or ""), f"{case_id}.archive kickoff") != kickoff_at:
            raise HydrationError(f"{case_id}: archived kickoff mismatch")

        fixture = supabase.fixture(canonical_hash)
        if str(fixture.get("home_team") or "") != str(item["canonical_home"]):
            raise HydrationError(f"{case_id}: canonical home mismatch")
        if str(fixture.get("away_team") or "") != str(item["canonical_away"]):
            raise HydrationError(f"{case_id}: canonical away mismatch")
        if str(fixture.get("league") or "") != str(item["canonical_league"]):
            raise HydrationError(f"{case_id}: canonical league mismatch")
        if _parse_utc(str(fixture.get("kickoff_utc") or ""), f"{case_id}.fixture kickoff") != kickoff_at:
            raise HydrationError(f"{case_id}: canonical kickoff mismatch")

        flattened: list[dict[str, Any]] = []
        row_counts: dict[str, int] = {}
        raw_counts: dict[str, int] = {}
        first_seen: str | None = None
        last_seen: str | None = None
        pre_prediction_rows = 0
        post_prediction_pre_kickoff_rows = 0

        for table, timestamp_field in SOURCE_TABLES:
            raw_rows = supabase.table_history(table, timestamp_field, canonical_hash)
            raw_counts[table] = len(raw_rows)
            kept: list[dict[str, Any]] = []
            for row in raw_rows:
                ts = _row_timestamp(row)
                if ts >= kickoff_at:
                    continue
                copied = dict(row)
                copied["_archive_source_table"] = table
                copied["_archive_source_match_id_hash"] = canonical_hash
                kept.append(copied)
                ts_text = ts.isoformat().replace("+00:00", "Z")
                if first_seen is None or ts_text < first_seen:
                    first_seen = ts_text
                if last_seen is None or ts_text > last_seen:
                    last_seen = ts_text
                if ts <= prediction_at:
                    pre_prediction_rows += 1
                else:
                    post_prediction_pre_kickoff_rows += 1
            if not kept:
                raise HydrationError(f"{case_id}: {table} has no prematch history")
            row_counts[table] = len(kept)
            flattened.extend(kept)

        flattened.sort(key=lambda row: (
            _row_timestamp(row),
            str(row.get("_archive_source_table") or ""),
            str(row.get("id") or ""),
        ))
        if not flattened:
            raise HydrationError(f"{case_id}: no prematch history after cutoff")

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
                "method": "fixture_home_away_kickoff_verified",
                "canonical_fixture": {
                    "home": fixture.get("home_team"),
                    "away": fixture.get("away_team"),
                    "league": fixture.get("league"),
                    "kickoff_at": str(item["kickoff_at"]),
                },
            },
            "timeline": {
                "prediction_at": str(item["prediction_at"]),
                "kickoff_at": str(item["kickoff_at"]),
                "first_snapshot_at": first_seen,
                "last_snapshot_at": last_seen,
                "rows_total": len(flattened),
                "rows_at_or_before_prediction": pre_prediction_rows,
                "rows_after_prediction_before_kickoff": post_prediction_pre_kickoff_rows,
                "row_counts_by_table": row_counts,
                "raw_counts_by_table": raw_counts,
            },
            "artifact": {
                "path": "historical_sxf_snapshots.json.gz",
                "sha256": snapshots_sha,
            },
            "provenance": {
                "source": "SmartXFlow Supabase historical tables",
                "source_tables": [table for table, _ in SOURCE_TABLES],
                "append_only": True,
                "original_case_files_rewritten": False,
            },
        }
        metadata_payload = _canonical_json_bytes(metadata)

        created = []
        if github.create_immutable(
            f"{case_path}/historical_sxf_snapshots.json.gz",
            snapshots_payload,
            f"Hydrate {case_id}: historical SXF snapshots",
        ):
            created.append("historical_sxf_snapshots.json.gz")
        if github.create_immutable(
            f"{case_path}/historical_sxf_snapshots.sha256",
            checksum_payload,
            f"Hydrate {case_id}: historical SXF checksum",
        ):
            created.append("historical_sxf_snapshots.sha256")
        if github.create_immutable(
            f"{case_path}/addenda/historical_sxf_backfill.json",
            metadata_payload,
            f"Hydrate {case_id}: historical SXF provenance",
        ):
            created.append("addenda/historical_sxf_backfill.json")

        # Post-write readback is mandatory; a success response without byte equality is failure.
        remote_snapshots = github.read(f"{case_path}/historical_sxf_snapshots.json.gz")
        remote_checksum = github.read(f"{case_path}/historical_sxf_snapshots.sha256")
        remote_metadata = github.read(f"{case_path}/addenda/historical_sxf_backfill.json")
        if remote_snapshots is None or remote_snapshots[0] != snapshots_payload:
            raise HydrationError(f"{case_id}: historical snapshots readback mismatch")
        if remote_checksum is None or remote_checksum[0] != checksum_payload:
            raise HydrationError(f"{case_id}: historical checksum readback mismatch")
        if remote_metadata is None or remote_metadata[0] != metadata_payload:
            raise HydrationError(f"{case_id}: historical metadata readback mismatch")

        manifest_entries.append({
            "case_id": case_id,
            "event": "HISTORICAL_SXF_BACKFILL",
            "event_key": backfill_at,
            "archive_path": case_path,
            "archive_schema_version": 1,
            "match_id_hash": case_hash,
            "canonical_source_hash": canonical_hash,
            "prediction_at": str(item["prediction_at"]),
            "settlement_status": str((case_doc.get("settlement") or {}).get("status") or "UNKNOWN"),
            "historical_snapshots_sha256": snapshots_sha,
            "historical_snapshot_rows": len(flattened),
        })
        receipts.append({
            "case_id": case_id,
            "archived_case_hash": case_hash,
            "canonical_source_hash": canonical_hash,
            "rows": len(flattened),
            "pre_prediction_rows": pre_prediction_rows,
            "post_prediction_pre_kickoff_rows": post_prediction_pre_kickoff_rows,
            "sha256": snapshots_sha,
            "created": created,
        })

    github.append_manifest_entries(manifest_entries)
    return {
        "status": "HYDRATED",
        "request_id": request_id,
        "requested": len(cases),
        "hydrated": len(receipts),
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
