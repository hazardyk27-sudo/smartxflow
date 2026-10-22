"""Offline tests for private .env provisioning; no real credentials."""
import os
import pathlib
import tempfile
import unittest
from unittest.mock import patch

from scripts import configure_sxf_archive_access as access

from scripts.configure_sxf_archive_access import save_secret_lines, check_file


class ArchiveConfigTests(unittest.TestCase):
    def test_atomic_update_preserves_unrelated_keys_and_permissions(self):
        with tempfile.TemporaryDirectory() as temp:
            target = pathlib.Path(temp) / ".env"
            target.write_text("EXISTING_KEY=keep\n", "utf-8")
            target.chmod(0o600)
            save_secret_lines(target, {"SXF_ADMIN_PASSWORD_HASH": "mockhash",
                                       "CAPITALE_GITHUB_ACTIONS_TOKEN": "test-not-secret"})
            content = target.read_text("utf-8")
            self.assertIn("EXISTING_KEY=keep", content)
            self.assertIn("SXF_ADMIN_PASSWORD_HASH=mockhash", content)
            self.assertIn("CAPITALE_GITHUB_ACTIONS_TOKEN=test-not-secret", content)
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_token_only_does_not_change_admin_password(self):
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / ".env"
            path.write_text("SXF_ADMIN_PASSWORD_HASH=original-admin-hash\n"
                            "CAPITALE_GITHUB_ACTIONS_TOKEN=old-invalid-token\n", "utf-8")
            path.chmod(0o600)
            with patch("sys.argv", ["setup.py", "--env-file", str(path), "--token-only"]), \
                    patch.object(access.getpass, "getpass", return_value="github_pat_valid_mocked_token_xxxxx"), \
                    patch.object(access, "verify_workflow_token") as check:
                access.main()
            check.assert_called_once()
            data = path.read_text("utf-8")
            self.assertIn("SXF_ADMIN_PASSWORD_HASH=original-admin-hash", data)
            self.assertIn("CAPITALE_GITHUB_ACTIONS_TOKEN=github_pat_valid_mocked_token_xxxxx", data)
            self.assertNotIn("old-invalid-token", data)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_invalid_replacement_is_rejected_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / ".env"
            original = "SXF_ADMIN_PASSWORD_HASH=original\nCAPITALE_GITHUB_ACTIONS_TOKEN=old\n"
            path.write_text(original, "utf-8")
            path.chmod(0o600)
            with patch("sys.argv", ["setup.py", "--env-file", str(path), "--token-only"]), \
                    patch.object(access.getpass, "getpass", return_value="bad"):
                with self.assertRaises(SystemExit):
                    access.main()
            self.assertEqual(path.read_text("utf-8"), original)

    def test_reject_world_readable_env(self):
        with tempfile.TemporaryDirectory() as temp:
            target = pathlib.Path(temp) / ".env"
            target.write_text("EXISTING_KEY=keep\n", "utf-8")
            target.chmod(0o644)
            with self.assertRaises(RuntimeError):
                check_file(target)


if __name__ == "__main__":
    unittest.main()
