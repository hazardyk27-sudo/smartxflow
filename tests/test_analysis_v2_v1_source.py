from analysis_v2.v1_source import (
    V1SignalSource,
    canonical_match_hash,
    fetch_all_v1_candidates,
    normalize_v1_row,
)


class _Response:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = [] if payload is None else payload

    def json(self):
        return self._payload


class _Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "timeout": timeout})
        if not self.responses:
            raise AssertionError("unexpected GET")
        return self.responses.pop(0)


def _underdog_row(**overrides):
    row = {
        "id": 10,
        "match_key": "Arsenal|Chelsea|2026-10-04",
        "home_team": "Arsenal",
        "away_team": "Chelsea",
        "league": "England Premier League",
        "match_date": "2026-10-04T18:00:00Z",
        "selection_code": "2",
        "odds": "3.40",
        "pct": "67.5",
        "amt": "£ 8,250",
        "volume": "£ 14,000",
        "created_at": "2026-10-03T12:00:00Z",
    }
    row.update(overrides)
    return row


def test_hash_is_derived_from_canonical_contract_when_legacy_row_has_none():
    row = _underdog_row()
    match_hash = canonical_match_hash(row)
    assert len(match_hash) == 12
    assert match_hash == canonical_match_hash(dict(row))


def test_existing_valid_hash_is_preserved():
    row = _underdog_row(match_id_hash="ABCDEF123456")
    assert canonical_match_hash(row) == "abcdef123456"


def test_underdog_trigger_fields_are_normalized_from_v1_columns():
    row = normalize_v1_row("underdog", _underdog_row())
    assert row["trigger_odds"] == "3.40"
    assert row["trigger_pct"] == "67.5"
    assert row["trigger_amount"] == "£ 8,250"
    assert row["trigger_volume"] == "£ 14,000"


def test_early_money_lock_does_not_invent_trigger_odds():
    row = normalize_v1_row(
        "early_money_lock",
        {
            "id": 11,
            "home_team": "A",
            "away_team": "B",
            "league": "L",
            "selection_code": "1",
            "pct_now": "87",
            "amt_now": "5000",
            "volume_now": "9000",
        },
    )
    assert "trigger_odds" not in row
    assert row["trigger_pct"] == "87"


def test_source_uses_get_only_and_builds_engine_first_candidate():
    session = _Session([_Response(200, [_underdog_row()])])
    source = V1SignalSource("https://example.supabase.co", "anon", session=session)
    batch = source.fetch_candidates("underdog")
    assert batch.row_count == 1
    assert batch.candidate_count == 1
    assert batch.skipped_count == 0
    assert batch.candidates[0].source_engine == "underdog_pressure_v1"
    assert len(session.calls) == 1
    assert "/rest/v1/underdog_signals?" in session.calls[0]["url"]


def test_source_http_failure_is_fail_closed():
    session = _Session([_Response(500, {"message": "error"})])
    source = V1SignalSource("https://example.supabase.co", "anon", session=session)
    try:
        source.fetch_rows("confirmed_money")
    except RuntimeError as exc:
        assert "V1_SOURCE_HTTP_500" in str(exc)
    else:
        raise AssertionError("HTTP failure must not create candidates")


def test_one_bad_row_is_skipped_without_losing_valid_rows():
    invalid = _underdog_row(id=12, selection_code="X")
    valid = _underdog_row(id=13)
    session = _Session([_Response(200, [invalid, valid])])
    source = V1SignalSource("https://example.supabase.co", "anon", session=session)
    batch = source.fetch_candidates("underdog")
    assert batch.row_count == 2
    assert batch.candidate_count == 1
    assert batch.skipped_count == 1
    assert batch.errors and batch.errors[0].startswith("12:")


def test_old_confirmed_money_v2_is_not_a_supported_source_engine():
    session = _Session([])
    source = V1SignalSource("https://example.supabase.co", "anon", session=session)
    try:
        source.fetch_rows("confirmed_money_v2")
    except ValueError as exc:
        assert "UNSUPPORTED_SOURCE_ENGINE" in str(exc)
    else:
        raise AssertionError("old CM V2 must not seed new V2")


def test_fetch_all_isolates_one_table_failure():
    responses = [
        _Response(200, [_underdog_row()]),
        _Response(500, {}),
        _Response(200, []),
        _Response(200, []),
    ]
    source = V1SignalSource(
        "https://example.supabase.co",
        "anon",
        session=_Session(responses),
    )
    batches = fetch_all_v1_candidates(source)
    assert batches["underdog_pressure_v1"].candidate_count == 1
    assert batches["confirmed_money_v1"].errors
    assert batches["early_money_lock_v1"].candidate_count == 0
