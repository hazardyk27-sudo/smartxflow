from __future__ import annotations

from copy import deepcopy
import os
import unittest
from unittest.mock import patch

from learning_archive.exporter import LearningArchiveExporter
from learning_archive.github_backend import ArchiveWriteResult
from learning_archive.package import build_archive_package, verify_package_checksums
from learning_archive.source_history import fetch_selected_match_history
from learning_archive.validator import classify_evidence_phase, validate_case


def sample_case():
    return {
        "archive_schema_version": 1,
        "case_id": "20261003-test-001",
        "match": {"match_id_hash": "abc123def456", "league": "Test", "home": "Home", "away": "Away", "kickoff_at": "2026-10-03T18:00:00Z"},
        "prediction": {"prediction_at": "2026-10-03T15:30:00Z", "decision": "WATCH", "market": "Double Chance", "selection": "1X", "entry_odds": 1.42, "rationale": "Money flow and price reaction aligned."},
        "evidence": [
            {"source": "news", "observed_at": "2026-10-03T15:00:00Z", "relationship": "SUPPORTS", "note": "Pre-cutoff evidence."},
            {"source": "closing", "observed_at": "2026-10-03T17:00:00Z", "relationship": "NEUTRAL", "note": "Post-cutoff evidence."},
        ],
        "settlement": {"status": "WIN", "final_score": "2-1"},
        "provenance": {"archive_created_at": "2026-10-03T19:00:00Z", "source_repo": "hazardyk27-sudo/smartxflow", "source_commit": "6318e350e485470136c20aee1fdbbba5f454f8f7"},
    }


def sample_snapshots():
    return [
        {"match_id_hash": "abc123def456", "scraped_at": "2026-10-03T15:25:00+03:00", "market": "1X2", "home": 2.1},
        {"match_id_hash": "abc123def456", "scraped_at": "2026-10-03T15:10:00+03:00", "market": "1X2", "home": 2.2},
    ]


class MemoryBackend:
    def __init__(self):
        self.saved = None
    def write_case(self, package, case):
        duplicate = self.saved == package.files
        if self.saved is None:
            self.saved = package.files
        return ArchiveWriteResult("memory://case", "mem-1", duplicate)


class FakeResponse:
    def __init__(self, code, payload):
        self.status_code = code
        self.payload = payload
    def json(self):
        return self.payload


class FakeSession:
    def __init__(self):
        self.headers = {}
    def get(self, url, params=None, timeout=None):
        table = url.rsplit('/', 1)[-1]
        if table == "moneyway_double_chance_history":
            return FakeResponse(404, {"code": "PGRST205", "message": "Could not find the table"})
        if table == "moneyway_1x2_history":
            return FakeResponse(200, [{"match_id_hash": "abc123def456", "scraped_at": "2026-10-03T15:00:00+03:00"}])
        return FakeResponse(200, [])


class LearningArchiveTests(unittest.TestCase):
    def test_valid_case_and_pre_post_cutoff(self):
        case = sample_case()
        self.assertTrue(validate_case(case, sample_snapshots()).ok)
        self.assertEqual([x["phase"] for x in classify_evidence_phase(case)], ["PRE", "POST"])

    def test_secret_rejected(self):
        case = sample_case()
        case["evidence"][0]["note"] = "Bearer abcdefghijklmnopqrstuvwxyz123456"
        self.assertFalse(validate_case(case, sample_snapshots()).ok)

    def test_polymarket_rejected(self):
        case = sample_case()
        case["evidence"][0]["source"] = "Polymarket"
        self.assertFalse(validate_case(case, sample_snapshots()).ok)

    def test_false_pre_phase_rejected(self):
        case = sample_case()
        case["evidence"][1]["phase"] = "PRE"
        result = validate_case(case, sample_snapshots())
        self.assertFalse(result.ok)
        self.assertTrue(any("must be POST" in item for item in result.errors))

    def test_deterministic_package_and_checksum(self):
        first = build_archive_package(sample_case(), sample_snapshots())
        second = build_archive_package(deepcopy(sample_case()), list(reversed(sample_snapshots())))
        self.assertEqual(first.files, second.files)
        self.assertTrue(verify_package_checksums(first)[0])

    def test_done_only_after_backend_write_and_idempotent_repeat(self):
        exporter = LearningArchiveExporter(MemoryBackend())
        self.assertFalse(exporter.finalize_case(sample_case(), sample_snapshots()).idempotent)
        self.assertTrue(exporter.finalize_case(sample_case(), sample_snapshots()).idempotent)

    def test_empty_history_fails_closed(self):
        self.assertFalse(validate_case(sample_case(), []).ok)

    def test_existing_history_reader_and_optional_market_table(self):
        with patch.dict(os.environ, {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_KEY": "test-key"}, clear=False):
            result = fetch_selected_match_history(
                "abc123def456",
                tables=("moneyway_1x2_history", "moneyway_double_chance_history"),
                session=FakeSession(),
            )
        self.assertEqual(len(result.snapshots), 1)
        self.assertEqual(result.unavailable_optional_tables, ("moneyway_double_chance_history",))


if __name__ == "__main__":
    unittest.main()
