from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from learning_archive.exporter import LearningArchiveExporter
from learning_archive.ssh_batch_backend import GitSshBatchArchiveBackend
from learning_archive.supabase_source import LearningArchiveHistoryPayload
from scripts.settle_due_learning_cases_fast import (
    _audit_finalized_package,
    _legacy_event,
    _select_finalization_history,
)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class PostmatchFastPreflightTests(unittest.TestCase):
    def test_finalized_package_integrity_checks_required_files_and_manifest_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp)
            payloads = {
                "case.json": b'{"case_id":"case-a"}\n',
                "evidence.json": b"[]\n",
                "settlement.json": b'{"status":"WIN"}\n',
            }
            snapshot_raw = json.dumps(
                [{"match_id_hash": "aaaaaaaaaaaa", "scraped_at": "2026-10-05T17:00:00Z"}],
                sort_keys=True,
                separators=(",", ":"),
            ).encode() + b"\n"
            snapshot_path = case_dir / "sxf_snapshots.json.gz"
            with snapshot_path.open("wb") as raw_handle:
                with gzip.GzipFile(filename="", mode="wb", fileobj=raw_handle, mtime=0) as handle:
                    handle.write(snapshot_raw)
            payloads["sxf_snapshots.json.gz"] = snapshot_path.read_bytes()
            for name, data in payloads.items():
                if name == "sxf_snapshots.json.gz":
                    continue
                (case_dir / name).write_bytes(data)

            checksum_bytes = (
                "\n".join(f"{_digest(payloads[name])}  {name}" for name in sorted(payloads)) + "\n"
            ).encode()
            (case_dir / "checksums.sha256").write_bytes(checksum_bytes)
            event = {"event": "FINALIZED", "checksum_summary": _digest(checksum_bytes)}

            self.assertEqual(_audit_finalized_package(case_dir, event), [])

            (case_dir / "settlement.json").unlink()
            self.assertIn("settlement.json missing", _audit_finalized_package(case_dir, event))

    def test_history_selection_uses_batch_db_without_touching_capture(self):
        payload = LearningArchiveHistoryPayload(
            match_id_hash="aaaaaaaaaaaa",
            match={},
            histories={
                "moneyway_1x2_history": [
                    {"match_id_hash": "aaaaaaaaaaaa", "scraped_at": "2026-10-05T17:00:00Z"}
                ]
            },
            source_tables=("moneyway_1x2_history",),
            unavailable_optional_tables=(),
        )
        rows, source = _select_finalization_history(
            Path("/path/that/does/not/exist"),
            "aaaaaaaaaaaa",
            {"aaaaaaaaaaaa": payload},
        )
        self.assertEqual(source, "SXF_DB_BATCH")
        self.assertEqual(rows[0]["_archive_source_table"], "moneyway_1x2_history")

    def test_history_selection_directly_uses_archive_capture_when_db_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp)
            captures = case_dir / "captures"
            captures.mkdir()
            with gzip.open(captures / "20261005T170000Z.json.gz", "wt", encoding="utf-8") as handle:
                json.dump(
                    [{"match_id_hash": "aaaaaaaaaaaa", "scraped_at": "2026-10-05T17:00:00Z"}],
                    handle,
                )
            rows, source = _select_finalization_history(
                case_dir,
                "aaaaaaaaaaaa",
                {},
            )
            self.assertEqual(source, "ARCHIVE_CAPTURE_FALLBACK")
            self.assertEqual(rows[0]["match_id_hash"], "aaaaaaaaaaaa")

    def test_legacy_event_is_classified_before_new_pipeline(self):
        self.assertTrue(_legacy_event({"event": "SETTLED_PENDING_HISTORY"}))
        self.assertFalse(_legacy_event({"event": "CAPTURED"}))

    def test_exporter_prefers_batch_ssh_backend_when_token_also_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            key = Path(tmp) / "archive_key"
            key.write_text("test-key\n", encoding="utf-8")
            key.chmod(0o600)
            with patch.dict(
                os.environ,
                {
                    "LEARNING_ARCHIVE_GIT_SSH_KEY": str(key),
                    "GITHUB_TOKEN": "generic-token",
                },
                clear=False,
            ):
                exporter = LearningArchiveExporter.from_env()
            self.assertIsInstance(exporter.backend, GitSshBatchArchiveBackend)


if __name__ == "__main__":
    unittest.main()
