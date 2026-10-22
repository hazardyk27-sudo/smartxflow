"""No-network archive admin tests with dedicated admin password gating."""
import os
import time
import unittest
from unittest.mock import patch

from flask import Flask
from werkzeug.security import generate_password_hash
import sxf_capitale_archive_admin as bridge


class ArchiveAdminTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "CAPITALE_GITHUB_ACTIONS_TOKEN": "MOCK_TOKEN_NOT_REAL",
            "SXF_ADMIN_PASSWORD_HASH": generate_password_hash(
                "local-test-password-only", method="pbkdf2:sha256:260000"
            ),
        })
        self.env.start()
        self.app = Flask(__name__)
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

    def admin(self, strong=True):
        with self.client.session_transaction() as state:
            state["admin_authenticated"] = True
            state["sxf_capitale_archive_csrf"] = "csrf-unchanged"
            if strong:
                state["sxf_admin_auth_mode"] = "PASSWORD_V2"
                state["sxf_admin_login_at"] = int(time.time())
        return {"Origin": "http://localhost", "X-CSRF-Token": "csrf-unchanged"}

    def test_admin_required_and_legacy_anon_cannot_dispatch(self):
        self.assertEqual(self.client.get("/api/admin/sxf-archive/runs").status_code, 403)
        h = self.admin(strong=False)
        self.assertEqual(self.client.post("/api/admin/sxf-archive/dispatch",
                         headers=h, json={"day": "2026-10-09", "kind": "full_snapshots"}).status_code, 403)
        self.assertEqual(self.client.get("/admin/sxf-archive").status_code, 200)
        self.assertEqual(self.requests, [])

    def test_csrf_and_wrong_origin_rejected(self):
        h = self.admin()
        self.assertEqual(self.client.post("/api/admin/sxf-archive/dispatch",
                         headers={"Origin": "https://attacker.invalid", "X-CSRF-Token": h["X-CSRF-Token"]},
                         json={"day": "2026-10-09", "kind": "full_snapshots"}).status_code, 403)
        self.assertEqual(self.client.post("/api/admin/sxf-archive/dispatch",
                         headers={"Origin": "http://localhost", "X-CSRF-Token": "bad"},
                         json={"day": "2026-10-09", "kind": "full_snapshots"}).status_code, 403)

    def test_dispatch_queues_but_never_claims_archived(self):
        h = self.admin()
        r = self.client.post("/api/admin/sxf-archive/dispatch",
                             headers=h, json={"day": "2026-10-09", "kind": "concentrated"})
        self.assertEqual(r.status_code, 202)
        self.assertEqual(r.json["status"], "QUEUED_NOT_ARCHIVED")
        self.assertEqual(self.requests[-1][2]["inputs"], {"day": "2026-10-09", "archive_kind": "concentrated"})
        self.assertEqual(self.client.post("/api/admin/sxf-archive/dispatch",
                         headers=h, json={"day": "2026-10-09", "kind": "concentrated"}).status_code, 409)

    def test_invalid_day_kind_expired_session_and_missing_hash(self):
        h = self.admin()
        for payload in (
            {"day": "2030-01-01", "kind": "full_snapshots"},
            {"day": "2026-10-09", "kind": "bad"},
            {"day": "../config", "kind": "concentrated"},
        ):
            self.assertEqual(self.client.post("/api/admin/sxf-archive/dispatch",
                             headers=h, json=payload).status_code, 400)
        with self.client.session_transaction() as state:
            state["sxf_admin_login_at"] = int(time.time()) - 9*3600
        self.assertEqual(self.client.get("/api/admin/sxf-archive/runs").status_code, 403)
        with patch.dict(os.environ, {"SXF_ADMIN_PASSWORD_HASH": ""}):
            self.assertEqual(self.client.get("/api/admin/sxf-archive/runs").status_code, 403)

    def test_missing_token_fails_closed(self):
        h = self.admin()
        with patch.dict(os.environ, {"CAPITALE_GITHUB_ACTIONS_TOKEN": ""}):
            self.assertEqual(self.client.post("/api/admin/sxf-archive/dispatch",
                             headers=h, json={"day": "2026-10-09", "kind": "full_snapshots"}).status_code, 503)


if __name__ == "__main__":
    unittest.main()
