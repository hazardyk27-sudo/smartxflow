#!/usr/bin/env python3
"""Repair FINALIZED Learning Archive cases whose settlement.json was not committed.

A historical SSH-writer bug allowed the repository-wide ``*.json`` ignore rule to
hide newly-created settlement.json files from ``git add`` even though the final
package checksum and FINALIZED manifest event were written. This repair is
fail-closed: it reconstructs the deterministic final package from the immutable
case, verified result source, and already-archived final SXF snapshot. Existing
package files/checksums must match exactly or the archive backend rejects the
repair as a conflict.
"""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
import sys
import tempfile
from typing import Any

from learning_archive.exporter import ArchiveFinalizationError, LearningArchiveExporter
from learning_archive.outbox import load_dotenv_literal
from learning_archive.result_source import ResultSourceError, fetch_finished_result
from learning_archive.settlement import SettlementError, build_settlement, prepare_final_snapshots
from scripts.enqueue_due_learning_revisit import export_archive_snapshot
from scripts.settle_due_learning_cases import (
    ARCHIVE_BRANCH,
    DEFAULT_OVERRIDE_DIR,
    DEFAULT_ROOT,
    PostmatchSettlementError,
    _assert_production_checkout,
    _case_from_event,
    _load_overrides,
    _manifest_state,
    _result_dict,
    _run,
    utc_now_iso,
)


class SettlementRepairError(RuntimeError):
    pass


def _load_final_snapshots(case_dir: Path) -> list[dict[str, Any]]:
    path = case_dir / "sxf_snapshots.json.gz"
    if not path.is_file():
        raise SettlementRepairError(f"finalized case is missing {path.name}")
    try:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise SettlementRepairError(f"cannot read finalized SXF snapshot {path}") from exc
    if not isinstance(payload, list) or not payload:
        raise SettlementRepairError(f"finalized SXF snapshot is empty or invalid: {path}")
    for index, row in enumerate(payload):
        if not isinstance(row, dict):
            raise SettlementRepairError(f"finalized SXF snapshot row {index} is not an object")
    return [dict(row) for row in payload]


def repair_missing_settlements(
    app_root: Path,
    *,
    now: str,
    override_dir: Path | None = DEFAULT_OVERRIDE_DIR,
) -> dict[str, Any]:
    _assert_production_checkout(app_root)
    overrides = _load_overrides(None, override_dir)
    _run(["git", "fetch", "origin", ARCHIVE_BRANCH], cwd=app_root)

    repaired: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    with tempfile.TemporaryDirectory(prefix="sxf-settlement-repair-") as tmp:
        archive_root = Path(tmp) / "archive"
        export_archive_snapshot(app_root, archive_root)
        latest, finalized = _manifest_state(archive_root)
        exporter = LearningArchiveExporter.from_env()

        for case_id in sorted(finalized):
            event = latest.get(case_id)
            if not event or event.get("event") != "FINALIZED":
                continue
            try:
                case_dir, case_doc, evidence = _case_from_event(archive_root, event)
                if (case_dir / "settlement.json").is_file():
                    continue

                result_row = overrides.get(case_id)
                if result_row is None:
                    match_hash = str((case_doc.get("match") or {}).get("match_id_hash") or "").strip()
                    match_result = fetch_finished_result(match_hash)
                    if match_result is None:
                        raise SettlementRepairError("finished result is unavailable for settlement repair")
                    result_row = _result_dict(match_result)

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

                snapshots = prepare_final_snapshots(final_case, _load_final_snapshots(case_dir))
                result = exporter.finalize_case(final_case, snapshots)
                repaired.append({
                    "case_id": case_id,
                    "archive_commit": result.archive_commit,
                    "checksum_summary": result.checksum_summary,
                    "status": result.status,
                    "settlement_status": settlement["status"],
                })
            except (
                OSError,
                ValueError,
                SettlementError,
                SettlementRepairError,
                ResultSourceError,
                ArchiveFinalizationError,
                RuntimeError,
            ) as exc:
                errors.append({"case_id": case_id, "error": str(exc)})

    output = {
        "status": "SETTLEMENT_REPAIR_DONE" if not errors else "SETTLEMENT_REPAIR_FAILED",
        "repaired": len(repaired),
        "failed": len(errors),
        "cases": repaired,
        "errors": errors,
    }
    if errors:
        raise SettlementRepairError(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    parser.add_argument("--result-dir", default=str(DEFAULT_OVERRIDE_DIR))
    parser.add_argument("--now", help="Deterministic current timestamp; defaults to UTC now")
    parser.add_argument("--dotenv", help="Production dotenv loaded literally")
    args = parser.parse_args()

    try:
        if args.dotenv:
            load_dotenv_literal(args.dotenv)
        result = repair_missing_settlements(
            Path(args.root),
            now=args.now or utc_now_iso(),
            override_dir=Path(args.result_dir) if args.result_dir else None,
        )
    except (OSError, ValueError, PostmatchSettlementError, SettlementRepairError, ResultSourceError) as exc:
        print(f"SETTLEMENT_REPAIR_FAIL: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
