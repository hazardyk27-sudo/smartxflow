from analysis_v2.market_contract import (
    get_market,
    has_real_provider_payload,
    selection_fields,
    table_pair,
)


def test_double_chance_contract_fields():
    fields = selection_fields("DC", "X2")
    assert fields.odds == "oddsx2"
    assert fields.pct == "pctx2"
    assert fields.amount == "amtx2"
    assert table_pair("DC") == (
        "moneyway_double_chance",
        "moneyway_double_chance_history",
    )


def test_optional_market_requires_real_quote_or_amount():
    assert not has_real_provider_payload(
        "DC",
        {"odds1x": "", "oddsx2": "", "odds12": "", "amt1x": "", "amtx2": "", "amt12": ""},
    )
    assert has_real_provider_payload("DC", {"oddsx2": "1.42"})
    assert has_real_provider_payload("DC", {"amtx2": "£ 1234"})


def test_core_market_contract_remains_available():
    market = get_market("1x2")
    assert market.current_table == "moneyway_1x2"
    assert tuple(market.selections) == ("1", "X", "2")
