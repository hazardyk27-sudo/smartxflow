from __future__ import annotations

import gzip
import json
from pathlib import Path
import tempfile
import unittest

from learning_archive.package import canonical_json_bytes, sha256_hex
from learning_archive.reader import LearningArchiveReadError, LearningArchiveReader


CASE_ID = "20261003-legacy-history-test"


def _write_legacy_case(root: Path, *, tamper_history: bool = False) -> None:
    data_root = root / "learning_archive_data"
    case_dir = data_root / "cases" / "2026" / "10" / "03" / CASE_ID
    (case_dir / "addenda").mkdir(parents=True)

    case_doc = {
        "archive_schema_version": 1,
        "case_id": CASE_ID,
        "match": {
            "match_id_hash": "oldhash123456",
            "league": "Legacy League",
            "home": "Home",
            "away": "Away",
            "kickoff_at": "2026-10-03T18:00:00Z",
        },
        "prediction": {
            "prediction_at": "2026-10-03T15:00:00Z",
            "decision": "BET",
            "market": "1X2",
            "selection": "Home",
            "entry_odds": 1.80,
            "confidence": 70,
            "rationale": "Legacy case.",
            "counterargument": "Legacy counterargument.",
        },
        "provenance": {
            "archive_created_at": "2026-10-04T01:00:00Z",
            "source_repo": "hazardyk27-sudo/smartxflow",
            "source_commit": "deadbeef",
        },
    }
    evidence = [{
        "source": "legacy-report",
        "observed_at": "2026-10-03T14:30:00Z",
        "relationship": "SUPPORTS",
        "note": "Legacy evidence.",
        "phase": "PRE",
    }]
    settlement = {"status": "WIN", "final_score": "1-0"}

    base_files = {
        "case.json": canonical_json_bytes(case_doc),
        "evidence.json": canonical_json_bytes(evidence),
        "settlement.json": canonical_json_bytes(settlement),
    }
    for name, payload in base_files.items():
        (case_dir / name).write_bytes(payload)
    checksums = "".join(
        f"{sha256_hex(base_files[name])}  {name}\n" for name in sorted(base_files)
    ).encode("utf-8")
    (case_dir / "checksums.sha256").write_bytes(checksums)

    history = [{
        "scraped_at_utc": "2026-10-03T14:00:00Z",
        "markets": {"1X2": {"Home": {"odds": 1.90, "volume": 100, "share": 70}}},
    }]
    history_bytes = gzip.compress(canonical_json_bytes(history), compresslevel=9, mtime=0)
    history_path = case_dir / "historical_sxf_snapshots.json.gz"
    history_path.write_bytes(history_bytes)
    (case_dir / "historical_sxf_snapshots.sha256").write_text(
        f"{sha256_hex(history_bytes)}  historical_sxf_snapshots.json.gz\n",
        encoding="utf-8",
    )
    (case_dir / "addenda" / "historical_sxf_backfill.json").write_bytes(canonical_json_bytes({
        "kind": "HISTORICAL_SXF_BACKFILL",
        "identity_resolution": {
            "archived_case_hash": "oldhash123456",
            "canonical_source_hash": "newhash654321",
        },
    }))
    if tamper_history:
        history_path.write_bytes(gzip.compress(b"[]\n", compresslevel=9, mtime=0))

    archive_path = f"learning_archive_data/cases/2026/10/03/{CASE_ID}"
    manifest = {
        "case_id": CASE_ID,
        "event": "FINALIZED",
        "event_key": "final",
        "archive_path": archive_path,
        "archive_schema_version": 1,
        "match_id_hash": "oldhash123456",
        "prediction_at": "2026-10-03T15:00:00Z",
        "decision": "BET",
        "settlement_status": "WIN",
        "checksum_summary": "legacy",
    }
    (data_root / "manifest.jsonl").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


class HistoricalBackfillReaderTests(unittest.TestCase):
    def test_reader_uses_verified_historical_backfill_when_canonical_snapshot_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_legacy_case(root)
            loaded = LearningArchiveReader(root).read_case(CASE_ID)
            self.assertTrue(loaded["finalized"])
            self.assertEqual(loaded["snapshot_source"], "historical_backfill")
            self.assertEqual(len(loaded["snapshots"]), 1)
            self.assertEqual(
                loaded["snapshot_provenance"]["identity_resolution"]["canonical_source_hash"],
                "newhash654321",
            )

    def test_reader_fails_closed_on_historical_backfill_checksum_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_legacy_case(root, tamper_history=True)
            with self.assertRaisesRegex(LearningArchiveReadError, "checksum mismatch"):
                LearningArchiveReader(root).read_case(CASE_ID)


if __name__ == "__main__":
    unittest.main()
