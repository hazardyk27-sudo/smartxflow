from pathlib import Path

from services.supabase_client import SupabaseClient


MARKETS = (
    'moneyway_1x2',
    'moneyway_ou25',
    'moneyway_btts',
    'dropping_1x2',
    'dropping_ou25',
    'dropping_btts',
)


class _Response:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _HTTP:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, url, headers, json, timeout):
        self.calls.append((url, json, timeout))
        return self.response


def _client(monkeypatch, response):
    client = SupabaseClient.__new__(SupabaseClient)
    client.url = 'https://example.supabase.co'
    client.key = 'anon-test'
    client._http_client = None
    http = _HTTP(response)
    monkeypatch.setattr(client, '_get_http_client', lambda: http)
    return client, http


def test_bulk_rpc_uses_one_http_call_and_preserves_market_shape(monkeypatch):
    payload = {market: [] for market in MARKETS}
    payload['moneyway_1x2'] = [{
        'home': 'Alpha',
        'away': 'Beta',
        'league': 'League',
        'scraped_at': '2026-10-07T12:00:00Z',
        'odds1': 1.9,
        'oddsx': 3.2,
        'odds2': 4.0,
    }]
    client, http = _client(monkeypatch, _Response(200, payload))

    result = client.get_match_history_bulk('Alpha', 'Beta', 'League')

    assert result is not None
    assert set(result) == set(MARKETS)
    assert result['moneyway_1x2'][0]['Odds1'] == 1.9
    assert len(http.calls) == 1
    url, body, timeout = http.calls[0]
    assert url.endswith('/rest/v1/rpc/sxf_match_history_bulk_v1')
    assert body == {
        'p_home': 'Alpha',
        'p_away': 'Beta',
        'p_league': 'League',
    }
    assert timeout == 30


def test_bulk_rpc_empty_success_is_not_treated_as_failure(monkeypatch):
    client, http = _client(
        monkeypatch,
        _Response(200, {market: [] for market in MARKETS}),
    )
    result = client.get_match_history_bulk('Alpha', 'Beta')
    assert result == {market: [] for market in MARKETS}
    assert len(http.calls) == 1


def test_bulk_rpc_non_200_returns_none_for_legacy_fallback(monkeypatch):
    client, http = _client(monkeypatch, _Response(404, {}))
    assert client.get_match_history_bulk('Alpha', 'Beta', 'League') is None
    assert len(http.calls) == 1


def test_bulk_endpoint_wires_rpc_before_parallel_fallback():
    source = Path('app.py').read_text()
    route_start = source.index("@app.route('/api/match/history/bulk')")
    route_end = source.index("@app.route('/api/favorite/toggle'", route_start)
    route = source[route_start:route_end]
    rpc_call = route.index('db.get_match_history_bulk(')
    fallback_pool = route.index('ThreadPoolExecutor(max_workers=6)', rpc_call)
    assert rpc_call < fallback_pool
    assert 'if bulk_histories is not None:' in route
    assert 'history_override=bulk_histories.get(market, [])' in route


def test_bulk_rpc_migration_is_security_invoker_and_capped():
    sql = Path('migrations/2026_10_07_match_history_bulk_rpc.sql').read_text().lower()
    assert 'security invoker' in sql
    assert 'sxf_match_history_bulk_v1' in sql
    assert sql.count('limit 10000') == 6
    for market in MARKETS:
        assert f'public.{market}_history' in sql
