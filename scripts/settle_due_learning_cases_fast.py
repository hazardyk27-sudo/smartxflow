#!/usr/bin/env python3
"""Fast fail-closed postmatch finalizer.

All due cases are discovered and fully preflighted first. If any case is invalid,
all errors are returned together and no archive write is attempted. A clean batch
is then finalized through one atomic SSH clone/commit/push when the canonical SSH
backend is active.
"""
from __future__ import annotations

import argparse
from datetime import timedelta
import json
from pathlib import Path
import sys
import tempfile
from typing import Any

from learning_archive.exporter import ArchiveFinalizationError, LearningArchiveExporter
from learning_archive.outbox import load_dotenv_literal
from learning_archive.result_source import ResultSourceError, fetch_finished_result
from learning_archive.settlement import SettlementError, build_settlement, prepare_final_snapshots
from learning_archive.supabase_source import LearningArchiveSourceError
from scripts.enqueue_due_learning_revisit import export_archive_snapshot
from scripts.settle_due_learning_cases import (
    ARCHIVE_BRANCH,
    DEFAULT_OVERRIDE_DIR,
    DEFAULT_QUEUE,
    DEFAULT_ROOT,
    PostmatchSettlementError,
    _assert_production_checkout,
    _case_from_event,
    _eligible_for_automatic_finalization,
    _finalization_history,
    _load_overrides,
    _manifest_state,
    _parse_utc,
    _read_queue,
    _result_dict,
    _run,
    _write_queue,
    utc_now_iso,
)


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

    _run(["git", "fetch", "origin", ARCHIVE_BRANCH], cwd=app_root)
    with tempfile.TemporaryDirectory(prefix="sxf-postmatch-fast-") as tmp:
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

        discovered = 0
        result_pending = 0
        discovery_errors: list[dict[str, str]] = []
        for case_id, event in sorted(latest.items()):
            if case_id in finalized or case_id in settlements:
                continue
            if not _eligible_for_automatic_finalization(event):
                continue
            try:
                _, case_doc, _ = _case_from_event(archive_root, event)
                kickoff = _parse_utc(
                    (case_doc.get("match") or {}).get("kickoff_at"),
                    f"{case_id}.kickoff_at",
                )
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
            except (KeyError, OSError, ValueError, ResultSourceError, RuntimeError) as exc:
                discovery_errors.append({"case_id": case_id, "error": str(exc)})

        # Persist result discovery once, not after every case. A crash after this
        # point remains retryable with the exact immutable result rows.
        _write_queue(queue_file, queue)

        prepared: list[tuple[str, dict[str, Any], list[dict[str, Any]], dict[str, Any]]] = []
        preflight_errors: list[dict[str, str]] = list(discovery_errors)
        for case_id in sorted(settlements):
            event = latest.get(case_id)
            if not _eligible_for_automatic_finalization(event):
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
                prepared.append((case_id, final_case, snapshots, settlement))
            except (
                KeyError,
                OSError,
                TypeError,
                ValueError,
                SettlementError,
                LearningArchiveSourceError,
                RuntimeError,
            ) as exc:
                preflight_errors.append({"case_id": case_id, "error": str(exc)})

        if preflight_errors:
            output = {
                "status": "POSTMATCH_PREFLIGHT_FAIL",
                "discovered_results": discovered,
                "result_pending": result_pending,
                "prepared": len(prepared),
                "failed": len(preflight_errors),
                "remaining_queue": len(settlements),
                "pruned_legacy": pruned_legacy,
                "errors": preflight_errors,
            }
            raise PostmatchSettlementError(json.dumps(output, ensure_ascii=False, sort_keys=True))

        exporter = LearningArchiveExporter.from_env()
        try:
            finalized_results = exporter.finalize_cases(
                [(final_case, snapshots) for _, final_case, snapshots, _ in prepared]
            )
        except ArchiveFinalizationError as exc:
            raise PostmatchSettlementError(f"batch archive finalization failed: {exc}") from exc

        if len(finalized_results) != len(prepared):
            raise PostmatchSettlementError("batch archive result count mismatch")

        done: list[dict[str, Any]] = []
        for (case_id, final_case, _snapshots, settlement), finalized_result in zip(prepared, finalized_results):
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

        # One durable queue mutation after the atomic archive batch.
        _write_queue(queue_file, queue)

    return {
        "status": "POSTMATCH_DONE",
        "discovered_results": discovered,
        "result_pending": result_pending,
        "finalized": len(done),
        "failed": 0,
        "remaining_queue": len(queue["settlements"]),
        "pruned_legacy": pruned_legacy,
        "archive_commits": sorted({row["archive_commit"] for row in done}),
        "cases": done,
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
