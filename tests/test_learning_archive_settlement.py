from __future__ import annotations

from copy import deepcopy
import gzip
import json
from pathlib import Path
import tempfile
import unittest

from learning_archive.settlement import SettlementError, build_settlement, prepare_final_snapshots
from learning_archive.validator import validate_case
from scripts.settle_due_learning_cases import PostmatchSettlementError, _archived_capture_history


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

    def test_over_35_uses_the_stored_line(self):
        value = case(decision="WATCH", market="O/U 3.5", selection="Over 3.5", odds=None)
        self.assertEqual(self.settle(value, "2-1")["hypothetical_result"], "LOSS")
        self.assertEqual(self.settle(value, "3-1")["hypothetical_result"], "WIN")

    def test_btts_no_win(self):
        value = case(market="Both Teams To Score", selection="No", odds=1.44)
        self.assertEqual(self.settle(value, "1-0")["status"], "WIN")

    def test_double_chance_x2(self):
        value = case(market="Double Chance", selection="X2", odds=1.34)
        self.assertEqual(self.settle(value, "1-1")["status"], "WIN")
        self.assertEqual(self.settle(value, "4-0")["status"], "LOSS")

    def test_double_chance_team_prefixed_x2_watch(self):
        value = case(decision="WATCH", market="Double Chance", selection="Stafford Rangers X2", odds=None)
        value["match"]["home"] = "Halesowen Town"
        value["match"]["away"] = "Stafford Rangers"
        result = self.settle(value, "1-2")
        self.assertEqual(result["status"], "NO_BET")
        self.assertEqual(result["hypothetical_result"], "WIN")

    def test_double_chance_team_prefix_must_match_code_side(self):
        value = case(decision="WATCH", market="Double Chance", selection="Portugal X2", odds=None)
        with self.assertRaises(SettlementError):
            self.settle(value, "1-1")

    def test_handicap_plus_15_watch(self):
        value = case(decision="WATCH", market="Handicap", selection="Norway +1.5", odds=None)
        self.assertEqual(self.settle(value, "2-1")["hypothetical_result"], "WIN")
        self.assertEqual(self.settle(value, "3-1")["hypothetical_result"], "LOSS")

    def test_handicap_minus_15_watch(self):
        value = case(decision="WATCH", market="Handicap", selection="Portugal -1.5", odds=None)
        self.assertEqual(self.settle(value, "3-1")["hypothetical_result"], "WIN")
        self.assertEqual(self.settle(value, "2-1")["hypothetical_result"], "LOSS")

    def test_handicap_reserve_suffix_roman_ii_alias(self):
        value = case(decision="WATCH", market="Handicap", selection="Kongsvinger II +1.5", odds=None)
        value["match"]["home"] = "Skjetten"
        value["match"]["away"] = "Kongsvinger Il"
        self.assertEqual(self.settle(value, "2-1")["hypothetical_result"], "WIN")

    def test_watch_is_no_bet_with_hypothetical_result(self):
        value = case(decision="WATCH", market="Double Chance", selection="X2", odds=1.67)
        result = self.settle(value, "1-1")
        self.assertEqual(result["status"], "NO_BET")
        self.assertEqual(result["hypothetical_result"], "WIN")
        final = deepcopy(value)
        final["settlement"] = result
        self.assertTrue(validate_case(final, [snapshots()[0]]).ok)

    def test_legacy_pass_settles_for_audit_but_is_not_a_valid_new_formal_case(self):
        value = case(decision="PASS", market=None, selection=None, odds=None)
        result = self.settle(value, "1-1")
        self.assertEqual(result["status"], "NO_BET")
        self.assertIsNone(result["hypothetical_result"])
        final = deepcopy(value)
        final["settlement"] = result
        self.assertFalse(validate_case(final, [snapshots()[0]]).ok)

    def test_builder_never_converts_watch_or_legacy_pass_into_real_wager(self):
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

    def test_archived_capture_fallback_uses_newest_durable_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp)
            captures = case_dir / "captures"
            captures.mkdir()
            older = [
                {"match_id_hash": "abc123def456", "scraped_at": "2026-10-04T18:30:00Z", "market": "1X2"},
            ]
            newer = [
                {"match_id_hash": "abc123def456", "scraped_at": "2026-10-04T18:30:00Z", "market": "1X2"},
                {"match_id_hash": "abc123def456", "scraped_at": "2026-10-04T18:40:00Z", "market": "BTTS"},
            ]
            for name, payload in (
                ("20261004T183000Z.json.gz", older),
                ("20261004T184000Z.json.gz", newer),
            ):
                with gzip.open(captures / name, "wt", encoding="utf-8") as handle:
                    json.dump(payload, handle)
            loaded = _archived_capture_history(case_dir, "abc123def456")
            self.assertEqual(loaded, newer)

    def test_archived_capture_fallback_rejects_identity_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp)
            captures = case_dir / "captures"
            captures.mkdir()
            with gzip.open(captures / "20261004T184000Z.json.gz", "wt", encoding="utf-8") as handle:
                json.dump([
                    {"match_id_hash": "ffffffffffff", "scraped_at": "2026-10-04T18:40:00Z", "market": "1X2"}
                ], handle)
            with self.assertRaises(PostmatchSettlementError):
                _archived_capture_history(case_dir, "abc123def456")


if __name__ == "__main__":
    unittest.main()
