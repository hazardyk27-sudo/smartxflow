"""Canonical market-data contract for SmartXFlow Analysis V2.

This module intentionally separates *real provider market data* from any model
inference. In particular, Double Chance money/price fields are valid only when
the provider exposes a real Double Chance market.
"""

from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass(frozen=True)
class SelectionFields:
    odds: str
    pct: str
    amount: str


@dataclass(frozen=True)
class MarketContract:
    key: str
    source_name: str
    current_table: str
    history_table: str
    selections: Dict[str, SelectionFields]
    optional: bool = False


MARKETS: Dict[str, MarketContract] = {
    "1X2": MarketContract(
        key="1X2",
        source_name="Match Odds",
        current_table="moneyway_1x2",
        history_table="moneyway_1x2_history",
        selections={
            "1": SelectionFields("odds1", "pct1", "amt1"),
            "X": SelectionFields("oddsx", "pctx", "amtx"),
            "2": SelectionFields("odds2", "pct2", "amt2"),
        },
    ),
    "DC": MarketContract(
        key="DC",
        source_name="Double Chance",
        current_table="moneyway_double_chance",
        history_table="moneyway_double_chance_history",
        selections={
            "1X": SelectionFields("odds1x", "pct1x", "amt1x"),
            "X2": SelectionFields("oddsx2", "pctx2", "amtx2"),
            "12": SelectionFields("odds12", "pct12", "amt12"),
        },
        optional=True,
    ),
    "DNB": MarketContract(
        key="DNB",
        source_name="Draw no Bet",
        current_table="moneyway_draw_no_bet",
        history_table="moneyway_draw_no_bet_history",
        selections={
            "1": SelectionFields("odds1", "pct1", "amt1"),
            "2": SelectionFields("odds2", "pct2", "amt2"),
        },
        optional=True,
    ),
    "OU25": MarketContract(
        key="OU25",
        source_name="Over/Under 2.5 Goals",
        current_table="moneyway_ou25",
        history_table="moneyway_ou25_history",
        selections={
            "O": SelectionFields("over", "pctover", "amtover"),
            "U": SelectionFields("under", "pctunder", "amtunder"),
        },
    ),
    "BTTS": MarketContract(
        key="BTTS",
        source_name="Both teams to Score?",
        current_table="moneyway_btts",
        history_table="moneyway_btts_history",
        selections={
            "Y": SelectionFields("yes", "pctyes", "amtyes"),
            "N": SelectionFields("no", "pctno", "amtno"),
        },
    ),
}


def get_market(key: str) -> MarketContract:
    """Return a canonical contract or raise on an unknown market."""
    return MARKETS[key.upper()]


def selection_fields(market_key: str, selection: str) -> SelectionFields:
    """Return the canonical storage fields for one market selection."""
    return get_market(market_key).selections[selection.upper()]


def table_pair(market_key: str) -> Tuple[str, str]:
    """Return (current_table, history_table)."""
    market = get_market(market_key)
    return market.current_table, market.history_table


def has_real_provider_payload(market_key: str, row: dict) -> bool:
    """True when at least one selection has a real quote or matched amount.

    Percentages alone do not count because they may be stale/derived output.
    This guard prevents empty optional provider markets from polluting history.
    """
    market = get_market(market_key)
    for fields in market.selections.values():
        if row.get(fields.odds) not in (None, "", "-"):
            return True
        if row.get(fields.amount) not in (None, "", "£ 0", "£0", 0):
            return True
    return False


def provider_market_names() -> Dict[str, str]:
    """Map canonical market key -> expected provider market name."""
    return {key: value.source_name for key, value in MARKETS.items()}
