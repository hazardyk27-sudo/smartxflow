import unittest

from learning_archive.outbox import CaptureOutboxError, capture_event_row, event_id, outbox_requests


class LearningArchiveOutboxTests(unittest.TestCase):
    def _capture(self, case_id="case-a"):
        return {
            "case": {
                "case_id": case_id,
                "match": {
                    "match_id_hash": "ABC123",
                    "kickoff_at": "2026-10-05T18:00:00Z",
                },
                "prediction": {"prediction_at": "2026-10-05T16:00:00Z"},
            }
        }

    def test_event_id_is_deterministic_per_case_and_observed_at(self):
        first = event_id("case-a", "2026-10-05T17:30:00Z")
        second = event_id("case-a", "2026-10-05T17:30:00Z")
        other = event_id("case-a", "2026-10-05T17:35:00Z")
        self.assertEqual(first, second)
        self.assertNotEqual(first, other)

    def test_capture_event_row_preserves_immutable_identity(self):
        row = capture_event_row(self._capture(), "2026-10-05T17:30:00Z")
        self.assertEqual(row["case_id"], "case-a")
        self.assertEqual(row["match_id_hash"], "abc123")
        self.assertEqual(row["observed_at"], "2026-10-05T17:30:00Z")
        self.assertEqual(row["kickoff_at"], "2026-10-05T18:00:00Z")
        self.assertEqual(row["prediction_at"], "2026-10-05T16:00:00Z")
        self.assertEqual(row["status"], "PENDING")

    def test_missing_identity_fails_closed(self):
        broken = self._capture()
        broken["case"]["match"]["match_id_hash"] = ""
        with self.assertRaises(CaptureOutboxError):
            capture_event_row(broken, "2026-10-05T17:30:00Z")

    def test_pending_rows_group_by_observed_at(self):
        requests = outbox_requests(
            [
                {"observed_at": "2026-10-05T17:30:00Z", "case_id": "case-b"},
                {"observed_at": "2026-10-05T17:30:00Z", "case_id": "case-a"},
                {"observed_at": "2026-10-05T17:35:00Z", "case_id": "case-a"},
            ]
        )
        self.assertEqual(
            requests,
            [
                {"observed_at": "2026-10-05T17:30:00Z", "case_ids": ["case-a", "case-b"]},
                {"observed_at": "2026-10-05T17:35:00Z", "case_ids": ["case-a"]},
            ],
        )


if __name__ == "__main__":
    unittest.main()
