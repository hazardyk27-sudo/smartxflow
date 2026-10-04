import json
from pathlib import Path
import tempfile
import unittest

from scripts.build_due_learning_revisit_batch import DueCaptureError, build_due_batch


class DueLearningCaptureTests(unittest.TestCase):
    def _write_case(self, root: Path, case_id: str, kickoff: str, prediction: str = "2026-10-04T14:00:00Z"):
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
                "prediction_at": prediction,
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
        return case_dir

    def _write_manifest(self, root: Path, entries):
        data_root = root / "learning_archive_data"
        data_root.mkdir(parents=True, exist_ok=True)
        (data_root / "manifest.jsonl").write_text(
            "".join(json.dumps(entry) + "\n" for entry in entries),
            encoding="utf-8",
        )

    def test_selects_recorded_case_within_35_minutes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            case_id = "20261004-test-watch"
            self._write_case(root, case_id, "2026-10-04T16:00:00Z")
            self._write_manifest(root, [{"case_id": case_id, "event": "RECORDED"}])
            payload = build_due_batch(root, "2026-10-04T15:30:00Z")
            self.assertEqual(len(payload["captures"]), 1)
            self.assertEqual(payload["captures"][0]["case"]["case_id"], case_id)
            self.assertEqual(payload["captures"][0]["case"]["settlement"]["status"], "PENDING")

    def test_skips_case_too_early(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            case_id = "20261004-test-watch"
            self._write_case(root, case_id, "2026-10-04T16:30:00Z")
            self._write_manifest(root, [{"case_id": case_id, "event": "RECORDED"}])
            payload = build_due_batch(root, "2026-10-04T15:30:00Z")
            self.assertEqual(payload["captures"], [])

    def test_skips_case_already_captured(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            case_id = "20261004-test-watch"
            self._write_case(root, case_id, "2026-10-04T16:00:00Z")
            self._write_manifest(root, [
                {"case_id": case_id, "event": "RECORDED"},
                {"case_id": case_id, "event": "CAPTURED"},
            ])
            payload = build_due_batch(root, "2026-10-04T15:30:00Z")
            self.assertEqual(payload["captures"], [])

    def test_explicit_backfill_can_target_already_captured_case_at_another_prematch_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            case_id = "20261004-test-watch"
            self._write_case(root, case_id, "2026-10-04T16:00:00Z")
            self._write_manifest(root, [
                {"case_id": case_id, "event": "RECORDED"},
                {"case_id": case_id, "event": "CAPTURED"},
            ])
            payload = build_due_batch(
                root,
                "2026-10-04T15:10:00Z",
                case_ids={case_id},
            )
            self.assertEqual(len(payload["captures"]), 1)
            self.assertEqual(payload["captures"][0]["observed_at"], "2026-10-04T15:10:00Z")

    def test_explicit_backfill_rejects_post_kickoff_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            case_id = "20261004-test-watch"
            self._write_case(root, case_id, "2026-10-04T16:00:00Z")
            self._write_manifest(root, [{"case_id": case_id, "event": "RECORDED"}])
            with self.assertRaisesRegex(DueCaptureError, "strictly before kickoff_at"):
                build_due_batch(root, "2026-10-04T16:00:00Z", case_ids={case_id})

    def test_explicit_backfill_rejects_unknown_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            known_case = "20261004-known-watch"
            self._write_case(root, known_case, "2026-10-04T16:00:00Z")
            self._write_manifest(root, [{"case_id": known_case, "event": "RECORDED"}])
            with self.assertRaisesRegex(DueCaptureError, "selected case_id not found"):
                build_due_batch(root, "2026-10-04T15:10:00Z", case_ids={"missing-case"})

    def test_skips_finalized_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            case_id = "20261004-test-watch"
            self._write_case(root, case_id, "2026-10-04T16:00:00Z")
            self._write_manifest(root, [
                {"case_id": case_id, "event": "RECORDED"},
                {"case_id": case_id, "event": "FINALIZED"},
            ])
            payload = build_due_batch(root, "2026-10-04T15:30:00Z")
            self.assertEqual(payload["captures"], [])

    def test_skips_after_kickoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            case_id = "20261004-test-watch"
            self._write_case(root, case_id, "2026-10-04T16:00:00Z")
            self._write_manifest(root, [{"case_id": case_id, "event": "RECORDED"}])
            payload = build_due_batch(root, "2026-10-04T16:00:01Z")
            self.assertEqual(payload["captures"], [])


if __name__ == "__main__":
    unittest.main()
