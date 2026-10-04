import unittest

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
        self.assertEqual(merged["request_id"], "prematch-capture-queue")
        self.assertEqual(len(merged["requests"]), 2)
        self.assertEqual(merged["requests"][1]["case_ids"], ["case-b", "case-c"])

    def test_due_case_already_in_queue_is_not_retimestamped(self):
        existing = {
            "request_id": "prematch-capture-queue",
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


if __name__ == "__main__":
    unittest.main()
