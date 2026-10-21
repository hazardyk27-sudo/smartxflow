"""Betwatch source fidelity: explicit zero is not a missing market outcome."""
from datetime import datetime,timezone
from decimal import Decimal

from core.moneyway_quote_fidelity import observed_snapshot_quote
from core.moneyway_ingest_quality import summarize_ingest_quality
from base_signal_engine.rules import Snapshot,Quote


def _snapshot(market, originals):
    total=sum(float(r["volume"]) for r in originals if r.get("volume") is not None)
    rows=[]
    for selection,r in zip(("1","X","2"),originals):
        val=float(r.get("volume") or 0)
        odds,volume,share=observed_snapshot_quote(r,val,total)
        rows.append({"fixture_uid":"fixture-1","market":market,
                     "scraped_at_utc":"2026-10-21T15:00:00Z",
                     "selection":selection,"odds":odds,"volume":volume,"share":share})
    return rows


def test_provider_zero_on_draw_is_preserved_as_actual_zero_and_complete_1x2():
    rows=_snapshot("1X2",[{"odd":1.7,"volume":1800},
                         {"odd":3.2,"volume":0},
                         {"odd":5.1,"volume":200}])
    assert rows[1]["volume"]==0
    assert rows[1]["share"]==0
    report=summarize_ingest_quality(rows)
    assert report["1X2"]["complete"]==1
    q={r["selection"]:Quote(r["odds"],r["volume"],r["share"]) for r in rows}
    snap=Snapshot("1X2",datetime(2026,10,21,15,tzinfo=timezone.utc),q)
    assert snap.complete is True
    assert snap.quotes["X"].amount==Decimal("0")


def test_missing_volume_stays_unknown_even_when_odds_is_present():
    rows=_snapshot("1X2",[{"odd":1.7,"volume":1800},
                         {"odd":3.2},
                         {"odd":5.1,"volume":200}])
    assert rows[1]["volume"] is None and rows[1]["share"] is None
    assert summarize_ingest_quality(rows)["1X2"]["invalid_fields"]==1


def test_missing_runner_never_becomes_zero_from_existing_empty_dict():
    assert observed_snapshot_quote({},0,2000)==(None,None,None)


def test_empty_and_invalid_volume_remains_unknown_not_proven_zero():
    for value in (None,"","n/a",-1,"NaN"):
        odd,volume,share=observed_snapshot_quote({"odd":2.5,"volume":value},0,2000)
        assert odd==2.5 and volume is None and share is None


def test_explicit_zero_with_no_market_volume_cannot_make_complete_snapshot():
    odd,volume,share=observed_snapshot_quote({"odd":2.6,"volume":0},0,0)
    assert odd==2.6 and volume==0 and share is None


def test_bad_odds_never_qualify_signal():
    for val in (None,"",0,0.5,"NaN","garbage"):
        odds,volume,share=observed_snapshot_quote({"odd":val,"volume":0},0,2000)
        assert odds is None
        assert volume==0 and share==0


def test_no_synthetic_quote_from_unobserved_source_side():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    scraper=(root/"betwatch_prematch.py").read_text()
    assert scraper.count("observed_snapshot_quote(r, v, total)")==3
    assert "from core.moneyway_quote_fidelity import observed_snapshot_quote" in scraper
    assert "for sel, r, v in" in scraper
    assert 'runners_by_sel.get("X", {})' in scraper
