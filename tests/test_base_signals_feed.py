"""Read-only Base V3 feed: secure joins, real data, TR-day identity, no phantom signals."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from base_signal_engine.feed import (
    BaseFeedUnavailable, BaseSignalsFeed, TR_TZ, parse_day
)

UID = str(uuid4())
JOB = str(uuid4())


def _day():
    return datetime.now(TR_TZ).date() - timedelta(days=2)


def _stamp(start):
    return datetime.combine(start + timedelta(days=2), datetime.min.time(), TR_TZ).replace(
        hour=20, minute=30).astimezone(timezone.utc).isoformat()


def _event(start, *, ident=12, kind="PRELIMINARY_SIGNAL",
           selection="2", engine="SURPRISE_TEAM"):
    ts=_stamp(start)
    return {"event_id":ident,"job_id":JOB,"fixture_uid":UID,
            "kickoff_utc":ts,"kind":kind,"market":"1X2","selection":selection,
            "engine":engine,"family":"BASE","job_checkpoint_hours":8,
            "source_checkpoint_hours":8,"recorded_at":ts,
            "details":{"odds":"3.65","observed_at":ts,"label":"SIGNAL"}}


class Reply:
    status_code=200
    def __init__(self, data):
        self.data=data
    def json(self):
        return self.data


class Source:
    def __init__(self, start, events=None, state="COMPLETED"):
        self.start=start
        self.events=events if events is not None else [_event(start)]
        self.state=state
        self.calls=[]
    def get(self, url, *, params, headers, timeout):
        self.calls.append((url,params,headers))
        assert "service-token" == headers["apikey"]
        assert headers["Authorization"] == "Bearer service-token"
        assert timeout==12
        if url.endswith("sxf_base_signal_events"):
            return Reply(self.events)
        if url.endswith("sxf_base_checkpoint_jobs"):
            return Reply([{"job_id":JOB,"fixture_uid":UID,
                           "kickoff_utc":_stamp(self.start),"state":self.state}])
        if url.endswith("fixtures"):
            return Reply([{"fixture_uid":UID,"home_team":"Ev Sahibi",
                           "away_team":"Konuk Takım","league":"Süper Lig",
                           "kickoff_utc":_stamp(self.start),
                           "match_id_hash":"abc123abc123"}])
        raise AssertionError("not an allowed signal read")


def _feed(source):
    return BaseSignalsFeed("https://example.supabase.co", "service-token",session=source)


def test_real_signal_preserves_selection_kickoff_and_turkey_day():
    start=_day()
    source=Source(start)
    result=_feed(source).read(start)
    assert result["phase"]=="SHADOW"
    assert result["source_complete"] is False
    assert len(result["items"])==1
    signal=result["items"][0]
    assert signal["home"]=="Ev Sahibi" and signal["away"]=="Konuk Takım"
    assert signal["selection"]=="2" and signal["odds"]==3.65
    assert signal["day"]==(start+timedelta(days=2)).isoformat()
    assert signal["checkpoint"]==8 and signal["kind"]=="PRELIMINARY_SIGNAL"
    assert signal["shadow"] is True
    assert all(call[0].startswith("https://example.supabase.co/rest/v1/") for call in source.calls)
    assert {call[0].rsplit("/",1)[-1] for call in source.calls} == {
        "sxf_base_signal_events","sxf_base_checkpoint_jobs","fixtures"}


@pytest.mark.parametrize("state",["PENDING","WAITING_DATA","RETRY","LEASED"])
def test_uncompleted_jobs_are_not_displayed_as_signals(state):
    start=_day()
    result=_feed(Source(start,state=state)).read(start)
    assert result["items"]==[]


def test_incomplete_or_missing_selection_never_becomes_pick():
    start=_day()
    data=[_event(start,selection=""),_event(start,ident=14,engine=""),_event(start,ident=16,kind="MARKET_DECISION")]
    result=_feed(Source(start,events=data)).read(start)
    assert result["items"]==[]


def test_midnight_local_date_uses_europe_istanbul_not_utc():
    start=_day()
    source=Source(start)
    data=_event(start)
    ts=datetime.combine(start+timedelta(days=2),datetime.min.time(),TR_TZ).replace(
        minute=15).astimezone(timezone.utc).isoformat()
    data["kickoff_utc"]=ts
    source.events=[data]
    # The job and fixture must refer to exactly the same physical kickoff.
    def same_kickoff_get(url, *, params, headers, timeout):
        result=Source.get(source,url,params=params,headers=headers,timeout=timeout)
        if url.endswith(("fixtures","sxf_base_checkpoint_jobs")):
            result.data[0]["kickoff_utc"]=ts
        return result
    source.get=same_kickoff_get
    result=_feed(source).read(start)
    assert result["items"][0]["day"]==(start+timedelta(days=2)).isoformat()


def test_historical_or_foreign_kickoff_cannot_be_relabelled_as_same_fixture():
    start=_day()
    source=Source(start)
    original=source.get
    def swapped(url, *, params, headers, timeout):
        response=original(url,params=params,headers=headers,timeout=timeout)
        if url.endswith("fixtures"):
            response.data[0]["kickoff_utc"]=(datetime.fromisoformat(_stamp(start))+timedelta(hours=1)).isoformat()
        return response
    source.get=swapped
    assert _feed(source).read(start)["items"]==[]


def test_malformed_event_identity_fails_closed():
    start=_day()
    source=Source(start,events=[_event(start),_event(start)])
    with pytest.raises(BaseFeedUnavailable,match="duplicate"):
        _feed(source).read(start)


def test_pagination_cap_refuses_partial_signals():
    from base_signal_engine.feed import PAGE_SIZE,MAX_PAGES
    start=_day()
    source=Source(start,events=[_event(start,ident=i+1) for i in range(PAGE_SIZE)])
    with pytest.raises(BaseFeedUnavailable,match="safety limit"):
        _feed(source).read(start)
    assert len(source.calls)==MAX_PAGES


def test_untrusted_or_unconfigured_source_refused():
    for url,key in (("http://example.co","secret"),("https://example.co","")):
        with pytest.raises(BaseFeedUnavailable):
            BaseSignalsFeed(url,key)


@pytest.mark.parametrize("value",["2026-3-09","2026-02-30","invalid","2026-10-19%00"])
def test_strict_iso_day(value):
    with pytest.raises(ValueError):
        parse_day(value)


def test_completed_authoritative_t6_marks_old_t8_as_history_not_new_signal():
    start=_day()
    old=_event(start,ident=12)
    decision=_event(start,ident=13,kind="MARKET_DECISION",engine=None,selection=None)
    decision["job_checkpoint_hours"]=6
    decision["source_checkpoint_hours"]=6
    decision["details"]={"state":"AUTHORITATIVE_T6"}
    result=_feed(Source(start,events=[old,decision])).read(start)
    assert len(result["items"])==1
    assert result["items"][0]["stage_status"]=="T8_HISTORICAL"


def test_unresolved_t8_keeps_preliminary_label():
    start=_day()
    result=_feed(Source(start)).read(start)
    assert result["items"][0]["stage_status"]=="AS_RECORDED"


def test_reconciled_no_hit_is_not_a_fresh_signal():
    start=_day()
    corrected=_event(start,kind="CORRECTED")
    corrected["details"]={"decision":"NO_HIT"}
    assert _feed(Source(start,events=[corrected])).read(start)["items"]==[]
