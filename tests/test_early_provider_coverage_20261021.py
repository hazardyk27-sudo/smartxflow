from datetime import datetime,timedelta,timezone
from pathlib import Path

from core.early_provider_coverage import summarize_early_provider_coverage
from betwatch_client import map_market

NOW=datetime(2026,10,21,16,0,tzinfo=timezone.utc)


def fixture(hours,runners=None,market=True):
    return {"kickoff":(NOW+timedelta(hours=hours)).isoformat(),
            "teams":{"v1":"Home","v2":"Away"},
            "markets":[{"name":"Match Odds","runners":runners or []}] if market else []}


def runner(name,odd=None,volume=None):
    return {"name":name,"odd":odd,"volume":volume}


def test_provider_cohort_counts_genuine_three_sided_market_and_partial():
    complete=[runner("Home",1.6,1000),runner("The Draw",3.1,0),
              runner("Away",4.0,100)]
    partial=[runner("Home",1.6,1000),runner("The Draw",None,None),
             runner("Away",4.0,100)]
    data=summarize_early_provider_coverage([
        fixture(74,complete),fixture(75,partial),fixture(76,market=False),
        fixture(60.5,complete),fixture(39,partial),fixture(111,complete)
    ],now=NOW,map_market=map_market)
    assert data["T72_96"]=={
        "fixtures":3,"market_present":2,"fully_priced":1,
        "partially_priced":1,"no_priced_sides":0,
        "missing_market":1,"runner_field_missing":1}
    assert data["T60_72"]["fully_priced"]==1
    assert data["T24_40"]["partially_priced"]==1
    assert data["T96_PLUS"]["fully_priced"]==1


def test_no_odds_or_volume_is_missing_despite_three_runner_names():
    incomplete=[runner("Home",None,None),runner("The Draw",None,None),
                runner("Away",None,None)]
    row=summarize_early_provider_coverage([fixture(77,incomplete)],now=NOW,
                                          map_market=map_market)["T72_96"]
    assert row["fixtures"]==1
    assert row["no_priced_sides"]==1
    assert row["runner_field_missing"]==3
    assert row["fully_priced"]==0


def test_zero_market_amount_does_not_count_as_ready():
    rows=[runner("Home",1.8,0),runner("The Draw",3.4,0),
          runner("Away",4.2,0)]
    row=summarize_early_provider_coverage([fixture(76,rows)],now=NOW,
                                          map_market=map_market)["T72_96"]
    assert row["fully_priced"]==0
    assert row["partially_priced"]==1


def test_invalid_source_side_and_missing_identity_not_counted_ready():
    rows=[runner("Unrecognized",1.8,500),runner("The Draw",3.4,400),
          runner("Another Unknown",4.2,200)]
    row=summarize_early_provider_coverage([fixture(76,rows)],now=NOW,
                                          map_market=map_market)["T72_96"]
    assert row["fully_priced"]==0


def test_source_summary_is_logging_only_and_never_creates_prices():
    src=(Path(__file__).resolve().parents[1]/"betwatch_prematch.py").read_text()
    assert "summarize_early_provider_coverage(" in src
    assert 'writer.last_scrape_stats["early_provider_coverage"]' in src
    assert '"early_provider_coverage": early_source' in src
    assert "EARLY_SOURCE {cohort}" in src
