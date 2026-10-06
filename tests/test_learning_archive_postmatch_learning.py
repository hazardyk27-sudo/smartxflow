from __future__ import annotations

import json
import unittest

from learning_archive.package import build_archive_package, verify_package_checksums
from learning_archive.postmatch_learning import build_postmatch_learning_note


def base_case(*, decision="BET", market="O/U 2.5", selection="Under 2.5", odds=1.50):
    return {
        "archive_schema_version": 1,
        "case_id": "20261006-postmatch-learning-test",
        "match": {
            "match_id_hash": "abc123def456",
            "league": "Test League",
            "home": "Home FC",
            "away": "Away FC",
            "kickoff_at": "2026-10-06T18:45:00Z",
        },
        "prediction": {
            "prediction_at": "2026-10-06T15:00:00Z",
            "decision": decision,
            "market": market,
            "selection": selection,
            "entry_odds": odds,
            "confidence": 75,
            "rationale": "Frozen thesis.",
            "counterargument": "Failure condition.",
        },
        "evidence": [
            {"source": "official", "observed_at": "2026-10-06T15:10:00Z", "relationship": "SUPPORTS", "note": "Stage 2 support."},
        ],
        "settlement": {
            "status": "WIN" if decision == "BET" else "NO_BET",
            "final_score": "1-0",
            "hypothetical_result": None if decision == "BET" else "WIN",
            "result_observed_at": "2026-10-06T21:00:00Z",
        },
        "provenance": {
            "archive_created_at": "2026-10-06T15:01:00Z",
            "archive_finalized_at": "2026-10-06T21:05:00Z",
            "source_repo": "hazardyk27-sudo/smartxflow",
            "source_commit": "0123456789abcdef0123456789abcdef01234567",
        },
    }


def ou_snapshots():
    return [
        {
            "match_id_hash": "abc123def456",
            "_archive_source_table": "moneyway_ou25_history",
            "scraped_at": "2026-10-06T18:30:00Z",
            "under": "1.52",
            "pctunder": "65.0%",
            "amtunder": "£ 1000",
            "volume": "£ 1500",
        },
        {
            "match_id_hash": "abc123def456",
            "_archive_source_table": "moneyway_ou25_history",
            "scraped_at": "2026-10-06T18:40:00Z",
            "under": "1.55",
            "pctunder": "70.0%",
            "amtunder": "£ 1400",
            "volume": "£ 2000",
        },
    ]


class PostmatchLearningTests(unittest.TestCase):
    def test_native_note_uses_latest_prematch_selected_market_state(self):
        case = base_case()
        note = build_postmatch_learning_note(case, ou_snapshots(), observed_at="2026-10-06T21:05:00Z")
        self.assertTrue(note["final_prematch_sxf"]["native"])
        self.assertEqual(note["final_prematch_sxf"]["price"], "1.55")
        self.assertEqual(note["final_prematch_sxf"]["share"], "70.0%")
        self.assertEqual(note["type"], "OBSERVATION")

    def test_non_native_note_never_fabricates_execution_history(self):
        case = base_case(decision="WATCH", market="Handicap", selection="Away FC +1.5", odds=None)
        case["prediction"]["minimum_acceptable_odds"] = 1.70
        note = build_postmatch_learning_note(case, ou_snapshots(), observed_at="2026-10-06T21:05:00Z")
        self.assertFalse(note["final_prematch_sxf"]["native"])
        self.assertIn("no synthetic", note["final_prematch_sxf"]["unavailable_reason"].lower())
        self.assertEqual(note["hypothetical_result"], "WIN")
        self.assertEqual(note["selected_market"]["minimum_acceptable_odds"], 1.70)

    def test_final_package_always_contains_standard_postmatch_addendum(self):
        package = build_archive_package(base_case(), ou_snapshots())
        addenda = [name for name in package.files if name.startswith("addenda/") and name.endswith("-postmatch-learning.json")]
        self.assertEqual(len(addenda), 1)
        note = json.loads(package.files[addenda[0]].decode("utf-8"))
        self.assertEqual(note["case_id"], "20261006-postmatch-learning-test")
        self.assertEqual(note["observed_at"], "2026-10-06T21:05:00Z")
        self.assertTrue(verify_package_checksums(package)[0])


if __name__ == "__main__":
    unittest.main()
