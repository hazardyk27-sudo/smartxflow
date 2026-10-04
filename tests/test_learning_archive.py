from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from learning_archive.exporter import ArchiveFinalizationError, LearningArchiveExporter
from learning_archive.github_backend import ArchiveConflictError, ArchiveWriteResult, RepositoryFolderArchiveBackend
from learning_archive.package import build_archive_package, build_record_package, verify_package_checksums
from learning_archive.reader import LearningArchiveReader
from learning_archive.source_history import SXFHistoryError, fetch_selected_match_history
from learning_archive.validator import classify_evidence_phase, validate_case


def sample_case(status="WIN"):
    return {
        "archive_schema_version": 1,
        "case_id": "20261003-test-001",
        "match": {"match_id_hash": "abc123def456", "league": "Test", "home": "Home", "away": "Away", "kickoff_at": "2026-10-03T18:00:00Z"},
        "prediction": {
            "prediction_at": "2026-10-03T15:30:00Z", "decision": "WATCH", "market": "Double Chance", "selection": "1X", "entry_odds": 1.42,
            "confidence": 0.68, "rationale": "Money flow and price reaction aligned.", "counterargument": "Late reversal would invalidate the read."
        },
        "evidence": [
            {"source": "news", "observed_at": "2026-10-03T15:00:00Z", "relationship": "SUPPORTS", "note": "Pre-cutoff evidence."},
            {"source": "closing", "observed_at": "2026-10-03T17:00:00Z", "relationship": "NEUTRAL", "note": "Post-cutoff evidence."},
        ],
        "settlement": {"status": status, "final_score": "2-1" if status != "PENDING" else None},
        "provenance": {"archive_created_at": "2026-10-03T15:31:00Z", "source_repo": "hazardyk27-sudo/smartxflow", "source_commit": "e0935c053fd1d1faf0e5fd1b3348d232c1187dc6"},
    }


def sample_snapshots():
    return [
        {"match_id_hash": "abc123def456", "scraped_at": "2026-10-03T15:25:00+03:00", "market": "1X2", "home": 2.1},
        {"match_id_hash": "abc123def456", "scraped_at": "2026-10-03T15:10:00+03:00", "market": "1X2", "home": 2.2},
    ]


class MemoryBackend:
    durable = True
    def __init__(self):
        self.saved = None
    def write_case(self, package, case):
        duplicate = self.saved == package.files
        if self.saved is None:
            self.saved = package.files
        elif self.saved != package.files:
            raise ArchiveConflictError("conflict")
        return ArchiveWriteResult("memory://case", "mem-1", duplicate)


class FakeResponse:
    def __init__(self, code, payload):
        self.status_code = code
        self.payload = payload
    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, response=None):
        self.headers = {}
        self.response = response or FakeResponse(200, {
            "match_id_hash": "abc123def456",
            "histories": {
                "moneyway_1x2_history": [
                    {"match_id_hash": "abc123def456", "scraped_at": "2026-10-03T15:20:00+03:00", "odds1": 2.1},
                ],
                "dropping_1x2_history": [
                    {"match_id_hash": "abc123def456", "scraped_at": "2026-10-03T15:00:00+03:00", "odds1": 2.2},
                ],
            },
            "source_tables": ["moneyway_1x2_history", "dropping_1x2_history"],
            "unavailable_optional_tables": [],
        })
        self.last_url = None
        self.last_timeout = None
    def get(self, url, timeout=None):
        self.last_url = url
        self.last_timeout = timeout
        return self.response


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

    def test_first_write_manifest_and_idempotent_rerun(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = RepositoryFolderArchiveBackend(tmp)
            case = sample_case("PENDING")
            package = build_record_package(case, sample_snapshots(), "2026-10-03T15:31:00Z")
            first = backend.write_case(package, case)
            second = backend.write_case(package, case)
            self.assertFalse(first.idempotent)
            self.assertTrue(second.idempotent)
            manifest = Path(tmp, "learning_archive_data", "manifest.jsonl").read_text()
            self.assertEqual(manifest.count("\n"), 1)
            self.assertIn('"event":"RECORDED"', manifest)

    def test_conflicting_rerun_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = RepositoryFolderArchiveBackend(tmp)
            case = sample_case("PENDING")
            backend.write_case(build_record_package(case, sample_snapshots(), "2026-10-03T15:31:00Z"), case)
            changed = deepcopy(case)
            changed["prediction"]["rationale"] = "Rewritten after result."
            conflicting = build_record_package(changed, sample_snapshots(), "2026-10-03T15:31:00Z")
            with self.assertRaises(ArchiveConflictError):
                backend.write_case(conflicting, changed)

    def test_development_reader_reads_final_case_and_pre_only_view(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = RepositoryFolderArchiveBackend(tmp)
            pending = sample_case("PENDING")
            backend.write_case(build_record_package(pending, sample_snapshots(), "2026-10-03T15:31:00Z"), pending)
            final = sample_case("WIN")
            backend.write_case(build_archive_package(final, sample_snapshots()), final)
            loaded = LearningArchiveReader(tmp).read_case(final["case_id"])
            self.assertTrue(loaded["finalized"])
            self.assertEqual(len(loaded["pre_evidence"]), 1)
            self.assertEqual(len(loaded["post_evidence"]), 1)
            self.assertEqual(loaded["settlement"]["status"], "WIN")
            self.assertEqual(len(loaded["captures"]), 1)

    def test_done_only_after_durable_backend_and_settlement(self):
        exporter = LearningArchiveExporter(MemoryBackend())
        self.assertFalse(exporter.finalize_case(sample_case(), sample_snapshots()).idempotent)
        self.assertTrue(exporter.finalize_case(sample_case(), sample_snapshots()).idempotent)
        with self.assertRaisesRegex(ArchiveFinalizationError, "PENDING"):
            exporter.finalize_case(sample_case("PENDING"), sample_snapshots())

    def test_worktree_backend_never_claims_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            exporter = LearningArchiveExporter(RepositoryFolderArchiveBackend(tmp))
            with self.assertRaisesRegex(ArchiveFinalizationError, "uncommitted worktree"):
                exporter.finalize_case(sample_case(), sample_snapshots())

    def test_empty_history_fails_closed(self):
        self.assertFalse(validate_case(sample_case(), []).ok)

    def test_history_reader_uses_smartxflow_api_not_supabase(self):
        session = FakeSession()
        with patch.dict(os.environ, {
            "SMARTXFLOW_LEARNING_API_BASE_URL": "https://preview.smartxflow.test",
            "SMARTXFLOW_LEARNING_API_TOKEN": "service-test-token",
        }, clear=False):
            result = fetch_selected_match_history("abc123def456", session=session)
        self.assertEqual(len(result.snapshots), 2)
        self.assertEqual(result.source_tables, ("moneyway_1x2_history", "dropping_1x2_history"))
        self.assertEqual(result.unavailable_optional_tables, ())
        self.assertEqual(session.headers["Authorization"], "Bearer service-test-token")
        self.assertEqual(session.last_url, "https://preview.smartxflow.test/api/internal/learning-archive/match/abc123def456/history")

    def test_history_reader_auth_failure_is_explicit(self):
        session = FakeSession(FakeResponse(401, {"error": "unauthorized"}))
        with patch.dict(os.environ, {
            "SMARTXFLOW_LEARNING_API_BASE_URL": "https://preview.smartxflow.test",
            "SMARTXFLOW_LEARNING_API_TOKEN": "wrong-token",
        }, clear=False):
            with self.assertRaisesRegex(SXFHistoryError, "authentication failed"):
                fetch_selected_match_history("abc123def456", session=session)

    def test_history_reader_rejects_wrong_match_payload(self):
        session = FakeSession(FakeResponse(200, {
            "match_id_hash": "different123",
            "histories": {"moneyway_1x2_history": [{"match_id_hash": "different123", "scraped_at": "2026-10-03T15:00:00Z"}]},
            "source_tables": ["moneyway_1x2_history"],
            "unavailable_optional_tables": [],
        }))
        with patch.dict(os.environ, {
            "SMARTXFLOW_LEARNING_API_BASE_URL": "https://preview.smartxflow.test",
            "SMARTXFLOW_LEARNING_API_TOKEN": "service-test-token",
        }, clear=False):
            with self.assertRaisesRegex(SXFHistoryError, "different match_id_hash"):
                fetch_selected_match_history("abc123def456", session=session)

    def test_bet_requires_market_selection_odds(self):
        case = sample_case()
        case["prediction"]["decision"] = "BET"
        case["prediction"]["entry_odds"] = None
        self.assertFalse(validate_case(case, sample_snapshots()).ok)


if __name__ == "__main__":
    unittest.main()
