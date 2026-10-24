"""Offline tests: original admin login, no second PIN/password for archive panel.

The existing admin session is checked, alongside CSRF, origin, token and date
validation. The system's legacy anon-key login is a separate security risk:
no new authentication mechanism is introduced by this archive-only patch.
"""
import os
import unittest
from unittest.mock import patch
from flask import Flask
import sxf_capitale_archive_admin as bridge


class ArchiveAdminTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "CAPITALE_GITHUB_ACTIONS_TOKEN": "MOCK_TOKEN_NOT_REAL",
            "SXF_ADMIN_PASSWORD_HASH": "",
        })
        self.env.start()
        self.app = Flask(__name__, template_folder="../templates")
        self.app.secret_key = "test-only-flask-secret"
        self.app.register_blueprint(bridge.blueprint)
        self.client = self.app.test_client()
        self.remote = patch.object(bridge, "_github_request", side_effect=self.fake_github)
        self.remote.start()
        self.requests = []

    def tearDown(self):
        self.remote.stop()
        self.env.stop()

    def fake_github(self, url, method="GET", payload=None):
        self.requests.append((url, method, payload))
        return {} if method == "POST" else {"workflow_runs": []}

    def admin(self):
        with self.client.session_transaction() as state:
            state["admin_authenticated"] = True
            state["sxf_capitale_archive_csrf"] = "csrf-unchanged"
        return {"Origin": "http://localhost", "X-CSRF-Token": "csrf-unchanged"}

    def test_not_logged_in_cannot_read_or_dispatch(self):
        self.assertEqual(self.client.get("/admin/sxf-archive").status_code, 403)
        self.assertEqual(self.client.get("/api/admin/sxf-archive/runs").status_code, 403)
        self.assertEqual(self.client.post("/api/admin/sxf-archive/dispatch",
                         headers={"Origin": "http://localhost", "X-CSRF-Token": "csrf-unchanged"},
                         json={"day": "2026-10-09", "kind": "full_snapshots"}).status_code, 403)
        self.assertEqual(self.requests, [])

    def test_github_dispatch_http_error_is_retained_for_diagnostics(self):
        from urllib.error import HTTPError
        h = self.admin()
        with patch.object(bridge, "_github_request",
                          side_effect=HTTPError("https://api.github.com/...", 403,
                                                "Forbidden", {}, None)):
            r = self.client.post("/api/admin/sxf-archive/dispatch", headers=h,
                                 json={"day": "2026-10-09", "kind": "concentrated"})
        self.assertEqual(r.status_code, 502)
        self.assertEqual(r.json["error"], "GITHUB_DISPATCH_REJECTED")
        self.assertEqual(r.json["http_status"], 403)
        response = self.client.get("/admin/sxf-archive")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"GitHub HTTP", response.data)

    def test_existing_admin_session_can_read_without_strong_password(self):
        self.admin()
        r = self.client.get("/admin/sxf-archive")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn(b"G\xc3\xbcvenli y\xc3\xb6netici giri\xc5\x9fi gerekli", r.data)
        self.assertEqual(self.client.get("/api/admin/sxf-archive/runs").status_code, 200)

    def test_cross_origin_and_bad_csrf_denied(self):
        h = self.admin()
        for headers in (
            {"Origin": "https://attacker.invalid", "X-CSRF-Token": h["X-CSRF-Token"]},
            {"Origin": "http://localhost", "X-CSRF-Token": "bad"},
            {"X-CSRF-Token": h["X-CSRF-Token"]},
        ):
            self.assertEqual(self.client.post("/api/admin/sxf-archive/dispatch", headers=headers,
                             json={"day": "2026-10-09", "kind": "full_snapshots"}).status_code, 403)
        self.assertEqual(self.requests, [])

    def test_dispatch_from_original_admin_session_and_duplicate_protection(self):
        h = self.admin()
        r = self.client.post("/api/admin/sxf-archive/dispatch", headers=h,
                             json={"day": "2026-10-09", "kind": "concentrated"})
        self.assertEqual(r.status_code, 202)
        self.assertEqual(r.json["status"], "QUEUED_NOT_ARCHIVED")
        self.assertEqual(self.requests[-1][2]["inputs"], {
            "day": "2026-10-09", "archive_kind": "concentrated"
        })
        self.assertEqual(self.client.post("/api/admin/sxf-archive/dispatch", headers=h,
                         json={"day": "2026-10-09", "kind": "concentrated"}).status_code, 409)

    def test_progress_counts_only_git_hub_uploaded_rows(self):
        self.admin()
        def remote(url, method="GET", payload=None):
            if "/releases/tags/" in url:
                return {"assets": [
                    {"name": "progress_total_rows_300.json"},
                    {"name": "concentrated_2026-10-22_1X2_part0001_rows_250.jsonl.gz"},
                ]}
            if "sxf-admin-archive.yml/runs" in url:
                return {"workflow_runs": [{
                    "display_title": "SXF 2026-10-22 / concentrated",
                    "status": "in_progress", "conclusion": None,
                    "created_at": "2026-10-24T12:00:00Z",
                    "html_url": "https://github.com/hazardyk27-sudo/capitale/actions/runs/123"
                }]}
            return {"workflow_runs": []}
        with patch.object(bridge, "_github_request", side_effect=remote):
            r = self.client.get("/api/admin/sxf-archive/progress?day=2026-10-22&kind=concentrated")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json["expected_rows"], 300)
        self.assertEqual(r.json["uploaded_rows"], 250)
        self.assertEqual(r.json["remaining_rows"], 50)
        self.assertEqual(r.json["percent"], 83)
        self.assertEqual(r.json["status"], "AKTARILIYOR")
        self.assertFalse(r.json["verified"])

    def test_progress_never_reports_100_without_verified_success(self):
        self.admin()
        def remote(url, method="GET", payload=None):
            if "/releases/tags/" in url:
                return {"assets": [
                    {"name": "progress_total_rows_300.json"},
                    {"name": "raw_2026-10-22_A_part0001_rows_300.jsonl.gz"},
                    {"name": "verification_receipt.json"},
                ]}
            if "sxf-admin-archive.yml/runs" in url:
                return {"workflow_runs": [{
                    "display_title": "SXF 2026-10-22 / full_snapshots",
                    "status": "in_progress", "conclusion": None,
                    "created_at": "2026-10-24T12:00:00Z",
                }]}
            return {"workflow_runs": []}
        with patch.object(bridge, "_github_request", side_effect=remote):
            r = self.client.get("/api/admin/sxf-archive/progress?day=2026-10-22&kind=full_snapshots")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json["percent"], 99)
        self.assertFalse(r.json["verified"])

    def test_progress_reports_100_after_receipt_and_success(self):
        self.admin()
        def remote(url, method="GET", payload=None):
            if "/releases/tags/" in url:
                return {"assets": [
                    {"name": "progress_total_rows_27.json"},
                    {"name": "concentrated_2026-10-22_1X2_part0001_rows_27.jsonl.gz"},
                    {"name": "verification_receipt.json"},
                ]}
            if "sxf-admin-archive.yml/runs" in url:
                return {"workflow_runs": [{
                    "display_title": "SXF 2026-10-22 / concentrated",
                    "status": "completed", "conclusion": "success",
                    "created_at": "2026-10-24T12:00:00Z",
                }]}
            return {"workflow_runs": []}
        with patch.object(bridge, "_github_request", side_effect=remote):
            r = self.client.get("/api/admin/sxf-archive/progress?day=2026-10-22&kind=concentrated")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json["percent"], 100)
        self.assertTrue(r.json["verified"])
        self.assertEqual(r.json["status"], "DOĞRULANDI")

    def test_active_two_day_batch_blocks_duplicate_single_day_dispatch(self):
        h = self.admin()
        def existing_batch(url, method="GET", payload=None):
            if method == "POST":
                self.fail("Duplicate dispatch must not reach GitHub")
            if "sxf-raw-two-day-batch.yml/runs" in url:
                return {"workflow_runs": [{
                    "display_title": "SXF full raw 2026-10-09 + next day",
                    "status": "in_progress", "conclusion": None,
                    "created_at": "2026-10-24T01:42:00Z",
                    "html_url": "https://github.com/hazardyk27-sudo/capitale/actions/runs/40050990059",
                }]}
            return {"workflow_runs": []}
        with patch.object(bridge, "_github_request", side_effect=existing_batch):
            for day in ("2026-10-09", "2026-10-10"):
                r = self.client.post("/api/admin/sxf-archive/dispatch",
                                     headers=h,
                                     json={"day": day, "kind": "full_snapshots"})
                self.assertEqual(r.status_code, 409)
                self.assertEqual(r.json["error"], "ARCHIVE_ALREADY_RUNNING")
                self.assertTrue(r.json["existing_run_url"].endswith("/40050990059"))

    def test_invalid_day_and_kind_and_missing_github_token(self):
        h = self.admin()
        for payload in (
            {"day": "2030-01-01", "kind": "full_snapshots"},
            {"day": "2026-10-09", "kind": "bad"},
            {"day": "../config", "kind": "concentrated"},
        ):
            self.assertEqual(self.client.post("/api/admin/sxf-archive/dispatch", headers=h,
                             json=payload).status_code, 400)
        with patch.dict(os.environ, {"CAPITALE_GITHUB_ACTIONS_TOKEN": ""}):
            self.assertEqual(self.client.post("/api/admin/sxf-archive/dispatch", headers=h,
                             json={"day": "2026-10-09", "kind": "full_snapshots"}).status_code, 503)


if __name__ == "__main__":
    unittest.main()
