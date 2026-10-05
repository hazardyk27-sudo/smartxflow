from __future__ import annotations

from copy import deepcopy
import unittest

from learning_archive.settlement import build_settlement, prepare_final_snapshots
from learning_archive.validator import validate_case


def case(decision="BET", market="1X2", selection="Portugal", odds=1.64):
    return {
        "archive_schema_version": 1,
        "case_id": "20261004-postmatch-test",
        "match": {
            "match_id_hash": "abc123def456",
            "league": "Test League",
            "home": "Portugal",
            "away": "Norway",
            "kickoff_at": "2026-10-04T18:45:00Z",
        },
        "prediction": {
            "prediction_at": "2026-10-04T14:18:36Z",
            "decision": decision,
            "market": market,
            "selection": selection,
            "entry_odds": odds,
            "confidence": 80,
            "rationale": "Stored SXF history supported the final decision.",
            "counterargument": "Late reversal remained possible.",
        },
        "evidence": [],
        "settlement": {"status": "PENDING"},
        "provenance": {
            "archive_created_at": "2026-10-04T15:17:55Z",
            "source_repo": "hazardyk27-sudo/smartxflow",
            "source_commit": "0123456789abcdef0123456789abcdef01234567",
        },
    }


def snapshots():
    return [
        {"match_id_hash": "abc123def456", "scraped_at": "2026-10-04T18:40:00Z", "market": "1X2"},
        {"match_id_hash": "abc123def456", "scraped_at": "2026-10-04T18:45:00Z", "market": "1X2"},
        {"match_id_hash": "abc123def456", "scraped_at": "2026-10-04T18:50:00Z", "market": "1X2"},
    ]


class SettlementTests(unittest.TestCase):
    def settle(self, value, score):
        return build_settlement(
            value,
            final_score=score,
            result_source="SmartXFlow live_fixtures",
            result_observed_at="2026-10-04T21:00:00Z",
        )

    def test_1x2_win_and_loss(self):
        self.assertEqual(self.settle(case(), "2-1")["status"], "WIN")
        self.assertEqual(self.settle(case(), "0-0")["status"], "LOSS")

    def test_over_25_loss_at_one_one(self):
        value = case(market="Over/Under 2.5", selection="Over", odds=1.37)
        result = self.settle(value, "1-1")
        self.assertEqual(result["status"], "LOSS")
        self.assertEqual(result["pnl_units"], -1.0)

    def test_btts_no_win(self):
        value = case(market="Both Teams To Score", selection="No", odds=1.44)
        self.assertEqual(self.settle(value, "1-0")["status"], "WIN")

    def test_double_chance_x2(self):
        value = case(market="Double Chance", selection="X2", odds=1.34)
        self.assertEqual(self.settle(value, "1-1")["status"], "WIN")
        self.assertEqual(self.settle(value, "4-0")["status"], "LOSS")

    def test_watch_is_no_bet_with_hypothetical_result(self):
        value = case(decision="WATCH", market="Double Chance", selection="X2", odds=1.67)
        result = self.settle(value, "1-1")
        self.assertEqual(result["status"], "NO_BET")
        self.assertEqual(result["hypothetical_result"], "WIN")
        final = deepcopy(value)
        final["settlement"] = result
        self.assertTrue(validate_case(final, [snapshots()[0]]).ok)

    def test_pass_is_no_bet_without_hypothetical_wager(self):
        value = case(decision="PASS", market=None, selection=None, odds=None)
        result = self.settle(value, "1-1")
        self.assertEqual(result["status"], "NO_BET")
        self.assertIsNone(result["hypothetical_result"])
        final = deepcopy(value)
        final["settlement"] = result
        self.assertTrue(validate_case(final, [snapshots()[0]]).ok)

    def test_builder_never_converts_watch_or_pass_into_real_wager(self):
        watch = self.settle(case(decision="WATCH", market="Double Chance", selection="X2", odds=1.67), "1-1")
        passed = self.settle(case(decision="PASS", market=None, selection=None, odds=None), "2-1")
        self.assertEqual(watch["status"], "NO_BET")
        self.assertEqual(watch["hypothetical_result"], "WIN")
        self.assertEqual(passed["status"], "NO_BET")
        self.assertIsNone(passed["hypothetical_result"])

    def test_final_snapshots_are_strictly_prematch(self):
        kept = prepare_final_snapshots(case(), snapshots())
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["scraped_at"], "2026-10-04T18:40:00Z")


if __name__ == "__main__":
    unittest.main()
