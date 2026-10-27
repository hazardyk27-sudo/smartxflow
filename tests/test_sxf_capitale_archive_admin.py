"""Offline checks for the PRATİK archive admin bridge."""
import datetime as dt
import os
import unittest
from unittest.mock import patch

from flask import Flask
import sxf_capitale_archive_admin as bridge


class PratikArchiveAdminTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "CAPITALE_GITHUB_ACTIONS_TOKEN": "MOCK_TOKEN_NOT_REAL",
        })
        self.env.start()
        self.app = Flask(__name__, template_folder="../templates")
        self.app.secret_key = "test-only-flask-secret"
        self.app.register_blueprint(bridge.blueprint)
        self.client = self.app.test_client()
        self.requests = []
        self.remote = patch.object(bridge, "_github_request", side_effect=self.fake_github)
        self.remote.start()

    def tearDown(self):
        self.remote.stop()
        self.env.stop()

    def fake_github(self, url, method="GET", payload=None):
        self.requests.append((url, method, payload))
        if method == "POST":
            return {}
        return {"workflow_runs": []}

    def recent_day(self):
        from datetime import date, timedelta
        from zoneinfo import ZoneInfo
        return (dt.datetime.now(bridge.ISTANBUL).date() - timedelta(days=2)).isoformat()

    def admin_headers(self):
        with self.client.session_transaction() as state:
            state["admin_authenticated"] = True
            state["sxf_capitale_archive_csrf"] = "csrf-test"
        return {"Origin": "http://localhost", "X-CSRF-Token": "csrf-test"}

    def test_admin_authentication_guards_page_and_api(self):
        self.assertEqual(self.client.get("/admin/sxf-archive").status_code, 403)
        self.assertEqual(self.client.get("/api/admin/sxf-archive/runs").status_code, 403)
        response = self.client.post(
            "/api/admin/sxf-archive/dispatch",
            headers={"Origin": "http://localhost", "X-CSRF-Token": "csrf-test"},
            json={"day": "2026-10-09"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.requests, [])

    def test_page_describes_daily_pratik_workflow(self):
        self.admin_headers()
        response = self.client.get("/admin/sxf-archive")
        self.assertEqual(response.status_code, 200)
        self.assertIn("PRATİK ARŞİV".encode(), response.data)
        self.assertIn("02:00 Türkiye saati".encode(), response.data)
        self.assertNotIn("Konsantre Arşiv".encode(), response.data)
        self.assertNotIn("Tüm Snapshotlar".encode(), response.data)

    def test_cross_origin_and_bad_csrf_are_rejected(self):
        self.admin_headers()
        for headers in (
            {"Origin": "https://attacker.invalid", "X-CSRF-Token": "csrf-test"},
            {"Origin": "http://localhost", "X-CSRF-Token": "bad"},
            {"X-CSRF-Token": "csrf-test"},
        ):
            response = self.client.post(
                "/api/admin/sxf-archive/dispatch", headers=headers,
                json={"day": "2026-10-09"},
            )
            self.assertEqual(response.status_code, 403)
        self.assertEqual(self.requests, [])

    def test_dispatch_sends_only_the_day_and_prevents_repeat(self):
        headers = self.admin_headers()
        day = self.recent_day()
        response = self.client.post(
            "/api/admin/sxf-archive/dispatch", headers=headers,
            json={"day": day},
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json["status"], "QUEUED_NOT_ARCHIVED")
        posts = [(url, payload) for url, method, payload in self.requests if method == "POST"]
        self.assertEqual(len(posts), 1)
        self.assertIn("/sxf-admin-archive.yml/dispatches", posts[0][0])
        self.assertEqual(posts[0][1], {
            "ref": "main", "inputs": {"day": day},
        })
        repeated = self.client.post(
            "/api/admin/sxf-archive/dispatch", headers=headers,
            json={"day": day},
        )
        self.assertEqual(repeated.status_code, 409)

    def test_active_date_run_is_not_dispatched_again(self):
        self.admin_headers()
        day = self.recent_day()

        def remote(url, method="GET", payload=None):
            self.requests.append((url, method, payload))
            if method == "POST":
                return {}
            return {"workflow_runs": [{
                "display_title": f"PRATİK {day}",
                "status": "in_progress",
                "html_url": "https://github.com/hazardyk27-sudo/capitale/actions/runs/123",
            }]}

        with patch.object(bridge, "_github_request", side_effect=remote):
            response = self.client.post(
                "/api/admin/sxf-archive/dispatch", headers=self.admin_headers(),
                json={"day": day},
            )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json["error"], "ARCHIVE_ALREADY_RUNNING")
        self.assertFalse(any(method == "POST" for _, method, _ in self.requests))

    def test_invalid_and_future_dates_are_rejected(self):
        headers = self.admin_headers()
        for day in ("2026-13-40", "not-a-date", "2099-01-01"):
            response = self.client.post(
                "/api/admin/sxf-archive/dispatch", headers=headers,
                json={"day": day},
            )
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.requests, [])

    def test_archive_days_are_newest_first_and_show_missing_and_partial(self):
        self.admin_headers()
        latest = dt.datetime.now(bridge.ISTANBUL).date() - dt.timedelta(days=1)
        previous = latest - dt.timedelta(days=1)
        index = {
            "archive_name": "PRATİK ARŞİV",
            "days": [{
                "date": previous.isoformat(), "fixtures": 12, "alarms": 7,
                "total_bytes": 2048, "source_archive_status": "PARTIAL",
                "checksums": {"checkpoints": "a" * 64, "alarms": "b" * 64},
            }],
        }
        with patch.object(bridge, "_archive_index", return_value=index):
            response = self.client.get("/api/admin/sxf-archive/days")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["days"][0]["date"], latest.isoformat())
        self.assertEqual(response.json["days"][0]["status"], "Eksik")
        self.assertEqual(response.json["days"][1]["date"], previous.isoformat())
        self.assertEqual(response.json["days"][1]["status"], "Arşivlendi · kaynak kısmi")
        self.assertEqual(response.json["days"][1]["bytes"], 2048)

    def test_run_history_returns_only_display_fields(self):
        self.admin_headers()
        response = self.client.get("/api/admin/sxf-archive/runs")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"runs": []})
