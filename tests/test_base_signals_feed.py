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
    def __init__(self, start, events=None, state="COMPLETED", results=None):
        self.results=results or []
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
        if url.endswith("live_fixtures"):
            return Reply(self.results)
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
        "sxf_base_signal_events","sxf_base_checkpoint_jobs","fixtures","live_fixtures"}


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
        if url.endswith(("/fixtures","sxf_base_checkpoint_jobs")):
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

def _result_row(start, *, score="1-1", status="ft", minute="FT",
                home="Ev Sahibi", away="Konuk Takım", league="Süper Lig",
                match_hash="abc123abc123", kickoff=None, fixture_uid=None):
    return {
        "fixture_uid":fixture_uid,"match_id_hash":match_hash,
        "home_team":home,"away_team":away,"league":league,
        "kickoff_utc":kickoff or _stamp(start),
        "score":score,"status":status,"minute":minute,
        "updated_at":_stamp(start),
    }


@pytest.mark.parametrize("selection,expected",[
    ("1","LOSS"),("X","WIN"),("2","LOSS")
])
def test_1x2_real_ft_uses_hash_fallback_when_live_uid_null(selection,expected):
    start=_day()
    result=_feed(Source(start,events=[_event(start,selection=selection)],
        results=[_result_row(start)])).read(start)
    item=result["items"][0]
    assert item["result_state"]=="FT"
    assert item["final_score"]=="1-1"
    assert item["outcome"]==expected
    assert result["results_source_state"]=="ok"


@pytest.mark.parametrize("market,selection,score,expected",[
    ("OU25","O","2-2","WIN"),("OU25","U","2-2","LOSS"),
    ("OU25","O","1-1","LOSS"),("OU25","U","1-1","WIN"),
    ("BTTS","Y","1-1","WIN"),("BTTS","N","1-1","LOSS"),
    ("BTTS","Y","2-0","LOSS"),("BTTS","N","2-0","WIN")
])
def test_settlement_matches_actual_result_only(market,selection,score,expected):
    start=_day()
    event=_event(start,selection=selection)
    event["market"]=market
    item=_feed(Source(start,events=[event],results=[_result_row(start,score=score)])).read(start)["items"][0]
    assert item["outcome"]==expected
    assert item["result_state"]=="FT"


def test_live_score_is_never_claimed_as_final():
    start=_day()
    item=_feed(Source(start,results=[_result_row(start,score="2-1",status="live",minute="90+2'")])).read(start)["items"][0]
    assert item["result_state"]=="PENDING"
    assert item["final_score"] is None and item["outcome"] is None


@pytest.mark.parametrize("override",[
    {"home":"Unrelated team"},
    {"away":"Wrong opposition"},
    {"league":"Other League"},
    {"kickoff": "2026-10-01T15:00:00+00:00"},
    {"fixture_uid":str(uuid4())},
    {"score":"incomplete"},
    {"score":"999-2"},
    {"match_hash":"ffffffffffff"},
])
def test_results_fail_closed_on_nonmatching_or_invalid_identity(override):
    start=_day()
    item=_feed(Source(start,results=[_result_row(start,**override)])).read(start)["items"][0]
    assert item["final_score"] is None
    assert item["outcome"] is None


def test_ambiguous_duplicate_result_rows_never_get_settled():
    start=_day()
    row=_result_row(start)
    item=_feed(Source(start,results=[row,row])).read(start)["items"][0]
    assert item["outcome"] is None and item["result_state"]=="PENDING"


def test_optional_scoreboard_outage_does_not_hide_valid_base_signals():
    start=_day()
    source=Source(start)
    normal=source.get
    def failing(url,*,params,headers,timeout):
        if url.endswith("live_fixtures"):
            raise TimeoutError("scoreboard unavailable")
        return normal(url,params=params,headers=headers,timeout=timeout)
    source.get=failing
    # Wrap generic network failures just like requests.Session does.
    # Use a status failure to exercise the safe optional-source fallback.
    def failed_http(url,*,params,headers,timeout):
        if url.endswith("live_fixtures"):
            response=Reply([])
            response.status_code=503
            return response
        return normal(url,params=params,headers=headers,timeout=timeout)
    source.get=failed_http
    feed=_feed(source).read(start)
    assert len(feed["items"])==1
    assert feed["items"][0]["result_state"]=="UNAVAILABLE"
    assert feed["results_source_state"]=="unavailable"


def test_belated_checkpoint_is_explicitly_retroactive_not_an_on_time_alert():
    start=_day()
    event=_event(start)
    # Simulated persisted event written after kickoff for frozen T-8 evidence.
    event["recorded_at"]=(datetime.fromisoformat(_stamp(start))+
                          timedelta(minutes=30)).isoformat()
    signal=_feed(Source(start,events=[event])).read(start)["items"][0]
    assert signal["delivery_timing"]=="LATE_EVALUATION"
    assert signal["kind"]=="PRELIMINARY_SIGNAL"
    assert signal["shadow"] is True

def test_checkpoint_window_and_corrections_have_distinct_delivery_labels():
    start=_day()
    event=_event(start)
    kickoff=datetime.fromisoformat(_stamp(start))
    event["recorded_at"]=(kickoff-timedelta(hours=8)+
                          timedelta(minutes=5)).isoformat()
    signal=_feed(Source(start,events=[event])).read(start)["items"][0]
    assert signal["delivery_timing"]=="CHECKPOINT_WINDOW"
    corrected=_event(start,kind="CORRECTED")
    corrected["details"]["decision"]="HIT"
    signal=_feed(Source(start,events=[corrected])).read(start)["items"][0]
    assert signal["delivery_timing"]=="RECONCILED_LATER"


def test_price_rejected_signal_kept_in_archive_but_not_counted_as_valid():
    start=_day()
    event=_event(start,ident=201,engine="HEAVY_1X2_CONCENTRATION")
    kickoff=datetime.fromisoformat(_stamp(start))
    event["recorded_at"]=(kickoff-timedelta(hours=8)+timedelta(minutes=5)).isoformat()
    event["details"].update({"odds":"1.18","selection_status":"PRICE_FILTER_REJECT"})
    result=_feed(Source(start,events=[event])).read(start)
    assert len(result["items"])==1
    item=result["items"][0]
    assert item["selection_status"]=="PRICE_FILTER_REJECT"
    assert item["review_state"]=="PRICE_REJECTED"
    assert item["valid_on_time"] is False
    assert item["delivery_timing"]=="CHECKPOINT_WINDOW"


def test_retroactive_signal_remains_audit_record_not_timely_pick():
    start=_day()
    event=_event(start,ident=202,engine="EARLY_MONEY_T12",kind="EARLY_SIGNAL")
    event["job_checkpoint_hours"]=12
    event["source_checkpoint_hours"]=12
    event["recorded_at"]=(datetime.fromisoformat(_stamp(start))+
                          timedelta(minutes=1)).isoformat()
    event["details"]["selection_status"]="ELIGIBLE"
    result=_feed(Source(start,events=[event])).read(start)
    item=result["items"][0]
    assert item["review_state"]=="LATE_HISTORY"
    assert item["valid_on_time"] is False
    assert item["delivery_timing"]=="LATE_EVALUATION"


def test_timely_eligible_signal_is_countable():
    start=_day()
    event=_event(start,ident=203,engine="SURPRISE_TEAM")
    kickoff=datetime.fromisoformat(_stamp(start))
    event["recorded_at"]=(kickoff-timedelta(hours=8)+timedelta(minutes=5)).isoformat()
    event["details"]["selection_status"]="ELIGIBLE"
    result=_feed(Source(start,events=[event])).read(start)
    item=result["items"][0]
    assert item["review_state"]=="VALID_PREMATCH_RECORD"
    assert item["valid_on_time"] is True


def test_unknown_legacy_eligibility_fails_closed_without_dropping_record():
    start=_day()
    event=_event(start,ident=204)
    kickoff=datetime.fromisoformat(_stamp(start))
    event["recorded_at"]=(kickoff-timedelta(hours=8)+timedelta(minutes=5)).isoformat()
    result=_feed(Source(start,events=[event])).read(start)
    item=result["items"][0]
    assert item["review_state"]=="UNVERIFIED_STATUS"
    assert item["valid_on_time"] is False


def test_corrected_reconciliation_is_not_fresh_signal_even_with_eligible_state():
    start=_day()
    event=_event(start,ident=205,kind="CORRECTED")
    event["details"].update({"decision":"HIT","selection_status":"ELIGIBLE"})
    item=_feed(Source(start,events=[event])).read(start)["items"][0]
    assert item["review_state"]=="RECONCILED_HISTORY"
    assert item["valid_on_time"] is False
