from __future__ import annotations

import tempfile
import unittest

from learning_archive.github_backend import RepositoryFolderArchiveBackend
from learning_archive.package import build_record_package
from learning_archive.reader import LearningArchiveReader


def legacy_pass_case():
    return {
        "archive_schema_version": 1,
        "case_id": "20261004-legacy-pass",
        "match": {
            "match_id_hash": "legacy123",
            "league": "Test",
            "home": "Home",
            "away": "Away",
            "kickoff_at": "2026-10-04T18:00:00Z",
        },
        "prediction": {
            "prediction_at": "2026-10-04T15:00:00Z",
            "decision": "PASS",
            "market": None,
            "selection": None,
            "entry_odds": None,
            "confidence": 0.5,
            "rationale": "Legacy audit case.",
            "counterargument": "Legacy audit case.",
        },
        "evidence": [],
        "settlement": {"status": "PENDING"},
        "provenance": {
            "archive_created_at": "2026-10-04T15:01:00Z",
            "source_repo": "hazardyk27-sudo/smartxflow",
            "source_commit": "legacy",
        },
    }


class LearningArchivePredictionPolicyTests(unittest.TestCase):
    def test_legacy_pass_remains_auditable_but_is_not_in_default_iteration(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = RepositoryFolderArchiveBackend(tmp)
            case = legacy_pass_case()
            package = build_record_package(
                case,
                [{"match_id_hash": "legacy123", "scraped_at": "2026-10-04T14:55:00Z"}],
                "2026-10-04T15:01:00Z",
            )
            backend.write_case(package, case)

            reader = LearningArchiveReader(tmp)
            self.assertEqual(list(reader.iter_cases()), [])
            audit = list(reader.iter_cases(prediction_only=False))
            self.assertEqual(len(audit), 1)
            self.assertEqual(audit[0]["case"]["prediction"]["decision"], "PASS")


if __name__ == "__main__":
    unittest.main()
