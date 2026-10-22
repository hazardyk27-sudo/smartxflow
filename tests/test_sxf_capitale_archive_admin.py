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
