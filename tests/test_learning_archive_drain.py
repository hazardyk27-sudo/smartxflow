import unittest

from scripts.drain_due_learning_revisit_queue import PrematchDrainError, _pending_requests


class PrematchDrainTests(unittest.TestCase):
    def test_pending_requests_returns_queue_entries(self):
        requests = [{"observed_at": "2026-10-04T15:30:00Z", "case_ids": ["case-a"]}]
        self.assertEqual(_pending_requests({"requests": requests}), requests)

    def test_pending_requests_rejects_invalid_queue(self):
        with self.assertRaises(PrematchDrainError):
            _pending_requests({"requests": "bad"})


if __name__ == "__main__":
    unittest.main()
