import unittest
from unittest.mock import patch

import app as smartx_app


class AnalysisAccessTests(unittest.TestCase):
    def setUp(self):
        smartx_app.app.config.update(TESTING=True, SECRET_KEY='analysis-access-test')
        smartx_app._analyses_cache = {
            'analysis': {'data': None, 'ts': 0},
            'moves': {'data': None, 'ts': 0},
        }
        self.client = smartx_app.app.test_client()

    def test_pro_license_session_can_open_analyses(self):
        with self.client.session_transaction() as session:
            session['license_key'] = 'SXF-PRO-TEST'
            session['license_plan'] = 'pro'

        with patch.object(smartx_app, '_legacy_license_session_valid', return_value=True), \
                patch.object(smartx_app.db, 'get_analyses', return_value=[{'id': 1}]):
            response = self.client.get('/api/analyses?category=analysis')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), [{'id': 1}])

    def test_core_license_session_gets_pro_required_not_login_required(self):
        with self.client.session_transaction() as session:
            session['license_key'] = 'SXF-CORE-TEST'
            session['license_plan'] = 'core'

        with patch.object(smartx_app, '_legacy_license_session_valid', return_value=True):
            response = self.client.get('/api/analyses?category=analysis')

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()['error'], 'PRO_REQUIRED')

    def test_pro_license_header_uses_cached_plan(self):
        smartx_app._validated_licenses['SXF-HEADER-PRO'] = {
            'plan': 'pro',
            'expires': None,
            'cached_at': 0,
        }

        with patch.object(smartx_app, '_legacy_license_session_valid', return_value=True), \
                patch.object(smartx_app.db, 'get_analyses', return_value=[{'id': 3}]):
            response = self.client.get(
                '/api/analyses?category=analysis',
                headers={'X-License-Key': 'SXF-HEADER-PRO'},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), [{'id': 3}])

    def test_invalid_license_without_account_gets_login_required(self):
        with patch.object(smartx_app, '_legacy_license_session_valid', return_value=False), \
                patch.object(smartx_app, 'resolve_account_session', return_value=(None, None)):
            response = self.client.get('/api/analyses?category=analysis')

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()['error'], 'LOGIN_REQUIRED')

    def test_pro_account_session_still_opens_analyses(self):
        user = {'id': 'user-1', 'email_confirmed': True}
        profile = {'plan': 'pro', 'subscription_status': 'active'}

        with patch.object(smartx_app, '_legacy_license_session_valid', return_value=False), \
                patch.object(smartx_app, 'resolve_account_session', return_value=(user, profile)), \
                patch.object(smartx_app.auth_helpers, 'is_membership_active', return_value=True), \
                patch.object(smartx_app.db, 'get_analyses', return_value=[{'id': 2}]):
            response = self.client.get('/api/analyses?category=analysis')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), [{'id': 2}])

    def test_test_mode_keeps_analysis_restricted(self):
        with self.client.session_transaction() as session:
            session['license_plan'] = 'test'

        response = self.client.get('/api/analyses?category=analysis')

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()['error'], 'PRO_REQUIRED')


class AccountSessionStatusTests(unittest.TestCase):
    def setUp(self):
        smartx_app.app.config.update(TESTING=True, SECRET_KEY='account-session-status-test')
        self.client = smartx_app.app.test_client()

    def test_valid_legacy_license_session_status_is_ok_without_exposing_key(self):
        license_key = 'SXF-LEGACY-STATUS-TEST'
        with self.client.session_transaction() as session:
            session['license_key'] = license_key
            session['license_plan'] = 'pro'
            session['license_days_remaining'] = 37

        with patch.object(smartx_app, '_legacy_license_session_valid', return_value=True), \
                patch.dict(smartx_app._validated_licenses, {
                    license_key: {'plan': 'pro', 'expires': None, 'days_left': 37}
                }):
            response = self.client.get('/api/auth/session-status')

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload, {
            'status': 'ok',
            'legacy_license': True,
            'plan': 'pro',
            'days_left': 37,
        })
        self.assertNotIn(license_key, response.get_data(as_text=True))

    def test_invalid_legacy_license_session_remains_login_required(self):
        with self.client.session_transaction() as session:
            session['license_key'] = 'SXF-INVALID-STATUS-TEST'

        with patch.object(smartx_app, '_legacy_license_session_valid', return_value=False):
            response = self.client.get('/api/auth/session-status')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {'status': 'login_required'})

    def test_expired_account_session_does_not_fall_back_to_valid_legacy_license(self):
        with self.client.session_transaction() as session:
            session['sb_access_token'] = 'expired-access-token'
            session['license_key'] = 'SXF-LEGACY-STATUS-TEST'

        with patch.object(smartx_app, 'resolve_account_session', return_value=(None, None)), \
                patch.object(smartx_app, '_legacy_license_session_valid', return_value=True) as legacy_valid:
            response = self.client.get('/api/auth/session-status')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {'status': 'session_expired'})
        legacy_valid.assert_not_called()

    def test_invalid_account_cookie_is_reported_as_expired_session(self):
        with self.client.session_transaction() as session:
            session['sb_access_token'] = 'expired-access-token'

        with patch.object(smartx_app, 'resolve_account_session', return_value=(None, None)):
            response = self.client.get('/api/auth/session-status')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {'status': 'session_expired'})

    def test_no_account_cookie_preserves_legacy_login_fallback(self):
        response = self.client.get('/api/auth/session-status')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {'status': 'login_required'})

    def test_test_mode_session_status_remains_ok(self):
        with self.client.session_transaction() as session:
            session['license_plan'] = 'test'

        response = self.client.get('/api/auth/session-status')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {'status': 'ok', 'test_mode': True})

    def test_active_account_session_status_includes_plan(self):
        user = {'id': 'user-1', 'email': 'member@example.com', 'email_confirmed': True}
        profile = {'plan': 'pro', 'subscription_expires_at': '2030-01-01T00:00:00Z'}

        with patch.object(smartx_app, 'resolve_account_session', return_value=(user, profile)), \
                patch.object(smartx_app.auth_helpers, 'is_membership_active', return_value=True):
            response = self.client.get('/api/auth/session-status')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['status'], 'ok')
        self.assertEqual(response.get_json()['plan'], 'pro')
        self.assertEqual(response.get_json()['subscription_expires_at'], profile['subscription_expires_at'])

    def test_unverified_account_session_status_is_preserved(self):
        user = {'id': 'user-1', 'email': 'member@example.com', 'email_confirmed': False}

        with patch.object(smartx_app, 'resolve_account_session', return_value=(user, None)):
            response = self.client.get('/api/auth/session-status')

        self.assertEqual(response.get_json(), {
            'status': 'email_unverified',
            'email': 'member@example.com'
        })

    def test_inactive_membership_status_is_preserved(self):
        user = {'id': 'user-1', 'email': 'member@example.com', 'email_confirmed': True}
        profile = {'plan': 'core', 'subscription_status': 'expired'}

        with patch.object(smartx_app, 'resolve_account_session', return_value=(user, profile)), \
                patch.object(smartx_app.auth_helpers, 'is_membership_active', return_value=False):
            response = self.client.get('/api/auth/session-status')

        self.assertEqual(response.get_json(), {
            'status': 'membership_required',
            'email': 'member@example.com'
        })


if __name__ == '__main__':
    unittest.main()
