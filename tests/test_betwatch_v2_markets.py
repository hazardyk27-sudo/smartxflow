from betwatch_client import map_market


def _r(name, odd=2.0, volume=100):
    return {"name": name, "odd": odd, "volume": volume}


def test_existing_match_odds_contract_is_unchanged():
    key, sels = map_market(
        "Match Odds",
        [_r("Arsenal"), _r("The Draw"), _r("Chelsea")],
        home="Arsenal",
        away="Chelsea",
    )
    assert key == "1X2"
    assert [code for code, _ in sels] == ["1", "X", "2"]


def test_double_chance_generic_labels():
    key, sels = map_market(
        "Double Chance",
        [_r("Home or Draw"), _r("Draw or Away"), _r("Home or Away")],
        home="Arsenal",
        away="Chelsea",
    )
    assert key == "DC"
    assert [code for code, _ in sels] == ["1X", "X2", "12"]


def test_double_chance_team_labels():
    key, sels = map_market(
        "Double Chance",
        [_r("Arsenal or Draw"), _r("Draw or Chelsea"), _r("Arsenal or Chelsea")],
        home="Arsenal",
        away="Chelsea",
    )
    assert key == "DC"
    assert [code for code, _ in sels] == ["1X", "X2", "12"]


def test_double_chance_compact_labels():
    key, sels = map_market(
        "Double Chance",
        [_r("1X"), _r("X2"), _r("12")],
        home="Arsenal",
        away="Chelsea",
    )
    assert key == "DC"
    assert [code for code, _ in sels] == ["1X", "X2", "12"]


def test_draw_no_bet_team_labels():
    key, sels = map_market(
        "Draw no Bet",
        [_r("Arsenal"), _r("Chelsea")],
        home="Arsenal",
        away="Chelsea",
    )
    assert key == "DNB"
    assert [code for code, _ in sels] == ["1", "2"]


def test_unknown_market_is_not_synthesized():
    key, sels = map_market(
        "Correct Score",
        [_r("1 - 0"), _r("0 - 1")],
        home="Arsenal",
        away="Chelsea",
    )
    assert key is None
    assert sels == []


def test_betwatch_fixture_hash_uses_repository_canonical_contract():
    from betwatch_prematch import make_match_id_hash as betwatch_hash
    from core.hash_utils import make_match_id_hash as canonical_hash

    cases = [
        ("Alianza FC (SLV)", "CD Platense", "Salvadoran Primera Division"),
        ("Tulsa Roughnecks FC", "New Mexico United", "US United Soccer League"),
        ("Maccabi Ihud Bnei Avtin", "Hapoel Bnei Bi'ina", "Israeli Liga Bet"),
        ("İstanbulspor FC", "Şanlıurfaspor SK", "Türkiye 1. Lig"),
    ]
    for home, away, league in cases:
        assert betwatch_hash(home, away, league) == canonical_hash(home, away, league)
