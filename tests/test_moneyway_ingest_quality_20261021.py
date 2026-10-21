"""No fabricated market outcome: source missing side remains incomplete."""
from core.moneyway_ingest_quality import summarize_ingest_quality


def row(market, side, share=50, *, uid="u", volume=100, odds=1.8, stamp="2026-10-21T01:20Z"):
    return {"market":market, "selection":side, "share":share, "fixture_uid":uid,
            "volume":volume, "odds":odds, "scraped_at_utc":stamp}


def test_complete_three_markets_from_real_observations():
    rows=[row("1X2","1",20),row("1X2","X",30),row("1X2","2",50),
          row("OU25","O",70),row("OU25","U",30),
          row("BTTS","Y",65),row("BTTS","N",35)]
    data=summarize_ingest_quality(rows)
    for market in ("1X2","OU25","BTTS"):
        assert data[market]["complete"]==1
        assert data[market]["missing_sides"]==0


def test_one_sided_hundred_percent_money_is_not_a_complete_market():
    # Real SQL observed many single-sided groups whose one known share sums
    # to exactly 100%. Never use the share sum as a completeness shortcut.
    rows=[row("1X2","X",100),row("BTTS","Y",100),row("OU25","O",100)]
    result=summarize_ingest_quality(rows)
    assert all(v["groups"]==1 and v["missing_sides"]==1 and v["complete"]==0
               for v in result.values())


def test_missing_numeric_input_is_not_replaced_by_zero_or_price_estimate():
    rows=[row("OU25","O",50,volume=None),row("OU25","U",50)]
    result=summarize_ingest_quality(rows)
    assert result["OU25"]["invalid_fields"]==1
    assert result["OU25"]["complete"]==0
    assert rows[0]["volume"] is None


def test_duplicate_side_and_broken_share_refused():
    rows=[row("1X2","1",30),row("1X2","X",30),row("1X2","X",40),
          row("BTTS","Y",45),row("BTTS","N",45)]
    r=summarize_ingest_quality(rows)
    assert r["1X2"]["duplicate_sides"]==1
    assert r["BTTS"]["bad_share_sum"]==1


def test_same_batch_separates_fixture_identity_and_observation_time():
    a=[row("BTTS","Y",60,uid="u1"),row("BTTS","N",40,uid="u1"),
       row("BTTS","Y",60,uid="u2"),
       row("BTTS","Y",70,uid="u1",stamp="2026-10-21T01:26Z"),
       row("BTTS","N",30,uid="u1",stamp="2026-10-21T01:26Z")]
    r=summarize_ingest_quality(a)
    assert r["BTTS"]["groups"]==3
    assert r["BTTS"]["complete"]==2
    assert r["BTTS"]["missing_sides"]==1
