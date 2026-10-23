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
            "details":{"odds":"3.65","observed_at":ts,"label":"SIGNAL",
                       "selection_status":"ELIGIBLE"}}


class Reply:
    status_code=200
    def __init__(self, data):
        self.data=data
    def json(self):
        return self.data


class Source:
    def __init__(self, start, events=None, state="COMPLETED", results=None, skip_fixture=False):
        self.results=results or []
        self.start=start
        self.events=events if events is not None else [_event(start)]
        self.state=state
        self.skip_fixture=skip_fixture
        self.calls=[]
    def get(self, url, *, params, headers, timeout):
        self.calls.append((url,params,headers))
        assert "service-token" == headers["apikey"]
        assert headers["Authorization"] == "Bearer service-token"
        assert timeout==12
        if url.endswith("sxf_base_signal_events"):
            return Reply(self.events)
        if url.endswith("sxf_base_checkpoint_jobs"):
            if dict(params).get("state") == "eq.SKIPPED_DATA":
                if not self.skip_fixture:
                    return Reply([])
                return Reply([{"job_id":str(uuid4()),"fixture_uid":UID,
                              "kickoff_utc":_stamp(self.start),
                              "last_error_code":"SOURCE_INCOMPLETE"}])
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



def test_unrelated_early_gap_does_not_hide_a_completed_base_signal():
    start=_day()
    source=Source(start,skip_fixture=True)
    result=_feed(source).read(start)
    assert len(result["items"])==1
    assert result["items"][0]["engine"]=="SURPRISE_TEAM"
    # The immutable event survives; never probe for fixture-wide suppression.
    assert len(source.events)==1 and source.events[0]["event_id"]==12
    assert not any(dict(call[1]).get("state")=="eq.SKIPPED_DATA"
                   for call in source.calls if call[0].endswith("sxf_base_checkpoint_jobs"))


def test_feed_does_not_depend_on_unrelated_family_skip_probe():
    start=_day()
    source=Source(start)
    original=source.get
    def fail_legacy_probe(url,*,params,headers,timeout):
        if url.endswith("sxf_base_checkpoint_jobs") and dict(params).get("state")=="eq.SKIPPED_DATA":
            raise AssertionError("legacy cross-family probe must not run")
        return original(url,params=params,headers=headers,timeout=timeout)
    source.get=fail_legacy_probe
    assert len(_feed(source).read(start)["items"])==1


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
        if result.data and url.endswith(("/fixtures","sxf_base_checkpoint_jobs")):
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


def test_price_rejected_detection_never_enters_signal_feed():
    start=_day()
    event=_event(start,ident=201,engine="HEAVY_1X2_CONCENTRATION")
    kickoff=datetime.fromisoformat(_stamp(start))
    event["recorded_at"]=(kickoff-timedelta(hours=8)+timedelta(minutes=5)).isoformat()
    event["details"].update({"odds":"1.18","selection_status":"PRICE_FILTER_REJECT"})
    result=_feed(Source(start,events=[event])).read(start)
    assert result["items"]==[]
    # Feed filtering must not mutate the immutable stored audit event.
    assert event["details"]["selection_status"]=="PRICE_FILTER_REJECT"


def test_all_rejected_lincoln_twente_checkpoints_do_not_create_signal_cards():
    start=_day()
    events=[]
    for ident,engine,price,hours in [
        (210,"EARLY_MONEY_CORE","1.27",72),
        (211,"EARLY_MONEY_T12","1.24",12),
        (212,"HEAVY_1X2_CONCENTRATION","1.25",8),
        (213,"HEAVY_1X2_CONCENTRATION","1.24",6),
    ]:
        row=_event(start,ident=ident,engine=engine)
        row["job_checkpoint_hours"]=hours
        row["source_checkpoint_hours"]=hours
        row["details"].update({"odds":price,"selection_status":"PRICE_FILTER_REJECT"})
        row["kind"]="EARLY_SIGNAL" if hours>8 else ("PRELIMINARY_SIGNAL" if hours==8 else "FINAL_SIGNAL")
        events.append(row)
    source=Source(start,events=events)
    assert _feed(source).read(start)["items"]==[]
    assert len(source.events)==4


def test_mixed_valid_and_rejected_engines_show_only_actual_eligible_badges():
    start=_day()
    allowed=_event(start,ident=230,engine="1X2_CONCENTRATION_V1")
    blocked=_event(start,ident=231,engine="HEAVY_1X2_CONCENTRATION")
    blocked["details"].update({"odds":"1.24","selection_status":"PRICE_FILTER_REJECT"})
    valid=_feed(Source(start,events=[allowed,blocked])).read(start)["items"]
    assert [x["engine"] for x in valid]==["1X2_CONCENTRATION_V1"]


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


def test_unknown_legacy_eligibility_fails_closed_and_is_not_a_signal():
    start=_day()
    event=_event(start,ident=204)
    event["details"].pop("selection_status")
    kickoff=datetime.fromisoformat(_stamp(start))
    event["recorded_at"]=(kickoff-timedelta(hours=8)+timedelta(minutes=5)).isoformat()
    assert _feed(Source(start,events=[event])).read(start)["items"]==[]
    assert "selection_status" not in event["details"]


def test_incomplete_early_first_history_is_not_an_eligible_signal():
    start=_day()
    event=_event(start,ident=214,engine="EARLY_MONEY_CORE",kind="EARLY_SIGNAL")
    event["details"]["selection_status"]="HISTORY_INCOMPLETE"
    assert _feed(Source(start,events=[event])).read(start)["items"]==[]


def test_corrected_reconciliation_is_not_fresh_signal_even_with_eligible_state():
    start=_day()
    event=_event(start,ident=205,kind="CORRECTED")
    event["details"].update({"decision":"HIT","selection_status":"ELIGIBLE"})
    item=_feed(Source(start,events=[event])).read(start)["items"][0]
    assert item["review_state"]=="RECONCILED_HISTORY"
    assert item["valid_on_time"] is False


def test_feed_rechecks_price_floor_when_persisted_label_conflicts():
    start=_day()
    kickoff=datetime.fromisoformat(_stamp(start))
    event=_event(start,ident=206,engine="HEAVY_1X2_CONCENTRATION")
    event["recorded_at"]=(kickoff-timedelta(hours=8)+timedelta(minutes=5)).isoformat()
    event["details"].update({"selection_status":"ELIGIBLE","odds":"1.21"})
    assert _feed(Source(start,events=[event])).read(start)["items"]==[]


def test_mismatched_rejection_of_valid_price_does_not_become_eligible():
    start=_day()
    kickoff=datetime.fromisoformat(_stamp(start))
    event=_event(start,ident=207)
    event["recorded_at"]=(kickoff-timedelta(hours=8)+timedelta(minutes=5)).isoformat()
    event["details"].update({"selection_status":"PRICE_FILTER_REJECT","odds":"3.65"})
    assert _feed(Source(start,events=[event])).read(start)["items"]==[]


def test_scheduler_source_grace_plus_worker_budget_allows_twelve_minutes():
    start=_day()
    kickoff=datetime.fromisoformat(_stamp(start))
    event=_event(start,ident=208)
    event["recorded_at"]=(kickoff-timedelta(hours=8)+timedelta(minutes=12)).isoformat()
    event["details"]["selection_status"]="ELIGIBLE"
    item=_feed(Source(start,events=[event])).read(start)["items"][0]
    assert item["delivery_timing"]=="CHECKPOINT_WINDOW"
    assert item["valid_on_time"] is True


def test_three_hour_backlog_delay_stays_archived_even_before_kickoff():
    start=_day()
    kickoff=datetime.fromisoformat(_stamp(start))
    event=_event(start,ident=209)
    event["recorded_at"]=(kickoff-timedelta(hours=8)+timedelta(hours=3)).isoformat()
    event["details"]["selection_status"]="ELIGIBLE"
    item=_feed(Source(start,events=[event])).read(start)["items"][0]
    assert item["delivery_timing"]=="LATE_EVALUATION"
    assert item["review_state"]=="LATE_HISTORY"
    assert item["valid_on_time"] is False


def _core_event(start, *, ident=801, selection="2", checkpoint=60):
    event=_event(start, ident=ident, kind="EARLY_SIGNAL",
                 engine="EARLY_MONEY_CORE", selection=selection)
    event["family"]="EARLY_CORE"
    event["job_checkpoint_hours"]=checkpoint
    event["source_checkpoint_hours"]=checkpoint
    return event


def _retention_event(start, ident, h, state, *, side="2", first=60):
    event=_event(start,ident=ident,kind="RETENTION_CHECK",
                 engine=None,selection=None)
    event["family"]="EARLY_RETENTION"
    event["job_checkpoint_hours"]=h
    event["source_checkpoint_hours"]=h
    event["details"]={
        "first_core_checkpoint":first,
        "first_core_side":side,
        "current_checkpoint_state":state,
        # A completed T-6 record legitimately said INSUFFICIENT_DATA
        # because T-5/4/3 had not been executed yet.
        "overall_state":"INSUFFICIENT_DATA",
    }
    return event


def test_retention_uses_each_finished_checkpoint_not_early_overall_flag():
    day=_day()
    kickoff=datetime.fromisoformat(_stamp(day))
    early=_core_event(day)
    progress=[
        _retention_event(day, 802, 6, "RETAINED_AT_CHECKPOINT"),
        _retention_event(day, 803, 5, "RETAINED_AT_CHECKPOINT"),
        _retention_event(day, 804, 4, "RETAINED_AT_CHECKPOINT"),
        _retention_event(day, 805, 3, "RETAINED_AT_CHECKPOINT"),
    ]
    pre=_feed(Source(day,events=[early,*progress[:2]])).read(
        day,as_of_utc=kickoff-timedelta(hours=4,minutes=30))["items"][0]
    assert pre["retention"]["status"]=="PENDING"
    assert pre["retention"]["confirmed"]==[6,5]

    incomplete=_feed(Source(day,events=[early,progress[0],progress[2]])).read(
        day,as_of_utc=kickoff-timedelta(hours=3,minutes=30))["items"][0]
    assert incomplete["retention"]["status"]=="INCOMPLETE"

    fully=_feed(Source(day,events=[early,*progress])).read(
        day,as_of_utc=kickoff-timedelta(hours=2))["items"][0]
    assert fully["retention"]["status"]=="RETAINED"
    assert fully["retention"]["confirmed"]==[6,5,4,3]
    assert len([e for e in Source(day,events=[early,*progress]).events
                if e["kind"]=="RETENTION_CHECK"])==4


def test_retention_break_never_recovers_and_is_side_and_checkpoint_scoped():
    day=_day()
    kickoff=datetime.fromisoformat(_stamp(day))
    early=_core_event(day)
    events=[
        _retention_event(day, 807, 6, "RETENTION_BREAK"),
        _retention_event(day, 808, 5, "RETAINED_AT_CHECKPOINT"),
        _retention_event(day, 809, 4, "RETAINED_AT_CHECKPOINT"),
        _retention_event(day, 810, 3, "RETAINED_AT_CHECKPOINT"),
        _retention_event(day, 811, 3, "RETENTION_BREAK",side="1"),
        _retention_event(day, 812, 3, "RETENTION_BREAK",first=72),
    ]
    early_item=_feed(Source(day,events=[early,*events])).read(
        day,as_of_utc=kickoff-timedelta(hours=2))["items"][0]
    assert early_item["retention"]["status"]=="BROKEN"
    assert len(early_item["retention"]["checked"])==4
    assert early_item["engine"]=="EARLY_MONEY_CORE"


def test_retention_audit_is_never_itself_a_signal():
    day=_day()
    result=_feed(Source(day,events=[
        _retention_event(day, 815, 6, "RETAINED_AT_CHECKPOINT"),
    ])).read(day,as_of_utc=datetime.fromisoformat(_stamp(day)))
    assert result["items"]==[]


def test_retention_no_audit_after_kickoff_fails_closed_incomplete():
    day=_day()
    item=_feed(Source(day,events=[_core_event(day)])).read(
        day,as_of_utc=datetime.fromisoformat(_stamp(day))+timedelta(minutes=5))["items"][0]
    assert item["retention"]["status"]=="INCOMPLETE"


class CurrentQuotesSource(Source):
    def __init__(self, day, snapshots):
        super().__init__(day,events=[])
        self.snapshots=snapshots

    def get(self,url,*,params,headers,timeout):
        if url.endswith("moneyway_snapshots"):
            self.calls.append((url,params,headers))
            assert dict(params)["market"]=="eq.1X2"
            return Reply(self.snapshots)
        return super().get(url,params=params,headers=headers,timeout=timeout)


def _present_rows(uid, when, odds="1.90", share="85", amount="12000"):
    return [
        {"id":1,"fixture_uid":uid,"market":"1X2","selection":"1",
         "odds":"3.20","volume":"1300","share":"10","scraped_at_utc":when},
        {"id":2,"fixture_uid":uid,"market":"1X2","selection":"X",
         "odds":"3.60","volume":"600","share":str(100-float(share)-10),
         "scraped_at_utc":when},
        {"id":3,"fixture_uid":uid,"market":"1X2","selection":"2",
         "odds":odds,"volume":amount,"share":share,"scraped_at_utc":when},
    ]


def test_current_as_of_checks_snapshot_without_mutating_checkpoint_result():
    day=_day()
    now=datetime.fromisoformat(_stamp(day))-timedelta(hours=5)
    rows=_present_rows(UID,(now-timedelta(minutes=2)).isoformat(),
                       odds="2.22",share="76.8",amount="26742.60")
    source=CurrentQuotesSource(day,rows)
    checks=[{"uid":UID,"kickoff_utc":_stamp(day),"selection":"2",
             "engine":engine,"as_of_state":"NOT_RECHECKED",
             "as_of_checked_at":None,"odds":2.14}
            for engine in ("HEAVY_1X2_CONCENTRATION","1X2_CONCENTRATION_V2")]
    _feed(source)._enrich_current_1x2(checks,now=now)
    assert [x["as_of_state"] for x in checks]==["THRESHOLD_FAIL","THRESHOLD_FAIL"]
    assert checks[1]["as_of_scope"]=="V1_BASE_ONLY"
    assert [x["odds"] for x in checks]==[2.14,2.14]

    passing=_present_rows(UID,(now-timedelta(minutes=1)).isoformat(),
                          odds="2.10",share="81.7",amount="12217.01")
    source.snapshots=passing
    _feed(source)._enrich_current_1x2(checks,now=now)
    assert [x["as_of_state"] for x in checks]==["THRESHOLD_PASS","THRESHOLD_PASS"]


def test_current_as_of_never_uses_partial_stale_or_post_kickoff_data():
    day=_day()
    now=datetime.fromisoformat(_stamp(day))-timedelta(hours=4)
    fresh=(now-timedelta(minutes=2)).isoformat()
    item={"uid":UID,"kickoff_utc":_stamp(day),"selection":"2",
          "engine":"HEAVY_1X2_CONCENTRATION",
          "as_of_state":"NOT_RECHECKED","as_of_checked_at":None}
    for quotes in (
        _present_rows(UID,fresh)[:2],
        _present_rows(UID,(now-timedelta(minutes=25)).isoformat()),
        _present_rows(UID,fresh,share="95"),
    ):
        source=CurrentQuotesSource(day,quotes)
        copy=item.copy()
        _feed(source)._enrich_current_1x2([copy],now=now)
        assert copy["as_of_state"]=="NOT_RECHECKED"
    source=CurrentQuotesSource(day,_present_rows(UID,fresh))
    copy=item.copy()
    _feed(source)._enrich_current_1x2([copy],
        now=datetime.fromisoformat(_stamp(day))+timedelta(minutes=1))
    assert copy["as_of_state"]=="AFTER_KICKOFF"
    assert not any(call[0].endswith("moneyway_snapshots") for call in source.calls)


def test_as_of_clock_requires_timezone():
    day=_day()
    with pytest.raises(ValueError,match="timezone-aware"):
        _feed(Source(day)).read(day,as_of_utc=datetime(2026,10,23,12))
