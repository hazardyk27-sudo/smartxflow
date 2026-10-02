from analysis_v2.presenter import present_signal
from analysis_v2.runtime import (
    RuntimeConfig,
    choose_engine_key,
    evaluate_source_candidate,
    run_runtime_batch,
)


MATCH_HASH = "a1b2c3d4e5f6"
HOME = "Home FC"
AWAY = "Away FC"
AS_OF = "2026-10-03T12:00:00Z"
KICKOFF = "2026-10-03T18:00:00Z"


def _row(at, market, selection, odds, volume, share, row_id):
    return {
        "id": row_id,
        "match_id_hash": MATCH_HASH,
        "market": market,
        "selection": selection,
        "odds": odds,
        "volume": volume,
        "share": share,
        "scraped_at_utc": at,
    }


def confirmed_rows():
    rows = []
    rid = 1
    cycles = [
        (
            "2026-10-03T06:00:00Z",
            {
                "1X2": {
                    "1": (2.20, 5000, 50),
                    "X": (3.20, 3000, 30),
                    "2": (3.40, 2000, 20),
                },
                "DNB": {
                    "1": (1.65, 5000, 62.5),
                    "2": (2.70, 3000, 37.5),
                },
                "DC": {
                    "1X": (1.40, 4500, 56.25),
                    "X2": (1.80, 3000, 37.5),
                    "12": (1.30, 500, 6.25),
                },
                "OU25": {
                    "O": (1.90, 4000, 50),
                    "U": (1.90, 4000, 50),
                },
                "BTTS": {
                    "Y": (1.85, 4000, 50),
                    "N": (1.95, 4000, 50),
                },
            },
        ),
        (
            "2026-10-03T10:00:00Z",
            {
                "1X2": {
                    "1": (2.25, 5000, 33.3),
                    "X": (3.25, 3000, 20),
                    "2": (3.30, 7000, 46.7),
                },
                "DNB": {
                    "1": (1.70, 5000, 41.7),
                    "2": (2.60, 7000, 58.3),
                },
                "DC": {
                    "1X": (1.42, 4500, 37.5),
                    "X2": (1.75, 7000, 58.3),
                    "12": (1.30, 500, 4.2),
                },
                "OU25": {
                    "O": (1.90, 4500, 50),
                    "U": (1.90, 4500, 50),
                },
                "BTTS": {
                    "Y": (1.85, 4500, 50),
                    "N": (1.95, 4500, 50),
                },
            },
        ),
        (
            "2026-10-03T11:30:00Z",
            {
                "1X2": {
                    "1": (2.28, 5000, 27.8),
                    "X": (3.25, 3000, 16.7),
                    "2": (3.15, 10000, 55.5),
                },
                "DNB": {
                    "1": (1.72, 5000, 31.25),
                    "2": (2.48, 11000, 68.75),
                },
                "DC": {
                    "1X": (1.43, 4500, 27.3),
                    "X2": (1.66, 11500, 69.7),
                    "12": (1.30, 500, 3.0),
                },
                "OU25": {
                    "O": (1.88, 5000, 50),
                    "U": (1.92, 5000, 50),
                },
                "BTTS": {
                    "Y": (1.84, 5000, 50),
                    "N": (1.96, 5000, 50),
                },
            },
        ),
        (
            AS_OF,
            {
                "1X2": {
                    "1": (2.30, 5000, 25),
                    "X": (3.30, 3000, 15),
                    "2": (3.00, 12000, 60),
                },
                "DNB": {
                    "1": (1.75, 5000, 29.4),
                    "2": (2.40, 12000, 70.6),
                },
                "DC": {
                    "1X": (1.45, 4500, 25.7),
                    "X2": (1.60, 12500, 71.4),
                    "12": (1.30, 500, 2.9),
                },
                "OU25": {
                    "O": (1.87, 5200, 50),
                    "U": (1.93, 5200, 50),
                },
                "BTTS": {
                    "Y": (1.83, 5200, 50),
                    "N": (1.97, 5200, 50),
                },
            },
        ),
    ]

    for at, markets in cycles:
        for market, selections in markets.items():
            for selection, (odds, volume, share) in selections.items():
                rows.append(
                    _row(
                        at,
                        market,
                        selection,
                        odds,
                        volume,
                        share,
                        rid,
                    )
                )
                rid += 1
    return rows


def test_confirmed_high_odds_direction_becomes_underdog_engine_and_real_x2():
    payload = evaluate_source_candidate(
        confirmed_rows(),
        match_id_hash=MATCH_HASH,
        home_team=HOME,
        away_team=AWAY,
        league="League",
        kickoff_utc=KICKOFF,
        source_market="1X2",
        source_selection="2",
        as_of=AS_OF,
    )
    assert payload is not None
    assert payload["engine_key"] == "underdog_pressure_v2"
    assert payload["recommended_market"] == "DC"
    assert payload["recommended_selection"] == "X2"
    assert payload["recommended_odds"] == 1.60
    assert (
        payload["features"]["explainable_confidence"]["user_state"]
        == "FIRSAT"
    )


def test_engine_choice_uses_price_money_class_not_high_money_pct_alone():
    engine = choose_engine_key(
        source_market="1X2",
        source_selection="2",
        classification={"primary_class": "NO_EDGE"},
        source_features={
            "current": {
                "odds": 3.40,
                "pct": 95,
                "amount": 15000,
                "market_volume": 18000,
            }
        },
    )
    assert engine is None


def test_watch_only_presenter_does_not_label_source_market_as_recommendation():
    row = {
        "signal_id": "sig_" + "a" * 32,
        "engine_key": "price_money_divergence_v2",
        "engine_version": "2.0.0",
        "match_id_hash": MATCH_HASH,
        "home_team": HOME,
        "away_team": AWAY,
        "league": "League",
        "kickoff_utc": KICKOFF,
        "trigger_at": AS_OF,
        "market_key": "1X2",
        "selection_code": "2",
        "trigger_odds": 3.40,
        "recommended_market": "1X2",
        "recommended_selection": "2",
        "features": {
            "market_selector": {
                "decision": "WATCH_ONLY",
                "recommended_odds": None,
            },
            "explainable_confidence": {
                "user_state": "UZAK_DUR",
                "components": {},
            },
        },
    }
    card = present_signal(row)
    assert card["recommendation"]["decision"] == "WATCH_ONLY"
    assert card["recommendation"]["market"] == ""
    assert card["recommendation"]["selection"] == ""
    assert card["recommendation"]["odds"] is None
    assert card["recommendation"]["direction_copy"] == (
        "Deplasman tarafı güçleniyor."
    )


class LedgerUnavailable:
    def list_signals(self, **kwargs):
        raise RuntimeError("relation does not exist")


class NoReadSnapshotClient:
    def fetch_match_rows(self, **kwargs):
        raise AssertionError("history must not be read when ledger is unavailable")


def test_runtime_fails_closed_before_history_reads_when_ledger_missing():
    result = run_runtime_batch(
        snapshot_client=NoReadSnapshotClient(),
        signal_store=LedgerUnavailable(),
        fixtures={},
        current_snapshot_rows=[],
        as_of=AS_OF,
    )
    assert result["skipped"] is True
    assert result["skip_reason"] == "V2_LEDGER_UNAVAILABLE"
    assert result["candidate_count"] == 0


class MemoryStore:
    def __init__(self):
        self.payloads = []

    def list_signals(self, **kwargs):
        return []

    def create_signal_once(self, payload):
        self.payloads.append(payload)
        return payload


class MemorySnapshotClient:
    def fetch_match_rows(self, **kwargs):
        assert kwargs["match_id_hash"] == MATCH_HASH
        return confirmed_rows()


def test_runtime_batch_persists_real_candidate_from_current_snapshot_cycle():
    current = [
        row
        for row in confirmed_rows()
        if row["scraped_at_utc"] == AS_OF
    ]
    store = MemoryStore()
    result = run_runtime_batch(
        snapshot_client=MemorySnapshotClient(),
        signal_store=store,
        fixtures={
            MATCH_HASH: {
                "match_id_hash": MATCH_HASH,
                "home_team": HOME,
                "away_team": AWAY,
                "league": "League",
                "kickoff_utc": KICKOFF,
            }
        },
        current_snapshot_rows=current,
        as_of=AS_OF,
        max_matches=10,
        runtime_config=RuntimeConfig(),
    )
    assert result.get("skipped") is not True
    assert result["signal_count"] >= 1
    assert any(
        payload["engine_key"] == "underdog_pressure_v2"
        and payload.get("recommended_selection") == "X2"
        for payload in store.payloads
    )
