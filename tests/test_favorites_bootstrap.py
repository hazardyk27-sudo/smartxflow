from pathlib import Path

from services.supabase_client import SupabaseClient


class _Response:
    status_code = 200
    def json(self):
        return [
            {'license_key': 'u1', 'match_key': 'A|B|L'},
            {'license_key': 'u2', 'match_key': 'A|B|L'},
            {'license_key': 'u1', 'match_key': 'C|D|L'},
        ]


class _HTTP:
    def __init__(self):
        self.calls = []
    def get(self, url, headers, timeout):
        self.calls.append((url, timeout))
        return _Response()


def test_supabase_favorites_bootstrap_uses_one_table_read(monkeypatch):
    client = SupabaseClient.__new__(SupabaseClient)
    client.url = 'https://example.supabase.co'
    client.key = 'anon-test'
    client._http_client = None
    http = _HTTP()
    monkeypatch.setattr(client, '_ensure_favorites_table', lambda: True)
    monkeypatch.setattr(client, '_get_http_client', lambda: http)

    data = client.get_favorites_bootstrap('u1')
    assert data == {
        'favorites': ['A|B|L', 'C|D|L'],
        'counts': {'A|B|L': 2, 'C|D|L': 1},
    }
    assert len(http.calls) == 1
    assert http.calls[0][0].endswith('/rest/v1/license_favorites?select=license_key,match_key')
    assert http.calls[0][1] == 15


def test_app_exposes_bootstrap_with_legacy_failure_signal():
    source = Path('app.py').read_text()
    assert "@app.route('/api/favorites/bootstrap')" in source
    assert 'db.get_favorites_bootstrap(license_key)' in source
    assert "'favorites_bootstrap_unavailable'" in source
    assert ', 503' in source
