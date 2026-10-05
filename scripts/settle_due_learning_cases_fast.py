#!/usr/bin/env python3
"""Fail-closed, batch-first Learning Archive postmatch finalizer.

The timer performs one remote archive refresh, one aggregate preflight, one
batched result lookup, one batched history lookup, and (when work is ready) one
atomic archive write. Case-local failures stay retryable without forcing healthy
cases to be reprocessed on the next run.
"""
from __future__ import annotations

import argparse
from datetime import timedelta
import gzip
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from typing import Any

from learning_archive.exporter import ArchiveFinalizationError, LearningArchiveExporter
from learning_archive.github_backend import GitHubArchiveBackend
from learning_archive.outbox import load_dotenv_literal
from learning_archive.result_source import ResultSourceError, fetch_finished_results
from learning_archive.settlement import SettlementError, build_settlement, prepare_final_snapshots
from learning_archive.ssh_batch_backend import GitSshBatchArchiveBackend
from learning_archive.supabase_source import (
    LearningArchiveHistoryPayload,
    LearningArchiveSourceError,
    read_learning_archive_match_histories,
)
from scripts.enqueue_due_learning_revisit import export_archive_snapshot
from scripts.settle_due_learning_cases import (
    ARCHIVE_BRANCH,
    DEFAULT_OVERRIDE_DIR,
    DEFAULT_QUEUE,
    DEFAULT_ROOT,
    PostmatchSettlementError,
    _archived_capture_history,
    _assert_production_checkout,
    _case_from_event,
    _eligible_for_automatic_finalization,
    _load_overrides,
    _manifest_state,
    _parse_utc,
    _read_queue,
    _result_dict,
    _run,
    _write_queue,
    utc_now_iso,
)


REQUIRED_FINAL_FILES = (
    "case.json",
    "evidence.json",
    "settlement.json",
    "sxf_snapshots.json.gz",
    "checksums.sha256",
)
CHECKSUM_PAYLOAD_FILES = {
    "case.json",
    "evidence.json",
    "settlement.json",
    "sxf_snapshots.json.gz",
}
LEGACY_LIFECYCLE_EVENTS = {"SETTLED_PENDING_HISTORY"}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _audit_finalized_package(case_dir: Path, event: dict[str, Any]) -> list[str]:
    """Validate a FINALIZED receipt against the fetched canonical remote snapshot."""
    errors: list[str] = []
    for name in REQUIRED_FINAL_FILES:
        if not (case_dir / name).is_file():
            errors.append(f"{name} missing")
    if errors:
        return errors

    checksums_path = case_dir / "checksums.sha256"
    checksum_entries: dict[str, str] = {}
    try:
        for raw in checksums_path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            digest, name = raw.split("  ", 1)
            checksum_entries[name] = digest
    except (OSError, ValueError):
        return ["checksums.sha256 malformed"]

    if set(checksum_entries) != CHECKSUM_PAYLOAD_FILES:
        errors.append(
            "checksums.sha256 payload set mismatch: "
            + ",".join(sorted(checksum_entries))
        )
    for name in CHECKSUM_PAYLOAD_FILES:
        path = case_dir / name
        if not path.is_file():
            continue
        expected = checksum_entries.get(name)
        actual = _sha256(path.read_bytes())
        if expected != actual:
            errors.append(f"{name} checksum mismatch")

    manifest_summary = str(event.get("checksum_summary") or "").strip()
    actual_summary = _sha256(checksums_path.read_bytes())
    if not manifest_summary:
        errors.append("FINALIZED manifest checksum_summary missing")
    elif manifest_summary != actual_summary:
        errors.append("FINALIZED manifest checksum_summary mismatch")

    try:
        case_doc = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
        evidence = json.loads((case_dir / "evidence.json").read_text(encoding="utf-8"))
        settlement = json.loads((case_dir / "settlement.json").read_text(encoding="utf-8"))
        if not isinstance(case_doc, dict):
            errors.append("case.json invalid")
        if not isinstance(evidence, list):
            errors.append("evidence.json invalid")
        if not isinstance(settlement, dict):
            errors.append("settlement.json invalid")
        elif str(settlement.get("status") or "").upper() == "PENDING":
            errors.append("settlement.json is still PENDING")
        with gzip.open(case_dir / "sxf_snapshots.json.gz", "rt", encoding="utf-8") as handle:
            snapshots = json.load(handle)
        if not isinstance(snapshots, list) or not snapshots:
            errors.append("sxf_snapshots.json.gz empty/invalid")
    except (OSError, json.JSONDecodeError):
        errors.append("finalized payload parse/decompression failed")
    return sorted(set(errors))


def _audit_remote_finalized_packages(
    archive_root: Path,
    latest: dict[str, dict[str, Any]],
    finalized: set[str],
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for case_id in sorted(finalized):
        event = latest.get(case_id)
        if not event or event.get("event") != "FINALIZED":
            errors.append({"case_id": case_id, "error": "FINALIZED receipt missing from latest manifest state"})
            continue
        archive_path = str(event.get("archive_path") or "").strip()
        if not archive_path:
            errors.append({"case_id": case_id, "error": "FINALIZED manifest archive_path missing"})
            continue
        case_errors = _audit_finalized_package(archive_root / archive_path, event)
        for error in case_errors:
            errors.append({"case_id": case_id, "error": error})
    return errors


def _backend_preflight(app_root: Path, exporter: LearningArchiveExporter) -> dict[str, Any]:
    """One environment preflight for remote presence, gitignore and durable backend."""
    fetched = _run(["git", "rev-parse", f"origin/{ARCHIVE_BRANCH}"], cwd=app_root).stdout.strip()
    if len(fetched) != 40:
        raise PostmatchSettlementError("Learning Archive remote branch did not resolve to a commit")

    ignored = (
        _run(
            ["git", "check-ignore", "-q", "--", "learning_archive_data/cases/__preflight__/settlement.json"],
            cwd=app_root,
            check=False,
        ).returncode
        == 0
    )
    backend = exporter.backend
    if getattr(backend, "durable", False) is False:
        raise PostmatchSettlementError("Learning Archive backend is not durable")
    if ignored and not isinstance(backend, (GitSshBatchArchiveBackend, GitHubArchiveBackend)):
        raise PostmatchSettlementError(
            "global gitignore hides archive JSON but active backend has no ignore-safe write guarantee"
        )

    return {
        "archive_remote_head": fetched,
        "backend": type(backend).__name__,
        "gitignore_json_ignored": ignored,
        "gitignore_safe": (not ignored) or isinstance(backend, (GitSshBatchArchiveBackend, GitHubArchiveBackend)),
    }


def _flatten_history(payload: LearningArchiveHistoryPayload) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for table_name, table_rows in payload.histories.items():
        for row in table_rows:
            copied = dict(row)
            copied["_archive_source_table"] = table_name
            rows.append(copied)
    return rows


def _select_finalization_history(
    case_dir: Path,
    match_hash: str,
    db_histories: dict[str, LearningArchiveHistoryPayload],
) -> tuple[list[dict[str, Any]], str]:
    """Choose DB history when available; otherwise directly use durable PRE capture."""
    payload = db_histories.get(match_hash)
    if payload is not None:
        rows = _flatten_history(payload)
        if rows:
            return rows, "SXF_DB_BATCH"
    return _archived_capture_history(case_dir, match_hash), "ARCHIVE_CAPTURE_FALLBACK"


def _legacy_event(event: dict[str, Any] | None) -> bool:
    return bool(event and event.get("event") in LEGACY_LIFECYCLE_EVENTS)


def settle_due_cases_fast(
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

    # One archive network refresh for all package/manifest preflight work.
    _run(["git", "fetch", "--quiet", "origin", ARCHIVE_BRANCH], cwd=app_root)
    exporter = LearningArchiveExporter.from_env()
    environment = _backend_preflight(app_root, exporter)

    with tempfile.TemporaryDirectory(prefix="sxf-postmatch-fast-") as tmp:
        archive_root = Path(tmp) / "archive"
        export_archive_snapshot(app_root, archive_root)
        latest, finalized = _manifest_state(archive_root)

        # Existing FINALIZED receipts are trusted only after the package fetched
        # from canonical GitHub verifies as a complete checksum-consistent unit.
        finalized_integrity_errors = _audit_remote_finalized_packages(archive_root, latest, finalized)
        if finalized_integrity_errors:
            output = {
                "status": "POSTMATCH_REMOTE_INTEGRITY_FAIL",
                "environment": environment,
                "failed": len(finalized_integrity_errors),
                "errors": finalized_integrity_errors,
            }
            raise PostmatchSettlementError(json.dumps(output, ensure_ascii=False, sort_keys=True))

        queue = _read_queue(queue_file)
        settlements = queue["settlements"]
        legacy_settlements = queue.setdefault("legacy_settlements", {})

        legacy_cases = sorted(
            case_id for case_id, event in latest.items() if _legacy_event(event)
        )
        pruned_finalized = 0
        moved_legacy = 0
        pruned_unrelated = 0
        for case_id in list(settlements):
            event = latest.get(case_id)
            if case_id in finalized:
                settlements.pop(case_id, None)
                pruned_finalized += 1
            elif _legacy_event(event):
                legacy_settlements[case_id] = settlements.pop(case_id)
                moved_legacy += 1
            elif not _eligible_for_automatic_finalization(event):
                settlements.pop(case_id, None)
                pruned_unrelated += 1

        discovery_errors: list[dict[str, str]] = []
        due_cases: dict[str, tuple[Path, dict[str, Any], list[dict[str, Any]]]] = {}
        unresolved_hashes: list[str] = []
        hash_to_case_ids: dict[str, list[str]] = {}
        discovered = 0
        result_pending = 0

        # Discover all due cases locally first; no per-case network calls.
        for case_id, event in sorted(latest.items()):
            if case_id in finalized or case_id in settlements or _legacy_event(event):
                continue
            if not _eligible_for_automatic_finalization(event):
                continue
            try:
                case_dir, case_doc, evidence = _case_from_event(archive_root, event)
                kickoff = _parse_utc(
                    (case_doc.get("match") or {}).get("kickoff_at"),
                    f"{case_id}.kickoff_at",
                )
                if current_time < kickoff + timedelta(minutes=minimum_minutes_after_kickoff):
                    continue
                due_cases[case_id] = (case_dir, case_doc, evidence)
                if case_id in overrides:
                    settlements[case_id] = dict(overrides[case_id])
                    discovered += 1
                else:
                    match_hash = str((case_doc.get("match") or {}).get("match_id_hash") or "").strip().lower()
                    if not match_hash:
                        raise PostmatchSettlementError("match_id_hash is missing")
                    if match_hash not in hash_to_case_ids:
                        unresolved_hashes.append(match_hash)
                        hash_to_case_ids[match_hash] = []
                    hash_to_case_ids[match_hash].append(case_id)
            except (KeyError, OSError, ValueError, RuntimeError) as exc:
                discovery_errors.append({"case_id": case_id, "error": str(exc)})

        if unresolved_hashes:
            try:
                batch_results = fetch_finished_results(unresolved_hashes)
                for match_hash, case_ids in hash_to_case_ids.items():
                    match_result = batch_results.get(match_hash)
                    if match_result is None:
                        result_pending += len(case_ids)
                        continue
                    row = _result_dict(match_result)
                    for case_id in case_ids:
                        settlements[case_id] = dict(row)
                        discovered += 1
            except ResultSourceError as exc:
                for match_hash in unresolved_hashes:
                    for case_id in hash_to_case_ids[match_hash]:
                        discovery_errors.append({"case_id": case_id, "error": f"result batch: {exc}"})

        # Persist all newly discovered immutable result rows in one atomic queue mutation.
        _write_queue(queue_file, queue)

        candidate_case_ids = [
            case_id
            for case_id in sorted(settlements)
            if _eligible_for_automatic_finalization(latest.get(case_id))
        ]

        # Read all surviving DB histories in a table-batched query. Missing fixture
        # or history simply omits that hash so the archived capture is selected
        # directly, without exception-first fallback behavior.
        candidate_hashes: list[str] = []
        candidate_meta: dict[str, tuple[Path, dict[str, Any], list[dict[str, Any]]]] = {}
        preflight_errors: list[dict[str, str]] = list(discovery_errors)
        for case_id in candidate_case_ids:
            try:
                meta = due_cases.get(case_id)
                if meta is None:
                    meta = _case_from_event(archive_root, latest[case_id])
                candidate_meta[case_id] = meta
                match_hash = str((meta[1].get("match") or {}).get("match_id_hash") or "").strip().lower()
                if not match_hash:
                    raise PostmatchSettlementError("match_id_hash is missing")
                if match_hash not in candidate_hashes:
                    candidate_hashes.append(match_hash)
            except (KeyError, OSError, ValueError, RuntimeError) as exc:
                preflight_errors.append({"case_id": case_id, "error": str(exc)})

        db_histories: dict[str, LearningArchiveHistoryPayload] = {}
        history_batch_error: str | None = None
        if candidate_hashes:
            try:
                db_histories = read_learning_archive_match_histories(candidate_hashes)
            except LearningArchiveSourceError as exc:
                # The canonical archived PRE capture is already durable and is a
                # valid fail-safe source. Transport failure is surfaced in output
                # while cases can still finalize from verified archive evidence.
                history_batch_error = str(exc)
                db_histories = {}

        prepared: list[tuple[str, dict[str, Any], list[dict[str, Any]], dict[str, Any], str]] = []
        fallback_count = 0
        db_history_count = 0
        for case_id in candidate_case_ids:
            if case_id not in candidate_meta:
                continue
            try:
                case_dir, case_doc, evidence = candidate_meta[case_id]
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

                match_hash = str(final_case["match"]["match_id_hash"]).strip().lower()
                source_rows, history_source = _select_finalization_history(
                    case_dir,
                    match_hash,
                    db_histories,
                )
                snapshots = prepare_final_snapshots(final_case, source_rows)

                # Package/checksum/validator validation belongs to the single
                # preflight phase, before healthy cases reach the durable writer.
                exporter._prepare_finalization(final_case, snapshots)
                prepared.append((case_id, final_case, snapshots, settlement, history_source))
                if history_source == "SXF_DB_BATCH":
                    db_history_count += 1
                else:
                    fallback_count += 1
            except (
                KeyError,
                OSError,
                TypeError,
                ValueError,
                SettlementError,
                ArchiveFinalizationError,
                PostmatchSettlementError,
                RuntimeError,
            ) as exc:
                preflight_errors.append({"case_id": case_id, "error": str(exc)})

        done: list[dict[str, Any]] = []
        if prepared:
            try:
                finalized_results = exporter.finalize_cases(
                    [(final_case, snapshots) for _, final_case, snapshots, _, _ in prepared]
                )
            except ArchiveFinalizationError as exc:
                raise PostmatchSettlementError(f"batch archive finalization failed: {exc}") from exc

            if len(finalized_results) != len(prepared):
                raise PostmatchSettlementError("batch archive result count mismatch")

            for (
                case_id,
                final_case,
                _snapshots,
                settlement,
                history_source,
            ), finalized_result in zip(prepared, finalized_results):
                done.append({
                    "case_id": case_id,
                    "decision": final_case["prediction"]["decision"],
                    "settlement_status": settlement["status"],
                    "hypothetical_result": settlement.get("hypothetical_result"),
                    "final_score": settlement["final_score"],
                    "archive_commit": finalized_result.archive_commit,
                    "checksum_summary": finalized_result.checksum_summary,
                    "history_source": history_source,
                    "status": finalized_result.status,
                })
                settlements.pop(case_id, None)

        # Healthy finalized cases are removed once. Failed cases remain retryable,
        # so the next timer run resumes only the unresolved subset.
        _write_queue(queue_file, queue)

    all_errors = preflight_errors
    if all_errors and done:
        status = "POSTMATCH_PARTIAL"
    elif all_errors:
        status = "POSTMATCH_PREFLIGHT_FAIL"
    else:
        status = "POSTMATCH_DONE"

    return {
        "status": status,
        "environment": environment,
        "discovered_results": discovered,
        "result_pending": result_pending,
        "prepared": len(prepared),
        "finalized": len(done),
        "failed": len(all_errors),
        "remaining_queue": len(queue["settlements"]),
        "legacy_pending_history": len(legacy_cases),
        "moved_legacy_queue": moved_legacy,
        "pruned_finalized_queue": pruned_finalized,
        "pruned_unrelated_queue": pruned_unrelated,
        "history_db_cases": db_history_count,
        "history_archive_fallback_cases": fallback_count,
        "history_batch_error": history_batch_error,
        "archive_commits": sorted({row["archive_commit"] for row in done}),
        "cases": done,
        "errors": all_errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    parser.add_argument("--queue-file", default=str(DEFAULT_QUEUE))
    parser.add_argument("--now", help="Deterministic current timestamp; defaults to UTC now")
    parser.add_argument("--minimum-minutes-after-kickoff", type=int, default=75)
    parser.add_argument("--result-file", help="Optional verified result override JSON for historical backfill")
    parser.add_argument(
        "--result-dir",
        default=str(DEFAULT_OVERRIDE_DIR),
        help="Directory of auditable verified result override JSON files",
    )
    parser.add_argument("--dotenv", help="Production dotenv loaded literally")
    args = parser.parse_args()

    try:
        if args.dotenv:
            load_dotenv_literal(args.dotenv)
        result = settle_due_cases_fast(
            Path(args.root),
            Path(args.queue_file),
            now=args.now or utc_now_iso(),
            minimum_minutes_after_kickoff=args.minimum_minutes_after_kickoff,
            override_file=args.result_file,
            override_dir=Path(args.result_dir) if args.result_dir else None,
        )
    except (OSError, ValueError, PostmatchSettlementError, ResultSourceError) as exc:
        print(f"POSTMATCH_BATCH_FAIL: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "POSTMATCH_DONE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
