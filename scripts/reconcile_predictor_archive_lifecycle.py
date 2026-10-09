#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any
from zoneinfo import ZoneInfo

from predictor_orchestrator.lifecycle_store import PredictorLifecycleStore
from predictor_orchestrator.store import SQLiteOrchestratorStore


_REPOSITORY = "hazardyk27-sudo/smartxflow"


def _parse_dt(value: str) -> datetime:
    raw = str(value or "").strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RuntimeError("prediction_at must include timezone")
    return parsed


def _fixture_id(row: dict[str, Any]) -> str:
    return str(row.get("fixture_id") or row.get("fixture_uid") or row.get("match_id_hash") or "").strip()


def _case_id(prediction_at: str, fixture_id: str, market: str, selection: str) -> str:
    date = _parse_dt(prediction_at).astimezone(timezone.utc).strftime("%Y%m%d")
    clean_fixture = re.sub(r"[^a-zA-Z0-9]+", "", fixture_id).lower() or "fixture"
    digest = hashlib.sha256(f"{fixture_id}\n{market}\n{selection}".encode("utf-8")).hexdigest()[:10]
    return f"{date}-{clean_fixture}-{digest}"


def _load_manifest(root: Path) -> dict[str, dict[str, Any]]:
    path = root / "manifest.jsonl"
    if not path.is_file():
        raise RuntimeError("Learning Archive manifest.jsonl is missing")
    recorded: dict[str, dict[str, Any]] = {}
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"manifest.jsonl line {line_no} is invalid JSON") from exc
        if not isinstance(row, dict):
            continue
        case_id = str(row.get("case_id") or "").strip()
        event = str(row.get("event") or "").upper()
        if case_id and event == "RECORDED":
            recorded[case_id] = row
    return recorded


def _expected_price(row: dict[str, Any]) -> float | None:
    preference = row.get("preference") if isinstance(row.get("preference"), dict) else {}
    price = preference.get("price")
    if isinstance(price, (int, float)) and not isinstance(price, bool):
        return float(price)
    evidence = row.get("price_evidence") if isinstance(row.get("price_evidence"), dict) else {}
    price = evidence.get("price")
    if isinstance(price, (int, float)) and not isinstance(price, bool):
        return float(price)
    return None


def _verify_case(case_doc: dict[str, Any], stage3_row: dict[str, Any], case_id: str) -> None:
    fixture_id = _fixture_id(stage3_row)
    preference = stage3_row.get("preference") if isinstance(stage3_row.get("preference"), dict) else {}
    prediction = case_doc.get("prediction") if isinstance(case_doc.get("prediction"), dict) else {}
    match = case_doc.get("match") if isinstance(case_doc.get("match"), dict) else {}

    exact = {
        "case_id": (str(case_doc.get("case_id") or ""), case_id),
        "match_id_hash": (str(match.get("match_id_hash") or ""), fixture_id),
        "decision": (str(prediction.get("decision") or "").upper(), str(stage3_row.get("decision") or "").upper()),
        "market": (str(prediction.get("market") or ""), str(preference.get("market") or "")),
        "selection": (str(prediction.get("selection") or ""), str(preference.get("selection") or "")),
        "prediction_at": (str(prediction.get("prediction_at") or ""), str(stage3_row.get("prediction_at") or "")),
        "grade": (str(prediction.get("grade") or ""), str(stage3_row.get("grade") or "")),
        "execution_type": (str(prediction.get("execution_type") or ""), str(stage3_row.get("execution_type") or "")),
        "divergence_state": (str(prediction.get("divergence_state") or ""), str(stage3_row.get("divergence_state") or "")),
        "counter_severity": (str(prediction.get("counter_severity") or ""), str(stage3_row.get("counter_severity") or "")),
        "stage2_verdict": (str(prediction.get("stage2_verdict") or ""), str(stage3_row.get("stage2_verdict") or "")),
        "rationale": (str(prediction.get("rationale") or ""), str(stage3_row.get("rationale") or "")),
        "counterargument": (
            str(prediction.get("counterargument") or ""),
            str(stage3_row.get("strongest_counterargument") or ""),
        ),
    }
    for field, (actual, expected) in exact.items():
        if actual != expected:
            raise RuntimeError(f"{case_id}: archived {field} does not match accepted Stage 3")

    expected_confidence = stage3_row.get("final_confidence")
    if isinstance(expected_confidence, (int, float)) and not isinstance(expected_confidence, bool):
        actual = prediction.get("confidence")
        if not isinstance(actual, (int, float)) or float(actual) != float(expected_confidence):
            raise RuntimeError(f"{case_id}: archived confidence does not match accepted Stage 3")

    expected_price = _expected_price(stage3_row)
    if expected_price is not None:
        actual_price = prediction.get("entry_odds")
        if not isinstance(actual_price, (int, float)) or float(actual_price) != expected_price:
            raise RuntimeError(f"{case_id}: archived entry_odds does not match accepted Stage 3")


def reconcile(
    *,
    db_path: str,
    workflow_id: str,
    stage_run_id: str,
    archive_root: str,
    archive_commit: str,
) -> dict[str, Any]:
    db = Path(db_path).resolve()
    root = Path(archive_root).resolve()
    if not db.is_file():
        raise RuntimeError(f"Predictor SQLite DB is missing: {db}")
    if not root.is_dir():
        raise RuntimeError(f"Learning Archive root is missing: {root}")
    if not re.fullmatch(r"[0-9a-f]{40}", archive_commit):
        raise RuntimeError("archive_commit must be an exact 40-character lowercase SHA")

    store = SQLiteOrchestratorStore(str(db))
    workflow = store.get_workflow(workflow_id)
    if workflow is None:
        raise RuntimeError("target Predictor workflow is missing from durable store")
    accepted = store.get_stage_output(workflow_id, "STAGE3")
    if accepted is None:
        raise RuntimeError("accepted STAGE3 is missing from durable store")
    if str(accepted.get("stage_run_id") or "") != stage_run_id:
        raise RuntimeError("accepted STAGE3 run id does not match requested recovery run")

    stage3_payload = accepted.get("payload") if isinstance(accepted.get("payload"), dict) else {}
    formal_rows = [
        row for row in stage3_payload.get("matches") or []
        if isinstance(row, dict) and str(row.get("decision") or "").upper() in {"BET", "WATCH"}
    ]
    if not formal_rows:
        raise RuntimeError("accepted STAGE3 contains no formal BET/WATCH rows")

    manifest = _load_manifest(root)
    timezone_name = str(workflow.scope.get("timezone") or "Europe/Istanbul")
    lifecycle = PredictorLifecycleStore(str(db))
    verified: list[dict[str, Any]] = []
    diary_paths: set[str] = set()

    for row in formal_rows:
        fixture_id = _fixture_id(row)
        preference = row.get("preference") if isinstance(row.get("preference"), dict) else {}
        prediction_at = str(row.get("prediction_at") or "").strip()
        market = str(preference.get("market") or "").strip()
        selection = str(preference.get("selection") or "").strip()
        if not fixture_id or not prediction_at or not market or not selection:
            raise RuntimeError("formal Stage 3 row is missing immutable prediction identity")

        case_id = _case_id(prediction_at, fixture_id, market, selection)
        dt = _parse_dt(prediction_at)
        utc = dt.astimezone(timezone.utc)
        case_rel = f"cases/{utc:%Y/%m/%d}/{case_id}"
        case_dir = root / case_rel
        case_path = case_dir / "case.json"
        evidence_path = case_dir / "evidence.json"
        captures_dir = case_dir / "captures"
        if not case_path.is_file() or not evidence_path.is_file():
            raise RuntimeError(f"{case_id}: required immutable archive files are missing")
        if not captures_dir.is_dir() or not any(captures_dir.glob("*.json.gz")):
            raise RuntimeError(f"{case_id}: initial stored-history capture is missing")

        case_doc = json.loads(case_path.read_text(encoding="utf-8"))
        if not isinstance(case_doc, dict):
            raise RuntimeError(f"{case_id}: case.json is not an object")
        _verify_case(case_doc, row, case_id)

        manifest_row = manifest.get(case_id)
        if manifest_row is None:
            raise RuntimeError(f"{case_id}: RECORDED manifest event is missing")
        if str(manifest_row.get("match_id_hash") or "") != fixture_id:
            raise RuntimeError(f"{case_id}: RECORDED manifest identity mismatch")
        if str(manifest_row.get("decision") or "").upper() != str(row.get("decision") or "").upper():
            raise RuntimeError(f"{case_id}: RECORDED manifest decision mismatch")
        checksum_summary = str(manifest_row.get("checksum_summary") or "").strip() or None

        local_dt = dt.astimezone(ZoneInfo(timezone_name))
        diary_rel = f"diaries/{local_dt:%Y/%m/%d}/predictions.md"
        diary_paths.add(diary_rel)
        diary_path = root / diary_rel
        if not diary_path.is_file():
            raise RuntimeError(f"{case_id}: prediction diary is missing")
        diary_text = diary_path.read_text(encoding="utf-8")
        begin = f"<!-- SXF-PREDICTOR-STAGE3:{stage_run_id}:BEGIN -->"
        end = f"<!-- SXF-PREDICTOR-STAGE3:{stage_run_id}:END -->"
        if begin not in diary_text or end not in diary_text:
            raise RuntimeError(f"{case_id}: exact Stage 3 diary block is missing")
        block = diary_text.split(begin, 1)[1].split(end, 1)[0]
        if f"`{case_id}`" not in block:
            raise RuntimeError(f"{case_id}: case is missing from exact Stage 3 diary block")

        archive_reference = (
            f"https://github.com/{_REPOSITORY}/tree/{archive_commit}/learning_archive_data/{case_rel}"
        )
        diary_reference = (
            f"https://github.com/{_REPOSITORY}/blob/{archive_commit}/learning_archive_data/{diary_rel}"
        )
        lifecycle.upsert(
            workflow_id=workflow_id,
            stage_run_id=stage_run_id,
            fixture_id=fixture_id,
            case_id=case_id,
            archive_status="RECORDED",
            archive_reference=archive_reference,
            archive_commit=archive_commit,
            checksum_summary=checksum_summary,
            diary_status="RECORDED",
            diary_reference=diary_reference,
            error=None,
        )
        verified.append({"fixture_id": fixture_id, "case_id": case_id})

    summary = lifecycle.summary(workflow_id, stage_run_id)
    if summary.get("status") != "RECORDED" or summary.get("diary_status") != "RECORDED":
        raise RuntimeError("lifecycle reconciliation did not reach RECORDED")
    if int(summary.get("formal_cases") or 0) != len(formal_rows):
        raise RuntimeError("lifecycle reconciliation case count mismatch")

    return {
        "ok": True,
        "workflow_id": workflow_id,
        "stage_run_id": stage_run_id,
        "formal_cases": len(formal_rows),
        "archive_status": summary.get("status"),
        "diary_status": summary.get("diary_status"),
        "archive_commit": archive_commit,
        "diaries": sorted(diary_paths),
        "verified_cases": verified,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile Predictor lifecycle receipts from already-durable canonical Learning Archive truth"
    )
    parser.add_argument("--db", required=True)
    parser.add_argument("--workflow-id", required=True)
    parser.add_argument("--stage-run-id", required=True)
    parser.add_argument("--archive-root", required=True)
    parser.add_argument("--archive-commit", required=True)
    args = parser.parse_args()
    try:
        result = reconcile(
            db_path=args.db,
            workflow_id=args.workflow_id,
            stage_run_id=args.stage_run_id,
            archive_root=args.archive_root,
            archive_commit=args.archive_commit,
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)[:500]}, ensure_ascii=False, sort_keys=True))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
