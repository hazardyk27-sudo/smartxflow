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


if __name__ == '__main__':
    unittest.main()