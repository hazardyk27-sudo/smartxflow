#!/usr/bin/env python3
"""Automatically settle and finalize recorded Learning Archive cases.

The Hetzner timer is the primary postmatch clock. Finished scores are read from
SmartXFlow's existing live_fixtures table, persisted to a local durable queue,
and only removed after the canonical learning-archive write returns DONE.
Verified external result overrides may be committed as immutable JSON files
when the internal result source is unavailable for a specific historical case.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

from learning_archive.exporter import ArchiveFinalizationError, LearningArchiveExporter
from learning_archive.outbox import load_dotenv_literal
from learning_archive.result_source import MatchResult, ResultSourceError, fetch_finished_result
from learning_archive.settlement import SettlementError, build_settlement, prepare_final_snapshots
from learning_archive.supabase_source import LearningArchiveSourceError, read_learning_archive_match_history
from scripts.enqueue_due_learning_revisit import export_archive_snapshot


ARCHIVE_BRANCH = "learning-archive"
AUTOMATIC_LIFECYCLE_EVENTS = {"RECORDED", "CAPTURED"}
DEFAULT_ROOT = Path(os.environ.get("SMARTXFLOW_ROOT", "/opt/smartxflow"))
DEFAULT_QUEUE = Path(
    os.environ.get(
        "SMARTXFLOW_POSTMATCH_QUEUE",
        "/var/lib/smartxflow-postmatch/settlements.json",
    )
)
DEFAULT_OVERRIDE_DIR = Path(
    os.environ.get(
        "SMARTXFLOW_POSTMATCH_OVERRIDE_DIR",
        str(DEFAULT_ROOT / "learning_archive_result_overrides"),
    )
)


class PostmatchSettlementError(RuntimeError):
    pass


def _parse_utc(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise PostmatchSettlementError(f"{field} must be a non-empty ISO-8601 datetime")
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise PostmatchSettlementError(f"{field} must be valid ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PostmatchSettlementError(f"{field} must include timezone")
    return parsed.astimezone(timezone.utc)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _run(argv: list[str], *, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(argv, cwd=str(cwd), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "command failed").strip()
        raise PostmatchSettlementError(f"{' '.join(argv[:3])}: {detail}")
    return result


def _assert_production_checkout(app_root: Path) -> None:
    branch = _run(["git", "branch", "--show-current"], cwd=app_root).stdout.strip()
    if branch != "main":
        raise PostmatchSettlementError(f"production branch is {branch!r}, expected 'main'")
    if _run(["git", "diff", "--quiet"], cwd=app_root, check=False).returncode != 0:
        raise PostmatchSettlementError("production tracked worktree is dirty")
    if _run(["git", "diff", "--cached", "--quiet"], cwd=app_root, check=False).returncode != 0:
        raise PostmatchSettlementError("production index is dirty")


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PostmatchSettlementError(f"cannot read JSON {path}") from exc


def _manifest_state(archive_root: Path) -> tuple[dict[str, dict[str, Any]], set[str]]:
    manifest = archive_root / "learning_archive_data" / "manifest.jsonl"
    if not manifest.exists():
        raise PostmatchSettlementError("Learning Archive manifest is missing")
    latest: dict[str, dict[str, Any]] = {}
    finalized: set[str] = set()
    for number, raw in enumerate(manifest.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise PostmatchSettlementError(f"manifest line {number} is invalid JSON") from exc
        if not isinstance(event, dict):
            raise PostmatchSettlementError(f"manifest line {number} must be an object")
        case_id = str(event.get("case_id") or "").strip()
        if not case_id:
            raise PostmatchSettlementError(f"manifest line {number} is missing case_id")
        latest[case_id] = event
        if event.get("event") == "FINALIZED":
            finalized.add(case_id)
    return latest, finalized


def _eligible_for_automatic_finalization(event: dict[str, Any] | None) -> bool:
    return bool(event and event.get("event") in AUTOMATIC_LIFECYCLE_EVENTS)


def _read_queue(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "settlements": {}}
    payload = _load_json(path)
    if not isinstance(payload, dict) or not isinstance(payload.get("settlements"), dict):
        raise PostmatchSettlementError("postmatch queue must contain a settlements object")
    return payload


def _write_queue(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _parse_override_payload(payload: Any, *, source_label: str) -> dict[str, dict[str, Any]]:
    rows = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise PostmatchSettlementError(f"{source_label}: result override must contain a results array")
    result: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise PostmatchSettlementError(f"{source_label}: results[{index}] must be an object")
        case_id = str(row.get("case_id") or "").strip()
        score = str(row.get("final_score") or "").strip()
        observed_at = str(row.get("observed_at") or "").strip()
        source = str(row.get("source") or "verified settlement override").strip()
        if not case_id or not score or not observed_at:
            raise PostmatchSettlementError(
                f"{source_label}: results[{index}] is missing case_id/final_score/observed_at"
            )
        _parse_utc(observed_at, f"{source_label}.results[{index}].observed_at")
        if case_id in result:
            raise PostmatchSettlementError(f"{source_label}: duplicate override for {case_id}")
        result[case_id] = {
            "case_id": case_id,
            "final_score": score,
            "status": "ft",
            "observed_at": observed_at,
            "source": source,
            "source_url": row.get("source_url"),
        }
    return result


def _load_overrides(path: str | None, override_dir: Path | None) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    paths: list[Path] = []
    if override_dir and override_dir.exists():
        if not override_dir.is_dir():
            raise PostmatchSettlementError(f"result override directory is not a directory: {override_dir}")
        paths.extend(sorted(override_dir.glob("*.json")))
    if path:
        paths.append(Path(path))

    for candidate in paths:
        parsed = _parse_override_payload(_load_json(candidate), source_label=str(candidate))
        for case_id, row in parsed.items():
            existing = merged.get(case_id)
            if existing is not None and existing != row:
                raise PostmatchSettlementError(f"conflicting result overrides for {case_id}")
            merged[case_id] = row
    return merged


def _case_from_event(archive_root: Path, event: dict[str, Any]) -> tuple[Path, dict[str, Any], list[dict[str, Any]]]:
    archive_path = str(event.get("archive_path") or "").strip()
    if not archive_path:
        raise PostmatchSettlementError("manifest event is missing archive_path")
    case_dir = archive_root / archive_path
    case_doc = _load_json(case_dir / "case.json")
    evidence = _load_json(case_dir / "evidence.json")
    if not isinstance(case_doc, dict) or not isinstance(evidence, list):
        raise PostmatchSettlementError(f"invalid case/evidence payload for {archive_path}")
    return case_dir, case_doc, evidence


def _result_dict(result: MatchResult) -> dict[str, Any]:
    return {
        "final_score": result.final_score,
        "status": result.status,
        "observed_at": result.observed_at,
        "source": result.source,
        "source_url": None,
    }


def _stored_history(match_id_hash: str) -> list[dict[str, Any]]:
    payload = read_learning_archive_match_history(match_id_hash)
    flattened: list[dict[str, Any]] = []
    for table_name, rows in payload.histories.items():
        for row in rows:
            copied = dict(row)
            copied["_archive_source_table"] = table_name
            flattened.append(copied)
    if not flattened:
        raise PostmatchSettlementError(f"no stored SXF history found for selected match {match_id_hash}")
    return flattened


def _archived_capture_history(case_dir: Path, match_id_hash: str) -> list[dict[str, Any]]:
    """Load the newest durable prematch capture when live storage has aged out.

    Each CAPTURED file contains the complete stored SXF history available as of its
    immutable observed_at. Using the newest readable capture preserves the richest
    prematch history without fabricating later rows.
    """
    capture_dir = case_dir / "captures"
    candidates = sorted(capture_dir.glob("*.json.gz"), reverse=True) if capture_dir.is_dir() else []
    if not candidates:
        raise PostmatchSettlementError(f"no archived prematch captures exist for {match_id_hash}")

    expected_hash = str(match_id_hash or "").strip().lower()
    for capture in candidates:
        try:
            with gzip.open(capture, "rt", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise PostmatchSettlementError(f"cannot read archived prematch capture {capture.name}") from exc
        if not isinstance(payload, list) or not payload:
            raise PostmatchSettlementError(f"archived prematch capture {capture.name} is empty or invalid")

        rows: list[dict[str, Any]] = []
        for index, row in enumerate(payload):
            if not isinstance(row, dict):
                raise PostmatchSettlementError(f"archived prematch capture {capture.name}[{index}] is not an object")
            copied = dict(row)
            row_hash = str(copied.get("match_id_hash") or "").strip().lower()
            if row_hash and row_hash != expected_hash:
                raise PostmatchSettlementError(
                    f"archived prematch capture {capture.name}[{index}] belongs to a different match"
                )
            rows.append(copied)
        return rows

    raise PostmatchSettlementError(f"no readable archived prematch capture exists for {match_id_hash}")


def _finalization_history(case_dir: Path, match_id_hash: str) -> list[dict[str, Any]]:
    try:
        return _stored_history(match_id_hash)
    except LearningArchiveSourceError:
        return _archived_capture_history(case_dir, match_id_hash)


def settle_due_cases(
    app_root: Path,
    queue_file: Path,
    *,
    now: str,
    minimum_minutes_after_kickoff: int = 75,
    override_file: str | None = None,
    override_dir: Path | None = DEFAULT_OVERRIDE_DIR,
) -> dict[str, Any]:
    _assert_production_checkout(app_root)
    current_time = _parse_utc(now, "now")
    overrides = _load_overrides(override_file, override_dir)

    _run(["git", "fetch", "origin", ARCHIVE_BRANCH], cwd=app_root)
    with tempfile.TemporaryDirectory(prefix="sxf-postmatch-") as tmp:
        archive_root = Path(tmp) / "archive"
        export_archive_snapshot(app_root, archive_root)
        latest, finalized = _manifest_state(archive_root)
        queue = _read_queue(queue_file)
        settlements = queue["settlements"]

        pruned_legacy = 0
        for case_id in list(settlements):
            event = latest.get(case_id)
            if case_id in finalized or not _eligible_for_automatic_finalization(event):
                settlements.pop(case_id, None)
                pruned_legacy += 1
        if pruned_legacy:
            _write_queue(queue_file, queue)

        discovered = 0
        result_pending = 0
        for case_id, event in sorted(latest.items()):
            if case_id in finalized or case_id in settlements:
                continue
            if not _eligible_for_automatic_finalization(event):
                continue
            _, case_doc, _ = _case_from_event(archive_root, event)
            kickoff = _parse_utc((case_doc.get("match") or {}).get("kickoff_at"), f"{case_id}.kickoff_at")
            if current_time < kickoff + timedelta(minutes=minimum_minutes_after_kickoff):
                continue

            if case_id in overrides:
                row = dict(overrides[case_id])
            else:
                match_hash = str((case_doc.get("match") or {}).get("match_id_hash") or "").strip()
                match_result = fetch_finished_result(match_hash)
                if match_result is None:
                    result_pending += 1
                    continue
                row = _result_dict(match_result)

            settlements[case_id] = row
            discovered += 1
            _write_queue(queue_file, queue)

        exporter = LearningArchiveExporter.from_env()
        done: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        for case_id in sorted(list(settlements)):
            event = latest.get(case_id)
            if not _eligible_for_automatic_finalization(event):
                settlements.pop(case_id, None)
                _write_queue(queue_file, queue)
                continue
            try:
                case_dir, case_doc, evidence = _case_from_event(archive_root, event)
                result_row = settlements[case_id]
                settlement = build_settlement(
                    case_doc,
                    final_score=str(result_row.get("final_score") or ""),
                    result_source=str(result_row.get("source") or ""),
                    result_observed_at=str(result_row.get("observed_at") or ""),
                    source_status=str(result_row.get("status") or "ft"),
                )
                if result_row.get("source_url"):
                    settlement["result_source_url"] = str(result_row["source_url"])

                final_case = dict(case_doc)
                final_case["evidence"] = evidence
                final_case["settlement"] = settlement
                provenance = dict(final_case.get("provenance") or {})
                provenance["archive_finalized_at"] = now
                final_case["provenance"] = provenance

                match_hash = str(final_case["match"]["match_id_hash"])
                snapshots = prepare_final_snapshots(
                    final_case,
                    _finalization_history(case_dir, match_hash),
                )
                finalized_result = exporter.finalize_case(final_case, snapshots)
                done.append({
                    "case_id": case_id,
                    "decision": final_case["prediction"]["decision"],
                    "settlement_status": settlement["status"],
                    "hypothetical_result": settlement.get("hypothetical_result"),
                    "final_score": settlement["final_score"],
                    "archive_commit": finalized_result.archive_commit,
                    "checksum_summary": finalized_result.checksum_summary,
                    "status": finalized_result.status,
                })
                settlements.pop(case_id, None)
                _write_queue(queue_file, queue)
            except (KeyError, OSError, ValueError, SettlementError, LearningArchiveSourceError, ArchiveFinalizationError, RuntimeError) as exc:
                errors.append({"case_id": case_id, "error": str(exc)})

    output = {
        "status": "POSTMATCH_DONE" if not errors else "POSTMATCH_PARTIAL_FAILURE",
        "discovered_results": discovered,
        "result_pending": result_pending,
        "finalized": len(done),
        "failed": len(errors),
        "remaining_queue": len(queue["settlements"]),
        "pruned_legacy": pruned_legacy,
        "cases": done,
        "errors": errors,
    }
    if errors:
        raise PostmatchSettlementError(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    parser.add_argument("--queue-file", default=str(DEFAULT_QUEUE))
    parser.add_argument("--now", help="Deterministic current timestamp; defaults to UTC now")
    parser.add_argument("--minimum-minutes-after-kickoff", type=int, default=75)
    parser.add_argument("--result-file", help="Optional verified result override JSON for historical backfill")
    parser.add_argument("--result-dir", default=str(DEFAULT_OVERRIDE_DIR), help="Directory of auditable verified result override JSON files")
    parser.add_argument("--dotenv", help="Production dotenv loaded literally")
    args = parser.parse_args()

    try:
        if args.dotenv:
            load_dotenv_literal(args.dotenv)
        result = settle_due_cases(
            Path(args.root),
            Path(args.queue_file),
            now=args.now or utc_now_iso(),
            minimum_minutes_after_kickoff=args.minimum_minutes_after_kickoff,
            override_file=args.result_file,
            override_dir=Path(args.result_dir) if args.result_dir else None,
        )
    except (OSError, ValueError, PostmatchSettlementError, ResultSourceError) as exc:
        print(f"POSTMATCH_SETTLEMENT_FAIL: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())