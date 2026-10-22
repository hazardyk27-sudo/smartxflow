"""No-network security contract tests for the gated CAPITALE archive button."""
import os
import time
import unittest
from unittest.mock import patch

from flask import Flask
import sxf_capitale_archive_admin as bridge


class ArchiveAdminTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "SXF_ARCHIVE_ADMIN_PIN": "a-strong-isolated-test-pin",
            "CAPITALE_GITHUB_ACTIONS_TOKEN": "MOCK_TOKEN_NOT_REAL",
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

    def admin(self):
        with self.client.session_transaction() as state:
            state["admin_authenticated"] = True
            state["sxf_capitale_archive_csrf"] = "csrf-unchanged"
        return {"Origin": "http://localhost", "X-CSRF-Token": "csrf-unchanged"}

    def unlock(self):
        header = self.admin()
        result = self.client.post(
            "/api/admin/sxf-archive/unlock", headers=header,
            json={"pin": os.environ["SXF_ARCHIVE_ADMIN_PIN"]},
        )
        self.assertEqual(result.status_code, 200)
        return {"Origin": "http://localhost", "X-CSRF-Token": result.json["csrf_token"]}

    def test_requires_admin_and_separate_unlock(self):
        self.assertEqual(self.client.get("/api/admin/sxf-archive/runs").status_code, 403)
        h = self.admin()
        self.assertEqual(self.client.post("/api/admin/sxf-archive/dispatch",
                         headers=h, json={"day": "2026-10-09", "kind": "full_snapshots"}).status_code, 403)

    def test_wrong_origin_and_pin_rejected(self):
        h = self.admin()
        self.assertEqual(self.client.post("/api/admin/sxf-archive/unlock",
                         headers={"Origin": "https://attacker.invalid", "X-CSRF-Token": h["X-CSRF-Token"]},
                         json={"pin": os.environ["SXF_ARCHIVE_ADMIN_PIN"]}).status_code, 403)
        self.assertEqual(self.client.post("/api/admin/sxf-archive/unlock", headers=h,
                         json={"pin": "incorrect"}).status_code, 403)

    def test_dispatch_is_queued_never_claims_archived(self):
        h = self.unlock()
        result = self.client.post("/api/admin/sxf-archive/dispatch", headers=h,
                                  json={"day": "2026-10-09", "kind": "concentrated"})
        self.assertEqual(result.status_code, 202)
        self.assertEqual(result.json["status"], "QUEUED_NOT_ARCHIVED")
        self.assertEqual(self.requests[-1][1], "POST")
        self.assertEqual(self.requests[-1][2]["inputs"], {"day": "2026-10-09", "archive_kind": "concentrated"})
        self.assertEqual(self.client.post("/api/admin/sxf-archive/dispatch", headers=h,
                         json={"day": "2026-10-09", "kind": "concentrated"}).status_code, 409)

    def test_invalid_day_kind_and_expired_unlock(self):
        h = self.unlock()
        for payload in (
            {"day": "2030-01-01", "kind": "full_snapshots"},
            {"day": "2026-10-09", "kind": "bad"},
            {"day": "../config", "kind": "concentrated"},
        ):
            self.assertEqual(self.client.post("/api/admin/sxf-archive/dispatch",
                             headers=h, json=payload).status_code, 400)
        with self.client.session_transaction() as state:
            state["sxf_capitale_archive_unlocked_at"] = int(time.time()) - 1900
        self.assertEqual(self.client.get("/api/admin/sxf-archive/runs").status_code, 403)


if __name__ == "__main__":
    unittest.main()
