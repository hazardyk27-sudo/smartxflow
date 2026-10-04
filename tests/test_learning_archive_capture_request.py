import json
from pathlib import Path
import tempfile
import unittest

from scripts.build_learning_revisit_request_batch import CaptureRequestError, build_request_batch


class CaptureRequestBatchTests(unittest.TestCase):
    def _write_case(self, root: Path, case_id: str, kickoff: str):
        case_dir = root / "learning_archive_data" / "cases" / "2026" / "10" / "04" / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        case = {
            "archive_schema_version": 1,
            "case_id": case_id,
            "match": {
                "match_id_hash": "0123456789ab",
                "league": "Test League",
                "home": "Home",
                "away": "Away",
                "kickoff_at": kickoff,
            },
            "prediction": {
                "prediction_at": "2026-10-04T14:00:00Z",
                "decision": "WATCH",
                "market": "1X2",
                "selection": "1",
                "entry_odds": 2.0,
                "confidence": 60,
                "rationale": "test rationale",
                "counterargument": "test counterargument",
            },
            "provenance": {
                "archive_created_at": "2026-10-04T14:05:00Z",
                "source_repo": "hazardyk27-sudo/smartxflow",
                "source_commit": "deadbeef",
            },
        }
        (case_dir / "case.json").write_text(json.dumps(case), encoding="utf-8")
        (case_dir / "evidence.json").write_text("[]", encoding="utf-8")

    def _write_manifest(self, root: Path, case_ids):
        data_root = root / "learning_archive_data"
        data_root.mkdir(parents=True, exist_ok=True)
        (data_root / "manifest.jsonl").write_text(
            "".join(json.dumps({"case_id": case_id, "event": "RECORDED"}) + "\n" for case_id in case_ids),
            encoding="utf-8",
        )

    def test_builds_multiple_historical_groups(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            case_a = "20261004-a-watch"
            case_b = "20261004-b-watch"
            self._write_case(root, case_a, "2026-10-04T16:00:00Z")
            self._write_case(root, case_b, "2026-10-04T17:00:00Z")
            self._write_manifest(root, [case_a, case_b])
            request = root / "request.json"
            request.write_text(json.dumps({
                "request_id": "test-request",
                "requests": [
                    {"observed_at": "2026-10-04T15:30:00Z", "case_ids": [case_a]},
                    {"observed_at": "2026-10-04T16:30:00Z", "case_ids": [case_b]},
                ],
            }), encoding="utf-8")
            batch = build_request_batch(root, request)
            self.assertEqual(batch["request_id"], "test-request")
            self.assertEqual(len(batch["captures"]), 2)
            self.assertEqual(
                [item["observed_at"] for item in batch["captures"]],
                ["2026-10-04T15:30:00Z", "2026-10-04T16:30:00Z"],
            )

    def test_rejects_duplicate_request_pair(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            case_id = "20261004-a-watch"
            self._write_case(root, case_id, "2026-10-04T16:00:00Z")
            self._write_manifest(root, [case_id])
            request = root / "request.json"
            request.write_text(json.dumps({
                "requests": [
                    {"observed_at": "2026-10-04T15:30:00Z", "case_ids": [case_id]},
                    {"observed_at": "2026-10-04T15:30:00Z", "case_ids": [case_id]},
                ],
            }), encoding="utf-8")
            with self.assertRaisesRegex(CaptureRequestError, "duplicate capture request"):
                build_request_batch(root, request)


if __name__ == "__main__":
    unittest.main()
