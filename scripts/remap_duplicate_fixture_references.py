#!/usr/bin/env python3
"""Plan and optionally remap stale fixture-hash references.

Dry-run is the default. The script discovers stale->canonical fixture hashes using
exactly the same physical-identity/canonical-hash logic as
``cleanup_duplicate_fixtures.py`` and then plans reference-table remaps.

Safety rules:
- wrong Supabase project => refuse
- reference-scan errors => refuse
- unexpected stale/canonical coexistence => refuse
- APPLY requires an exact plan digest from a prior dry-run
- special collisions are handled explicitly:
  * moneyway_snapshots: exact logical duplicate snapshots are dropped, then the
    remaining stale rows are remapped
  * volumeshock_alarms: the two alarm states are merged under the canonical row
  * live_fixtures: stale row may be dropped only when all functional fields are
    identical and the canonical row is at least as new
- fixture rows themselves are NOT deleted here; run the separate cleanup audit
  after references are remapped
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.cleanup_duplicate_fixtures import (  # noqa: E402
    REFERENCE_TABLES,
    SUPABASE_URL,
    _headers,
    _validate_target,
    build_reference_map,
    canonical_hash,
    fetch_all_fixtures,
    identity_key,
)

APPLY = os.environ.get("FIXTURE_REMAP_APPLY", "0") == "1"
EXPECTED_PLAN = os.environ.get("FIXTURE_REMAP_EXPECT_PLAN", "").strip()
PAGE_SIZE = 1000


def _hash_filter(value: str) -> str:
    return quote(value, safe="")


def _count_hash(table: str, match_hash: str) -> int:
    url = (
        f"{SUPABASE_URL}/rest/v1/{table}"
        f"?select=match_id_hash&match_id_hash=eq.{_hash_filter(match_hash)}&limit=1"
    )
    response = requests.get(url, headers=_headers("count=exact"), timeout=30)
    response.raise_for_status()
    content_range = response.headers.get("Content-Range", "")
    if "/" in content_range:
        total = content_range.rsplit("/", 1)[1]
        if total.isdigit():
            return int(total)
    payload = response.json() or []
    return len(payload)


def _fetch_hash_rows(table: str, match_hash: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        url = (
            f"{SUPABASE_URL}/rest/v1/{table}"
            f"?select=*&match_id_hash=eq.{_hash_filter(match_hash)}"
            f"&limit={PAGE_SIZE}&offset={offset}"
        )
        response = requests.get(url, headers=_headers(), timeout=30)
        response.raise_for_status()
        page = response.json()
        if not isinstance(page, list):
            raise RuntimeError(f"{table} response is not a list")
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        if offset > 100_000:
            raise RuntimeError(f"{table} pagination safety limit exceeded")
    return rows


def _duplicate_mappings() -> list[tuple[str, str]]:
    fixtures = fetch_all_fixtures()
    groups: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for row in fixtures:
        key = identity_key(row)
        if key:
            groups[key].append(row)

    mapping: dict[str, str] = {}
    for rows in groups.values():
        if len(rows) <= 1:
            continue
        canonical_rows = [
            row for row in rows
            if str(row.get("match_id_hash") or "") == canonical_hash(row)
        ]
        if len(canonical_rows) != 1:
            continue
        keep_hash = str(canonical_rows[0].get("match_id_hash") or "")
        for row in rows:
            stale_hash = str(row.get("match_id_hash") or "")
            if not stale_hash or stale_hash == keep_hash:
                continue
            previous = mapping.get(stale_hash)
            if previous and previous != keep_hash:
                raise RuntimeError(
                    f"stale hash maps to multiple canonicals: {stale_hash} -> "
                    f"{previous},{keep_hash}"
                )
            mapping[stale_hash] = keep_hash
    return sorted(mapping.items())


def _snapshot_identity(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("scraped_at_utc") or ""),
        str(row.get("market") or ""),
        str(row.get("selection") or ""),
    )


def _snapshot_payload(row: dict[str, Any]) -> tuple[Any, Any, Any]:
    return row.get("odds"), row.get("volume"), row.get("share")


def plan_snapshot_collision(
    stale_hash: str,
    canonical_hash_value: str,
    stale_rows: list[dict[str, Any]],
    canonical_rows: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    canonical_by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in canonical_rows:
        canonical_by_key[_snapshot_identity(row)].append(row)

    duplicate_ids: list[int] = []
    for stale in stale_rows:
        key = _snapshot_identity(stale)
        peers = canonical_by_key.get(key, [])
        if not peers:
            continue
        if not any(_snapshot_payload(peer) == _snapshot_payload(stale) for peer in peers):
            errors.append(
                "moneyway_nonidentical_overlap "
                f"hash={stale_hash} key={key[0]}|{key[1]}|{key[2]}"
            )
            continue
        row_id = stale.get("id")
        if not isinstance(row_id, int):
            errors.append(f"moneyway_missing_numeric_id hash={stale_hash}")
            continue
        duplicate_ids.append(row_id)

    if errors:
        return None, errors
    return {
        "kind": "snapshot_dedupe_remap",
        "table": "moneyway_snapshots",
        "stale_hash": stale_hash,
        "canonical_hash": canonical_hash_value,
        "stale_count": len(stale_rows),
        "canonical_count": len(canonical_rows),
        "duplicate_stale_ids": sorted(duplicate_ids),
        "remap_count": len(stale_rows) - len(duplicate_ids),
    }, []


def _parse_history(value: Any) -> list[dict[str, Any]]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except Exception:
            return []
        if isinstance(decoded, list):
            return [item for item in decoded if isinstance(item, dict)]
    return []


def _ts(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


def _dedupe_history(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    for item in items:
        marker = json.dumps(item, sort_keys=True, separators=(",", ":"), default=str)
        if marker in seen:
            continue
        seen.add(marker)
        output.append(item)
    output.sort(key=lambda item: str(item.get("trigger_at") or ""))
    return output


def plan_volumeshock_collision(
    stale_hash: str,
    canonical_hash_value: str,
    stale_rows: list[dict[str, Any]],
    canonical_rows: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, list[str]]:
    if len(stale_rows) != 1 or len(canonical_rows) != 1:
        return None, [
            "volumeshock_expected_one_each "
            f"stale={stale_hash}:{len(stale_rows)} canonical={canonical_hash_value}:{len(canonical_rows)}"
        ]

    stale = stale_rows[0]
    canonical = canonical_rows[0]
    stale_key = (str(stale.get("market") or ""), str(stale.get("selection") or ""))
    canonical_key = (str(canonical.get("market") or ""), str(canonical.get("selection") or ""))
    if stale_key != canonical_key:
        return None, [
            f"volumeshock_key_mismatch stale={stale_hash} canonical={canonical_hash_value}"
        ]

    stale_ts = _ts(stale.get("trigger_at"))
    canonical_ts = _ts(canonical.get("trigger_at"))
    if stale_ts is None or canonical_ts is None:
        return None, [
            f"volumeshock_invalid_trigger_at stale={stale_hash} canonical={canonical_hash_value}"
        ]

    stale_id = stale.get("id")
    canonical_id = canonical.get("id")
    if not isinstance(stale_id, int) or not isinstance(canonical_id, int):
        return None, [
            f"volumeshock_missing_numeric_id stale={stale_hash} canonical={canonical_hash_value}"
        ]

    latest, older = (stale, canonical) if stale_ts > canonical_ts else (canonical, stale)
    history = _parse_history(stale.get("alarm_history")) + _parse_history(canonical.get("alarm_history"))
    if (
        str(older.get("trigger_at") or "") != str(latest.get("trigger_at") or "")
        or older.get("incoming_money") != latest.get("incoming_money")
        or older.get("volume_shock_value") != latest.get("volume_shock_value")
    ):
        history.append({
            "incoming_money": older.get("incoming_money"),
            "trigger_at": older.get("trigger_at"),
            "volume_shock_value": older.get("volume_shock_value"),
        })

    payload = {
        "incoming_money": latest.get("incoming_money"),
        "avg_previous": latest.get("avg_previous"),
        "volume_shock_value": latest.get("volume_shock_value"),
        "trigger_at": latest.get("trigger_at"),
        "alarm_history": _dedupe_history(history),
    }
    return {
        "kind": "volumeshock_merge",
        "table": "volumeshock_alarms",
        "stale_hash": stale_hash,
        "canonical_hash": canonical_hash_value,
        "stale_id": stale_id,
        "canonical_id": canonical_id,
        "merged_payload": payload,
    }, []


def plan_live_fixture_collision(
    stale_hash: str,
    canonical_hash_value: str,
    stale_rows: list[dict[str, Any]],
    canonical_rows: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, list[str]]:
    if len(stale_rows) != 1 or len(canonical_rows) != 1:
        return None, [
            "live_fixture_expected_one_each "
            f"stale={stale_hash}:{len(stale_rows)} canonical={canonical_hash_value}:{len(canonical_rows)}"
        ]

    stale = stale_rows[0]
    canonical = canonical_rows[0]
    ignored = {"id", "match_id_hash", "updated_at"}
    keys = (set(stale) | set(canonical)) - ignored
    differences = sorted(key for key in keys if stale.get(key) != canonical.get(key))
    if differences:
        return None, [
            "live_fixture_functional_difference "
            f"stale={stale_hash} canonical={canonical_hash_value} fields={','.join(differences)}"
        ]

    stale_updated = _ts(stale.get("updated_at"))
    canonical_updated = _ts(canonical.get("updated_at"))
    if stale_updated is None or canonical_updated is None:
        return None, [
            f"live_fixture_invalid_updated_at stale={stale_hash} canonical={canonical_hash_value}"
        ]
    if canonical_updated < stale_updated:
        return None, [
            f"live_fixture_canonical_older stale={stale_hash} canonical={canonical_hash_value}"
        ]

    stale_id = stale.get("id")
    canonical_id = canonical.get("id")
    if not isinstance(stale_id, int) or not isinstance(canonical_id, int):
        return None, [
            f"live_fixture_missing_numeric_id stale={stale_hash} canonical={canonical_hash_value}"
        ]

    return {
        "kind": "live_fixture_drop_stale",
        "table": "live_fixtures",
        "stale_hash": stale_hash,
        "canonical_hash": canonical_hash_value,
        "stale_id": stale_id,
        "canonical_id": canonical_id,
        "stale_updated_at": stale.get("updated_at"),
        "canonical_updated_at": canonical.get("updated_at"),
    }, []


def build_plan() -> tuple[list[dict[str, Any]], list[str]]:
    mappings = _duplicate_mappings()
    refs, reference_errors = build_reference_map([stale for stale, _ in mappings])
    if reference_errors:
        return [], ["reference_scan_failed:" + ",".join(reference_errors)]

    operations: list[dict[str, Any]] = []
    blocked: list[str] = []
    for stale_hash, canonical_hash_value in mappings:
        for table in sorted(refs.get(stale_hash, [])):
            stale_count = _count_hash(table, stale_hash)
            if stale_count == 0:
                continue
            canonical_count = _count_hash(table, canonical_hash_value)
            if canonical_count == 0:
                operations.append({
                    "kind": "remap",
                    "table": table,
                    "stale_hash": stale_hash,
                    "canonical_hash": canonical_hash_value,
                    "stale_count": stale_count,
                })
                continue

            stale_rows = _fetch_hash_rows(table, stale_hash)
            canonical_rows = _fetch_hash_rows(table, canonical_hash_value)
            if len(stale_rows) != stale_count or len(canonical_rows) != canonical_count:
                blocked.append(
                    f"count_mismatch table={table} stale={stale_hash} canonical={canonical_hash_value}"
                )
                continue

            operation: dict[str, Any] | None = None
            errors: list[str] = []
            if table == "moneyway_snapshots":
                operation, errors = plan_snapshot_collision(
                    stale_hash, canonical_hash_value, stale_rows, canonical_rows
                )
            elif table == "volumeshock_alarms":
                operation, errors = plan_volumeshock_collision(
                    stale_hash, canonical_hash_value, stale_rows, canonical_rows
                )
            elif table == "live_fixtures":
                operation, errors = plan_live_fixture_collision(
                    stale_hash, canonical_hash_value, stale_rows, canonical_rows
                )
            else:
                errors = [
                    "unexpected_collision "
                    f"table={table} stale={stale_hash} canonical={canonical_hash_value} "
                    f"stale_count={stale_count} canonical_count={canonical_count}"
                ]

            blocked.extend(errors)
            if operation:
                operations.append(operation)

    operations.sort(
        key=lambda item: (
            str(item.get("stale_hash") or ""),
            str(item.get("table") or ""),
            str(item.get("kind") or ""),
        )
    )
    return operations, blocked


def _plan_digest(operations: list[dict[str, Any]], blocked: list[str]) -> str:
    body = json.dumps(
        {"operations": operations, "blocked": sorted(blocked)},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _patch_hash(table: str, stale_hash: str, canonical_hash_value: str) -> None:
    url = (
        f"{SUPABASE_URL}/rest/v1/{table}"
        f"?match_id_hash=eq.{_hash_filter(stale_hash)}"
    )
    response = requests.patch(
        url,
        headers=_headers("return=minimal"),
        json={"match_id_hash": canonical_hash_value},
        timeout=30,
    )
    if response.status_code not in (200, 204):
        raise RuntimeError(f"PATCH failed table={table} status={response.status_code}")


def _patch_id(table: str, row_id: int, payload: dict[str, Any]) -> None:
    url = f"{SUPABASE_URL}/rest/v1/{table}?id=eq.{row_id}"
    response = requests.patch(
        url, headers=_headers("return=minimal"), json=payload, timeout=30
    )
    if response.status_code not in (200, 204):
        raise RuntimeError(f"PATCH id failed table={table} id={row_id} status={response.status_code}")


def _delete_id(table: str, row_id: int) -> None:
    url = f"{SUPABASE_URL}/rest/v1/{table}?id=eq.{row_id}"
    response = requests.delete(url, headers=_headers("return=minimal"), timeout=30)
    if response.status_code not in (200, 204):
        raise RuntimeError(f"DELETE id failed table={table} id={row_id} status={response.status_code}")


def apply_plan(operations: list[dict[str, Any]]) -> None:
    for operation in operations:
        kind = operation["kind"]
        table = operation["table"]
        stale_hash = operation["stale_hash"]
        canonical_hash_value = operation["canonical_hash"]

        if kind == "remap":
            _patch_hash(table, stale_hash, canonical_hash_value)
        elif kind == "snapshot_dedupe_remap":
            for row_id in operation["duplicate_stale_ids"]:
                _delete_id(table, int(row_id))
            _patch_hash(table, stale_hash, canonical_hash_value)
        elif kind == "volumeshock_merge":
            _patch_id(table, int(operation["canonical_id"]), operation["merged_payload"])
            _delete_id(table, int(operation["stale_id"]))
        elif kind == "live_fixture_drop_stale":
            _delete_id(table, int(operation["stale_id"]))
        else:
            raise RuntimeError(f"unknown operation kind={kind}")

        remaining = _count_hash(table, stale_hash)
        if remaining != 0:
            raise RuntimeError(
                f"post-apply stale rows remain table={table} hash={stale_hash} count={remaining}"
            )


def main() -> int:
    _validate_target()
    operations, blocked = build_plan()
    digest = _plan_digest(operations, blocked)

    counts: dict[str, int] = defaultdict(int)
    for operation in operations:
        counts[operation["kind"]] += 1
        if operation["kind"] == "remap":
            print(
                "FIXTURE_REMAP_PLAN "
                f"table={operation['table']} hash={operation['stale_hash']} "
                f"canonical={operation['canonical_hash']} rows={operation['stale_count']}"
            )
        elif operation["kind"] == "snapshot_dedupe_remap":
            print(
                "FIXTURE_REMAP_SNAPSHOT_PLAN "
                f"hash={operation['stale_hash']} canonical={operation['canonical_hash']} "
                f"delete_duplicates={len(operation['duplicate_stale_ids'])} "
                f"remap_rows={operation['remap_count']}"
            )
        elif operation["kind"] == "volumeshock_merge":
            print(
                "FIXTURE_REMAP_VOLUMESHOCK_PLAN "
                f"hash={operation['stale_hash']} canonical={operation['canonical_hash']} "
                f"stale_id={operation['stale_id']} canonical_id={operation['canonical_id']}"
            )
        elif operation["kind"] == "live_fixture_drop_stale":
            print(
                "FIXTURE_REMAP_LIVE_FIXTURE_DROP_PLAN "
                f"hash={operation['stale_hash']} canonical={operation['canonical_hash']} "
                f"stale_id={operation['stale_id']} canonical_id={operation['canonical_id']}"
            )

    for error in blocked:
        print(f"FIXTURE_REMAP_BLOCKED {error}")

    print(
        "FIXTURE_REMAP_RESULT "
        f"operations={len(operations)} blocked={len(blocked)} "
        f"plain={counts['remap']} snapshots={counts['snapshot_dedupe_remap']} "
        f"volumeshock_merges={counts['volumeshock_merge']} "
        f"live_fixture_drops={counts['live_fixture_drop_stale']} "
        f"apply={int(APPLY)} plan_sha256={digest}"
    )

    if blocked:
        print("FIXTURE_REMAP_REFUSE blocked plan")
        return 2
    if not APPLY:
        return 0
    if not EXPECTED_PLAN or EXPECTED_PLAN != digest:
        print(
            "FIXTURE_REMAP_REFUSE apply requires "
            f"FIXTURE_REMAP_EXPECT_PLAN={digest}"
        )
        return 3

    apply_plan(operations)
    print(f"FIXTURE_REMAP_APPLY_OK plan_sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
