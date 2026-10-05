from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from learning_archive.result_source import ResultSourceError, fetch_finished_result, fetch_finished_results


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class _Session:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, *, params, timeout):
        self.calls.append((url, params, timeout))
        return _Response(self.payload)


class ResultSourceBatchTests(unittest.TestCase):
    def _env(self):
        return patch.dict(
            os.environ,
            {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "test"},
            clear=False,
        )

    def test_batch_fetch_uses_one_request_and_preserves_pending(self):
        session = _Session([
            {
                "match_id_hash": "aaaaaaaaaaaa",
                "score": "2-1",
                "status": "finished",
                "minute": "FT",
                "updated_at": "2026-10-05T20:00:00Z",
            },
            {
                "match_id_hash": "bbbbbbbbbbbb",
                "score": "0-0",
                "status": "live",
                "minute": "55",
                "updated_at": "2026-10-05T19:30:00Z",
            },
        ])
        with self._env():
            results = fetch_finished_results(
                ["aaaaaaaaaaaa", "bbbbbbbbbbbb"],
                session=session,
            )
        self.assertEqual(len(session.calls), 1)
        self.assertEqual(session.calls[0][1]["match_id_hash"], "in.(aaaaaaaaaaaa,bbbbbbbbbbbb)")
        self.assertEqual(results["aaaaaaaaaaaa"].final_score, "2-1")
        self.assertIsNone(results["bbbbbbbbbbbb"])

    def test_duplicate_rows_fail_closed(self):
        row = {
            "match_id_hash": "aaaaaaaaaaaa",
            "score": "1-0",
            "status": "ft",
            "minute": "FT",
            "updated_at": "2026-10-05T20:00:00Z",
        }
        session = _Session([row, dict(row)])
        with self._env(), self.assertRaises(ResultSourceError):
            fetch_finished_results(["aaaaaaaaaaaa"], session=session)

    def test_single_lookup_uses_batch_path(self):
        session = _Session([])
        with self._env():
            self.assertIsNone(fetch_finished_result("aaaaaaaaaaaa", session=session))
        self.assertEqual(len(session.calls), 1)


if __name__ == "__main__":
    unittest.main()
