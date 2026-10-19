"""Projection truth: T6 authority, pending fallback, immutable correction and drift."""
import pytest
from base_signal_engine.projection import project_market_events

def e(id,kind,market="1X2",cp=8,source=8,**extra):
    return {"event_id":id,"event_key":f"ev-{id}","kind":kind,
            "market":market,"job_checkpoint_hours":cp,"source_checkpoint_hours":source,
            "engine":"1X2_CONCENTRATION_V1","selection":"1",**extra}

def go(events,authoritative=True):
    return project_market_events({"fixture_authoritative":authoritative,"events":events})

def test_pending_t8_is_never_mislabeled_final():
    out=go([e(1,"PRELIMINARY_SIGNAL")])
    assert out["markets"]["1X2"]["status"]=="PRELIMINARY_T8"
    out=go([e(1,"PRELIMINARY_SIGNAL"),
            e(2,"MARKET_DECISION",cp=6,source=8),
            e(3,"FINAL_SIGNAL",cp=6,source=8)])
    assert out["markets"]["1X2"]["status"]=="PROVISIONAL_T8_RECONCILIATION_PENDING"
    assert len(out["markets"]["1X2"]["signals"])==1

def test_authoritative_t6_replaces_t8_even_without_hit():
    rows=[e(1,"PRELIMINARY_SIGNAL"),
          e(2,"MARKET_DECISION",cp=6,source=6)]
    out=go(rows)
    assert out["markets"]["1X2"]=={"status":"AUTHORITATIVE_T6_NO_HIT","signals":[]}

def test_completed_correction_is_authoritative_but_manual_partial_is_not():
    decision=e(2,"MARKET_DECISION",cp=6,source=8)
    manual=e(3,"CORRECTED",cp=6,source=6,origin_event_key="ev-2",
             decision="HIT",reconciled=False)
    pending=go([decision,manual])
    assert pending["markets"]["1X2"]["status"].startswith("PROVISIONAL")
    settled={**manual,"reconciled":True}
    out=go([decision,settled])
    assert out["markets"]["1X2"]["status"]=="RECONCILED_T6"
    assert out["markets"]["1X2"]["signals"]==[
        {"engine":"1X2_CONCENTRATION_V1","selection":"1"}]

def test_completed_no_hit_reconciliation_suppresses_fallback():
    out=go([e(1,"MARKET_DECISION",cp=6,source=8),
            e(2,"FINAL_SIGNAL",cp=6,source=8),
            e(3,"CORRECTED",cp=6,source=6,
              origin_event_key="ev-1",decision="NO_HIT",
              engine=None,selection=None,reconciled=True)])
    assert out["markets"]["1X2"]=={"status":"RECONCILED_T6_NO_HIT","signals":[]}

def test_kickoff_drift_suppresses_all_current_markets():
    out=go([],False)
    assert not out["fixture_authoritative"]
    assert all(v["status"]=="IDENTITY_NOT_CURRENT" and not v["signals"]
               for v in out["markets"].values())
    with pytest.raises(ValueError):
        go([e(1,"PRELIMINARY_SIGNAL")],False)

def test_duplicate_events_and_multi_decision_fail_closed():
    with pytest.raises(ValueError):
        go([e(1,"PRELIMINARY_SIGNAL"),e(1,"PRELIMINARY_SIGNAL")])
    with pytest.raises(ValueError):
        go([e(1,"MARKET_DECISION",cp=6,source=6),
            e(2,"MARKET_DECISION",cp=6,source=8)])
