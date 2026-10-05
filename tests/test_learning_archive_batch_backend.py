from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from learning_archive.package import ArchivePackage
from learning_archive.ssh_batch_backend import GitSshBatchArchiveBackend


class LearningArchiveBatchBackendTests(unittest.TestCase):
    def _run(self, argv: list[str], cwd: Path | None = None) -> str:
        result = subprocess.run(
            argv,
            cwd=str(cwd) if cwd else None,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        return result.stdout.strip()

    def _package(self, case_id: str) -> tuple[ArchivePackage, dict]:
        case_path = f"cases/2026/10/05/{case_id}"
        files = {
            "case.json": (json.dumps({"case_id": case_id}, sort_keys=True) + "\n").encode(),
            "evidence.json": b"[]\n",
            "settlement.json": b'{"status":"WIN"}\n',
            "sxf_snapshots.json.gz": b"deterministic-test-snapshot",
            "checksums.sha256": b"test-checksums\n",
        }
        package = ArchivePackage(
            case_id=case_id,
            case_path=case_path,
            files=files,
            checksum_summary="summary-" + case_id,
            package_kind="FINALIZED",
            event_key="final",
        )
        case = {
            "archive_schema_version": 1,
            "case_id": case_id,
            "match": {"match_id_hash": "hash-" + case_id},
            "prediction": {
                "prediction_at": "2026-10-05T10:00:00Z",
                "decision": "BET",
            },
            "settlement": {"status": "WIN"},
        }
        return package, case

    def test_batch_force_stages_ignored_json_and_uses_one_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seed = root / "seed"
            bare = root / "remote.git"
            key = root / "archive_ed25519"
            key.write_text("test-key-placeholder\n", encoding="utf-8")
            key.chmod(0o600)

            self._run(["git", "init", "-b", "learning-archive", str(seed)])
            self._run(["git", "config", "user.name", "test"], cwd=seed)
            self._run(["git", "config", "user.email", "test@example.invalid"], cwd=seed)
            (seed / ".gitignore").write_text("*.json\n", encoding="utf-8")
            self._run(["git", "add", ".gitignore"], cwd=seed)
            self._run(["git", "commit", "-m", "seed"], cwd=seed)
            self._run(["git", "clone", "--bare", str(seed), str(bare)])

            backend = GitSshBatchArchiveBackend(key)
            backend.remote_url = str(bare)
            first = self._package("case-a")
            second = self._package("case-b")
            results = backend.write_cases([first, second])

            self.assertEqual(len(results), 2)
            self.assertEqual(results[0].commit_sha, results[1].commit_sha)
            self.assertEqual(
                self._run(["git", "--git-dir", str(bare), "rev-list", "--count", "learning-archive"]),
                "2",
            )
            for case_id in ("case-a", "case-b"):
                path = f"learning_archive_data/cases/2026/10/05/{case_id}/settlement.json"
                payload = self._run(["git", "--git-dir", str(bare), "show", f"learning-archive:{path}"])
                self.assertEqual(payload, '{"status":"WIN"}')

    def test_idempotent_batch_reuses_existing_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seed = root / "seed"
            bare = root / "remote.git"
            key = root / "archive_ed25519"
            key.write_text("test-key-placeholder\n", encoding="utf-8")
            key.chmod(0o600)

            self._run(["git", "init", "-b", "learning-archive", str(seed)])
            self._run(["git", "config", "user.name", "test"], cwd=seed)
            self._run(["git", "config", "user.email", "test@example.invalid"], cwd=seed)
            (seed / ".gitignore").write_text("*.json\n", encoding="utf-8")
            self._run(["git", "add", ".gitignore"], cwd=seed)
            self._run(["git", "commit", "-m", "seed"], cwd=seed)
            self._run(["git", "clone", "--bare", str(seed), str(bare)])

            backend = GitSshBatchArchiveBackend(key)
            backend.remote_url = str(bare)
            entry = self._package("case-a")
            first = backend.write_cases([entry])[0]
            second = backend.write_cases([entry])[0]

            self.assertFalse(first.idempotent)
            self.assertTrue(second.idempotent)
            self.assertEqual(first.commit_sha, second.commit_sha)
            self.assertEqual(
                self._run(["git", "--git-dir", str(bare), "rev-list", "--count", "learning-archive"]),
                "2",
            )


if __name__ == "__main__":
    unittest.main()
