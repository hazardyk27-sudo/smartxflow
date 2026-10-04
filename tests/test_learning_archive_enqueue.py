import unittest

from learning_archive.outbox import CaptureOutboxError, capture_event_row, event_id, outbox_requests
from scripts.enqueue_due_learning_revisit import PrematchEnqueueError, merge_request_payload


class PrematchEnqueueTests(unittest.TestCase):
    def test_appends_only_new_due_case_ids(self):
        existing = {
            "request_id": "old",
            "requests": [
                {
                    "observed_at": "2026-10-04T15:30:00Z",
                    "case_ids": ["case-a"],
                }
            ],
        }
        merged, added = merge_request_payload(
            existing,
            "2026-10-04T15:35:00Z",
            ["case-a", "case-b", "case-c"],
        )
        self.assertEqual(added, ["case-b", "case-c"])
        self.assertEqual(merged["request_id"], "hetzner-prematch-queue")
        self.assertEqual(len(merged["requests"]), 2)
        self.assertEqual(merged["requests"][1]["case_ids"], ["case-b", "case-c"])

    def test_due_case_already_in_queue_is_not_retimestamped(self):
        existing = {
            "request_id": "hetzner-prematch-queue",
            "requests": [
                {
                    "observed_at": "2026-10-04T15:30:00Z",
                    "case_ids": ["case-a"],
                }
            ],
        }
        merged, added = merge_request_payload(existing, "2026-10-04T15:35:00Z", ["case-a"])
        self.assertEqual(added, [])
        self.assertEqual(merged["requests"], existing["requests"])

    def test_invalid_existing_queue_fails_closed(self):
        with self.assertRaises(PrematchEnqueueError):
            merge_request_payload({"requests": "bad"}, "2026-10-04T15:30:00Z", ["case-a"])

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

    def test_outbox_event_id_is_deterministic(self):
        first = event_id("case-a", "2026-10-05T17:30:00Z")
        second = event_id("case-a", "2026-10-05T17:30:00Z")
        other = event_id("case-a", "2026-10-05T17:35:00Z")
        self.assertEqual(first, second)
        self.assertNotEqual(first, other)

    def test_outbox_row_preserves_identity_and_timestamps(self):
        row = capture_event_row(self._capture(), "2026-10-05T17:30:00Z")
        self.assertEqual(row["case_id"], "case-a")
        self.assertEqual(row["match_id_hash"], "abc123")
        self.assertEqual(row["observed_at"], "2026-10-05T17:30:00Z")
        self.assertEqual(row["status"], "PENDING")

    def test_outbox_missing_identity_fails_closed(self):
        broken = self._capture()
        broken["case"]["match"]["match_id_hash"] = ""
        with self.assertRaises(CaptureOutboxError):
            capture_event_row(broken, "2026-10-05T17:30:00Z")

    def test_outbox_pending_rows_group_by_observed_at(self):
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
