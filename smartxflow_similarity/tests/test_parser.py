import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import unittest
from smartxflow_similarity.utils import parse_number, parse_datetime, match_id_hash, is_placeholder_odds
from smartxflow_similarity.parser_layer import parse_snapshot_row, build_canonical_match
from datetime import datetime


class TestParseNumber(unittest.TestCase):
    def test_float(self):
        self.assertEqual(parse_number(2.32), 2.32)

    def test_int(self):
        self.assertEqual(parse_number(5), 5.0)

    def test_string_dot(self):
        self.assertEqual(parse_number("2.32"), 2.32)

    def test_string_comma_decimal(self):
        self.assertEqual(parse_number("2,32"), 2.32)

    def test_string_comma_thousand(self):
        self.assertEqual(parse_number("1,200"), 1200.0)

    def test_string_comma_thousand_dot_decimal(self):
        self.assertEqual(parse_number("1,234.50"), 1234.50)

    def test_string_dot_thousand_comma_decimal(self):
        self.assertEqual(parse_number("1.234,50"), 1234.50)

    def test_currency_symbol(self):
        self.assertEqual(parse_number("£1,200"), 1200.0)

    def test_euro_symbol(self):
        self.assertEqual(parse_number("€2.50"), 2.50)

    def test_none(self):
        self.assertIsNone(parse_number(None))

    def test_dash(self):
        self.assertIsNone(parse_number("-"))

    def test_na(self):
        self.assertIsNone(parse_number("N/A"))

    def test_empty(self):
        self.assertIsNone(parse_number(""))

    def test_null_string(self):
        self.assertIsNone(parse_number("null"))


class TestParseDateTime(unittest.TestCase):
    def test_iso_format(self):
        result = parse_datetime("2025-03-10T15:30:00")
        self.assertIsNotNone(result)
        self.assertEqual(result.hour, 15)

    def test_iso_with_tz(self):
        result = parse_datetime("2025-03-10T15:30:00+03:00")
        self.assertIsNotNone(result)

    def test_dot_format(self):
        result = parse_datetime("10.03.2025 15:30")
        self.assertIsNotNone(result)

    def test_slash_format(self):
        result = parse_datetime("10/03/2025 15:30")
        self.assertIsNotNone(result)

    def test_none(self):
        self.assertIsNone(parse_datetime(None))

    def test_garbage(self):
        self.assertIsNone(parse_datetime("not-a-date"))

    def test_date_only(self):
        result = parse_datetime("2025-03-10")
        self.assertIsNotNone(result)


class TestMatchIdHash(unittest.TestCase):
    def test_basic(self):
        h = match_id_hash("Premier League", "Arsenal", "Chelsea")
        self.assertEqual(len(h), 12)

    def test_deterministic(self):
        h1 = match_id_hash("La Liga", "Barcelona", "Madrid")
        h2 = match_id_hash("La Liga", "Barcelona", "Madrid")
        self.assertEqual(h1, h2)

    def test_case_insensitive(self):
        h1 = match_id_hash("Premier League", "arsenal", "chelsea")
        h2 = match_id_hash("Premier League", "Arsenal", "Chelsea")
        self.assertEqual(h1, h2)


class TestIsPlaceholderOdds(unittest.TestCase):
    def test_none(self):
        self.assertTrue(is_placeholder_odds(None))

    def test_low(self):
        self.assertTrue(is_placeholder_odds(1.0))

    def test_high(self):
        self.assertTrue(is_placeholder_odds(150.0))

    def test_valid(self):
        self.assertFalse(is_placeholder_odds(2.50))


class TestParseSnapshotRow(unittest.TestCase):
    def test_moneyway_1x2(self):
        row = {
            "league": "Premier League",
            "home": "Arsenal",
            "away": "Chelsea",
            "date": "2025-03-10",
            "volume": "500000",
            "scraped_at": "2025-03-10T12:00:00",
            "odds1": "1.85",
            "oddsx": "3.50",
            "odds2": "4.20",
            "pct1": "55",
            "pctx": "25",
            "pct2": "20",
            "amt1": "275000",
            "amtx": "125000",
            "amt2": "100000",
        }
        parsed, warnings = parse_snapshot_row(row, "moneyway_1x2_history")
        self.assertEqual(parsed["odds1"], 1.85)
        self.assertEqual(parsed["oddsx"], 3.50)
        self.assertEqual(parsed["odds2"], 4.20)
        self.assertEqual(parsed["pct1"], 55.0)
        self.assertEqual(parsed["amt1"], 275000.0)
        self.assertEqual(parsed["volume"], 500000.0)
        self.assertEqual(len(warnings), 0)

    def test_dropping_btts(self):
        row = {
            "league": "La Liga",
            "home": "Barcelona",
            "away": "Madrid",
            "date": "2025-03-10",
            "volume": "1000000",
            "scraped_at": "2025-03-10T10:00:00",
            "oddsyes": "1.90",
            "oddsno": "1.90",
            "oddsyes_prev": "1.85",
            "oddsno_prev": "1.95",
            "trendyes": "up",
            "trendno": "down",
        }
        parsed, warnings = parse_snapshot_row(row, "dropping_btts_history")
        self.assertEqual(parsed["oddsyes"], 1.90)
        self.assertEqual(parsed["oddsno"], 1.90)
        self.assertEqual(parsed["trendyes"], "up")

    def test_placeholder_warning(self):
        row = {
            "league": "Test",
            "home": "A",
            "away": "B",
            "date": "2025-01-01",
            "scraped_at": "2025-01-01T00:00:00",
            "odds1": "1.00",
            "oddsx": "3.00",
            "odds2": "5.00",
        }
        parsed, warnings = parse_snapshot_row(row, "moneyway_1x2_history")
        self.assertTrue(any("placeholder_odds" in w for w in warnings))

    def test_missing_match_info(self):
        row = {"scraped_at": "2025-01-01T00:00:00"}
        parsed, warnings = parse_snapshot_row(row, "moneyway_1x2_history")
        self.assertTrue(any("missing_match_info" in w for w in warnings))

    def test_alias_support(self):
        row = {
            "league": "Test",
            "home": "A",
            "away": "B",
            "date": "2025-01-01",
            "scrape_time": "2025-01-01T00:00:00",
            "home_odds": "2.00",
            "draw_odds": "3.00",
            "away_odds": "4.00",
        }
        parsed, warnings = parse_snapshot_row(row, "moneyway_1x2_history")
        self.assertEqual(parsed["odds1"], 2.0)
        self.assertEqual(parsed["oddsx"], 3.0)
        self.assertEqual(parsed["odds2"], 4.0)


class TestBuildCanonicalMatch(unittest.TestCase):
    def test_basic_build(self):
        rows = {
            "moneyway_1x2_history": [
                {"league": "PL", "home": "A", "away": "B", "date": "2025-03-10T18:00:00",
                 "volume": "500000", "scraped_at": "2025-03-10T12:00:00",
                 "odds1": "1.85", "oddsx": "3.50", "odds2": "4.20",
                 "pct1": "55", "pctx": "25", "pct2": "20",
                 "amt1": "275000", "amtx": "125000", "amt2": "100000"},
            ],
            "moneyway_ou25_history": [],
            "moneyway_btts_history": [],
            "dropping_1x2_history": [],
            "dropping_ou25_history": [],
            "dropping_btts_history": [],
        }
        cm = build_canonical_match(rows)
        self.assertEqual(cm["meta"]["league"], "PL")
        self.assertEqual(cm["meta"]["home"], "A")
        self.assertEqual(cm["total_snapshots"], 1)
        self.assertIn("moneyway_1x2", cm["available_markets"])
        self.assertTrue(len(cm["missing_markets"]) > 0)


if __name__ == "__main__":
    unittest.main()
