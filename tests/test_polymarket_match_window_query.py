from datetime import datetime, timezone

from services import polymarket_client


class _Response:
    status_code = 200

    def __init__(self, rows):
        self._rows = rows

    def json(self):
        return self._rows


def _reset_cache():
    with polymarket_client._stored_matches_cache_lock:
        polymarket_client._stored_matches_cache.clear()


def test_stored_match_fetch_pushes_exact_window_to_postgrest(monkeypatch):
    _reset_cache()
    calls = []
    monkeypatch.setenv('SUPABASE_URL', 'https://example.supabase.co')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'service-role-test')

    def fake_get(url, headers, params, timeout):
        calls.append((url, params))
        return _Response([])

    monkeypatch.setattr(polymarket_client.requests, 'get', fake_get)
    lower = datetime(2026, 10, 6, 21, 0, tzinfo=timezone.utc)
    upper = datetime(2026, 10, 9, 9, 30, tzinfo=timezone.utc)
    assert polymarket_client._fetch_stored_matches(
        back_cutoff=lower,
        cutoff=upper,
    ) == []

    params = calls[0][1]
    assert ('kickoff_utc', 'gte.2026-10-06T21:00:00Z') in params
    assert ('kickoff_utc', 'lte.2026-10-09T09:30:00Z') in params
    assert ('limit', '5000') in params


def test_unbounded_registry_fetch_keeps_no_kickoff_filter(monkeypatch):
    _reset_cache()
    calls = []
    monkeypatch.setenv('SUPABASE_URL', 'https://example.supabase.co')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'service-role-test')

    def fake_get(url, headers, params, timeout):
        calls.append(params)
        return _Response([])

    monkeypatch.setattr(polymarket_client.requests, 'get', fake_get)
    assert polymarket_client._fetch_stored_matches() == []
    assert not any(key == 'kickoff_utc' for key, _value in calls[0])


def test_bounded_and_unbounded_match_caches_are_isolated(monkeypatch):
    _reset_cache()
    calls = []
    monkeypatch.setenv('SUPABASE_URL', 'https://example.supabase.co')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'service-role-test')

    def fake_get(url, headers, params, timeout):
        calls.append(params)
        return _Response([{'event_id': str(len(calls))}])

    monkeypatch.setattr(polymarket_client.requests, 'get', fake_get)
    lower = datetime(2026, 10, 6, 21, 0, tzinfo=timezone.utc)
    upper = datetime(2026, 10, 9, 9, 30, tzinfo=timezone.utc)

    first = polymarket_client._fetch_stored_matches(
        back_cutoff=lower,
        cutoff=upper,
    )
    repeated = polymarket_client._fetch_stored_matches(
        back_cutoff=lower,
        cutoff=upper,
    )
    broad = polymarket_client._fetch_stored_matches()

    assert first == repeated
    assert broad != first
    assert len(calls) == 2


def test_today_matches_passes_window_and_keeps_local_guard(monkeypatch):
    lower = datetime(2026, 10, 6, 21, 0, tzinfo=timezone.utc)
    upper = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
    captured = {}

    monkeypatch.setattr(
        polymarket_client,
        '_compute_match_window',
        lambda hours_ahead, day_filter: (lower, upper),
    )

    def fake_fetch(**kwargs):
        captured.update(kwargs)
        return [
            {
                'event_id': 'inside',
                'slug': 'inside',
                'home': 'A',
                'away': 'B',
                'kickoff_utc': '2026-10-07T18:00:00Z',
            },
            {
                'event_id': 'outside',
                'slug': 'outside',
                'home': 'C',
                'away': 'D',
                'kickoff_utc': '2026-10-09T18:00:00Z',
            },
        ]

    monkeypatch.setattr(polymarket_client, '_fetch_stored_matches', fake_fetch)
    rows = polymarket_client.get_today_matches(hours_ahead=36)
    assert captured == {'back_cutoff': lower, 'cutoff': upper}
    assert [row['event_id'] for row in rows] == ['inside']


def test_today_matches_fails_closed_without_stored_registry(monkeypatch):
    import pytest
    lower = datetime(2026, 10, 6, 21, 0, tzinfo=timezone.utc)
    upper = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(
        polymarket_client, '_compute_match_window',
        lambda hours_ahead, day_filter: (lower, upper),
    )
    monkeypatch.setattr(polymarket_client, '_fetch_stored_matches', lambda **kwargs: None)

    def reject_live_fallback(*args, **kwargs):
        raise AssertionError("public page must not start Gamma event pagination")

    monkeypatch.setattr(polymarket_client, '_get_today_matches_live', reject_live_fallback)
    with pytest.raises(RuntimeError, match='registry unavailable'):
        polymarket_client.get_today_matches(36, None)


def test_search_fails_closed_without_stored_registry(monkeypatch):
    import pytest
    monkeypatch.setattr(polymarket_client, '_fetch_stored_matches', lambda: None)

    def reject_live_fallback(*args, **kwargs):
        raise AssertionError("public search must not start Gamma event pagination")

    monkeypatch.setattr(polymarket_client, '_search_matches_live', reject_live_fallback)
    with pytest.raises(RuntimeError, match='registry unavailable'):
        polymarket_client.search_matches('Arsenal')


def test_server_role_header_preferred_and_anon_not_used(monkeypatch):
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'server-only-key')
    monkeypatch.setenv('SUPABASE_ANON_KEY', 'wrong-public-key')
    assert polymarket_client._supabase_headers() == {
        'apikey': 'server-only-key', 'Authorization': 'Bearer server-only-key',
    }


def test_no_server_role_fails_closed_even_with_anon(monkeypatch):
    _reset_cache()
    monkeypatch.delenv('SUPABASE_SERVICE_ROLE_KEY', raising=False)
    monkeypatch.setenv('SUPABASE_URL', 'https://example.supabase.co')
    monkeypatch.setenv('SUPABASE_ANON_KEY', 'wrong-public-key')
    assert polymarket_client._supabase_headers() == {}
    assert polymarket_client._fetch_stored_matches() is None


def test_unauthorized_registry_never_falls_back_to_gamma(monkeypatch):
    import pytest
    _reset_cache()
    monkeypatch.setenv('SUPABASE_URL', 'https://example.supabase.co')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'server-only-key')
    class Unauthorized:
        status_code = 401
    monkeypatch.setattr(polymarket_client.requests, 'get', lambda **kwargs: Unauthorized())
    monkeypatch.setattr(polymarket_client, '_get_today_matches_live',
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('Gamma called')))
    with pytest.raises(RuntimeError, match='registry unavailable'):
        polymarket_client.get_today_matches()
