from __future__ import annotations

import unittest

from learning_archive.settlement import build_settlement


class WomenTeamSettlementAliasTests(unittest.TestCase):
    def test_handicap_selection_without_w_suffix_matches_archived_womens_fixture(self):
        case = {
            "archive_schema_version": 1,
            "case_id": "20261009-7e445fbf4f12-208baf8750",
            "match": {
                "match_id_hash": "7e445fbf4f12",
                "league": "FIFA Ladies World Cup Qualifiers",
                "home": "Croatia (W)",
                "away": "Iceland (W)",
                "kickoff_at": "2026-10-09T16:45:00+00:00",
            },
            "prediction": {
                "prediction_at": "2026-10-09T14:08:10.041482+00:00",
                "decision": "WATCH",
                "market": "Handicap",
                "selection": "Croatia +1.5",
                "entry_odds": None,
                "confidence": 70.0,
                "rationale": "Regression fixture for production postmatch settlement.",
                "counterargument": "Regression fixture.",
            },
        }

        result = build_settlement(
            case,
            final_score="0-1",
            result_source="SmartXFlow live_fixtures",
            result_observed_at="2026-10-09T19:00:00+00:00",
        )

        self.assertEqual(result["status"], "NO_BET")
        self.assertEqual(result["hypothetical_result"], "WIN")

    def test_w_suffix_alias_does_not_match_other_womens_team(self):
        case = {
            "archive_schema_version": 1,
            "case_id": "women-alias-negative",
            "match": {
                "match_id_hash": "abcdef123456",
                "league": "Test",
                "home": "Croatia (W)",
                "away": "Iceland (W)",
                "kickoff_at": "2026-10-09T16:45:00+00:00",
            },
            "prediction": {
                "prediction_at": "2026-10-09T14:00:00+00:00",
                "decision": "WATCH",
                "market": "Handicap",
                "selection": "Iceland +1.5",
                "entry_odds": None,
                "confidence": 70.0,
                "rationale": "Negative-side alias check.",
                "counterargument": "Regression fixture.",
            },
        }

        result = build_settlement(
            case,
            final_score="2-0",
            result_source="SmartXFlow live_fixtures",
            result_observed_at="2026-10-09T19:00:00+00:00",
        )

        self.assertEqual(result["hypothetical_result"], "LOSS")


if __name__ == "__main__":
    unittest.main()
