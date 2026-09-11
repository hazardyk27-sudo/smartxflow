import unittest
from unittest.mock import patch

from desktop.scraper_standalone import standalone_scraper
from desktop.scraper_standalone.alarm_calculator import AlarmCalculator


class FakeResponse:
    def __init__(self, status_code=201, text="[]"):
        self.status_code = status_code
        self.text = text


def history_rows(count):
    return [
        {
            "home": f"Home {i}",
            "away": f"Away {i}",
            "league": "Test League",
            "date": "2026-09-11T12:00:00+00:00",
            "volume": "£ 100",
        }
        for i in range(count)
    ]


class HistoryInsertTests(unittest.TestCase):
    def test_history_insert_is_chunked(self):
        calls = []

        def post(url, headers, json, timeout, verify):
            calls.append(len(json))
            return FakeResponse()

        writer = standalone_scraper.SupabaseWriter(
            "https://example.supabase.co", "test-key"
        )
        with patch.object(standalone_scraper.requests, "post", side_effect=post):
            self.assertTrue(
                writer.append_history(
                    "moneyway_1x2_history", history_rows(205), "2026-09-11T15:00:00+03:00"
                )
            )

        self.assertEqual(calls, [100, 100, 5])
        self.assertEqual(writer.last_write_errors, [])

    def test_statement_timeout_retries_at_smaller_batch_size(self):
        calls = []

        def post(url, headers, json, timeout, verify):
            calls.append(len(json))
            if len(calls) <= 3:
                return FakeResponse(500, '{"code":"57014","message":"statement timeout"}')
            return FakeResponse()

        writer = standalone_scraper.SupabaseWriter(
            "https://example.supabase.co", "test-key"
        )
        with patch.object(standalone_scraper.requests, "post", side_effect=post), \
             patch.object(standalone_scraper.time, "sleep"):
            self.assertTrue(
                writer.append_history(
                    "moneyway_1x2_history", history_rows(100), "2026-09-11T15:00:00+03:00"
                )
            )

        self.assertEqual(calls, [100, 100, 100, 50, 50])
        self.assertEqual(writer.last_write_errors, [])


class AlarmHistoryMemoryTests(unittest.TestCase):
    def test_history_cache_is_bounded_per_match(self):
        calculator = AlarmCalculator.__new__(AlarmCalculator)
        calculator.url = "https://example.supabase.co"
        calculator.key = "test-key"
        calculator._history_cache = {}
        calculator._active_hashes_checked = True
        calculator._active_hashes_cache = ["match-1"]

        rows = [
            {
                "match_id_hash": "match-1",
                "home": "Home",
                "away": "Away",
                "league": "League",
                "date": "2026-09-11T12:00:00+00:00",
                "scraped_at": f"2026-09-11T12:{i // 60:02d}:{i % 60:02d}+03:00",
            }
            for i in range(300)
        ]
        calculator._get = lambda table, params: rows if "offset=0" in params else []

        history = calculator.batch_fetch_history("moneyway_1x2")

        self.assertEqual(len(history["match-1"]), AlarmCalculator.MAX_HISTORY_ROWS_PER_MATCH)
        self.assertEqual(history["match-1"][0]["scraped_at"], rows[44]["scraped_at"])


if __name__ == "__main__":
    unittest.main()