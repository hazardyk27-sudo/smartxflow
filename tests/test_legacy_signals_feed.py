"""Part 3: verified legacy engine picks, no guessed score, date or physical fixture."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest

from base_signal_engine.feed import BaseFeedUnavailable, TR_TZ, BaseSignalsFeed
from base_signal_engine.legacy_feed import (
    LegacySignalsFeed, LEGACY_SOURCES, _literal_list,
    _exact_kickoff
)

TODAY=datetime.now(TR_TZ).date()
START=TODAY-timedelta(days=10)
DAY=TODAY.isoformat()
TIME=datetime.combine(TODAY,datetime.min.time(),TR_TZ).replace(hour=22).astimezone(timezone.utc)
UID=str(uuid4())
UID2=str(uuid4())
STAMP=TIME.isoformat()

def row(table,ident,*,home="Napoli",away="Bodo Glimt",league="UEFA Champions League",
        code="2",key=None,kickoff=None):
    value={"id":ident,"match_key":key if key is not None else home+"|"+away+"|"+STAMP,
           "match_date":DAY,"home_team":home,"away_team":away,
           "league":league,"selection_code":code,"created_at":(TIME-timedelta(days=2)).isoformat(),
           "fixture_uid":None}
    if table=="early_money_lock_signals":value["kickoff_utc"]=kickoff or STAMP
    return value

def fixture(*,uid=UID,home="Napoli",away="Bodo Glimt",league="UEFA Champions League",
            kickoff=STAMP):
    return {"fixture_uid":uid,"home_team":home,"away_team":away,"league":league,
            "kickoff_utc":kickoff,"match_id_hash":"123456abcdef"}

class Fake:
    def __init__(self,rows=None,fixtures=None):
        self.rows=rows or {}
        self.fixtures=fixtures if fixtures is not None else [fixture()]
        self.calls=[]
    def _get(self,table,params):
        self.calls.append((table,params))
        if table=="fixtures":values=self.fixtures
        else:values=self.rows.get(table,[])
        off=int(dict(params).get("offset",0))
        lim=int(dict(params).get("limit",250))
        return values[off:off+lim]

def test_legacy_records_rejoin_real_fixture_and_preserve_two_independent_engines():
    source=Fake({
        "early_money_lock_signals":[row("early_money_lock_signals",21,code="1")],
        "underdog_signals":[row("underdog_signals",100),
                           row("underdog_signals",101,key="Napoli|Bodo Glimt|20.Oct 22:00")]
    })
    payload=LegacySignalsFeed(source).read(START)
    assert len(payload["engines"])==5
    assert len(payload["items"])==2
    assert {x["engine"] for x in payload["items"]}=={
        "LEGACY_EARLY_MONEY_LOCK","LEGACY_UNDERDOG"}
    assert {x["uid"] for x in payload["items"]}=={UID}
    assert payload["duplicate_events_removed"]==1
    assert payload["identity_excluded"]==0
    assert payload["source_rows"]["LEGACY_UNDERDOG"]==2
    assert all(x["result_state"]=="PENDING" and x["final_score"] is None
               and x["odds"] is None and x["shadow"] is False
               and x["stage_status"]=="LEGACY_RECORDED"
               and x["source_checkpoint"] is None for x in payload["items"])
    assert all("match_date" in str(params) for table,params in source.calls if table!="fixtures")
    assert all("kickoff_utc" in str(params) for table,params in source.calls if table=="fixtures")

def test_legacy_does_not_join_wrong_league_or_kickoff_and_counts_missing_identity():
    source=Fake({"underdog_signals":[
        row("underdog_signals",11,league="Other League"),
        row("underdog_signals",12,key="Napoli|Bodo Glimt|2026-10-20T01:01:00+00:00"),
        row("underdog_signals",13),
    ]})
    result=LegacySignalsFeed(source).read(START)
    assert len(result["items"])==1
    assert result["identity_excluded"]==2

def test_ambiguous_same_named_fixtures_cannot_be_counted_as_a_verified_match():
    source=Fake({"underdog_signals":[
        row("underdog_signals",11,key="Napoli|Bodo Glimt|20.Oct 22:00")
    ]},[fixture(),fixture(uid=UID2,kickoff=(TIME+timedelta(minutes=30)).isoformat())])
    outcome=LegacySignalsFeed(source).read(START)
    assert outcome["items"]==[]
    assert outcome["identity_excluded"]==1

def test_explicit_source_uid_never_downgrades_to_team_only_match():
    fake=Fake({"underdog_signals":[dict(row("underdog_signals",11),fixture_uid=UID2)]})
    outcome=LegacySignalsFeed(fake).read(START)
    assert outcome["items"]==[] and outcome["identity_excluded"]==1

def test_source_row_selection_missing_or_bad_identity_is_not_a_signal():
    fake=Fake({"underdog_signals":[
        row("underdog_signals",1,code=""),
        row("underdog_signals",2,code="1X"),
        row("underdog_signals",3,home="<script>alert(1)</script>"),
        row("underdog_signals",4,key="wrong|key|fields"),
    ]})
    assert LegacySignalsFeed(fake).read(START)["items"]==[]

def test_empty_engine_still_has_own_card_and_no_source_query_to_browser():
    result=LegacySignalsFeed(Fake()).read(START)
    assert len(result["engines"])==5 and result["items"]==[]
    assert "LEGACY_FAKE_SHARP" in result["engines"]

def test_pagination_refuses_incomplete_source_not_fake_empty():
    source=Fake({"underdog_signals":[row("underdog_signals",i+1)
                                      for i in range(250*8)]})
    with pytest.raises(BaseFeedUnavailable,match="pagination"):
        LegacySignalsFeed(source).read(START)
    assert len([x for x in source.calls if x[0]=="underdog_signals"])==8

def test_kickoff_parser_never_infers_arbitrary_human_text_as_utc():
    assert _exact_kickoff({"match_key":"Napoli|Bodo Glimt|20.Oct 22:00"}) is None
    assert _exact_kickoff({"match_key":"Napoli|Bodo Glimt|"+STAMP})==TIME

def test_source_url_and_allowlist_remain_private_and_strict():
    source=BaseSignalsFeed("https://example.supabase.co","service-token",session=None)
    with pytest.raises(BaseFeedUnavailable):
        source._get("users",[("select","*")])
    value=_literal_list(['FC "Test", (U21)',"Napoli"])
    assert r'\"' in value and "Napoli" in value

def test_app_route_retains_pro_gate_before_private_base_reads():
    # Retired legacy motors cannot be exposed. Private Base queries remain
    # behind the account/PRO gate; no service-role material reaches browsers.
    from pathlib import Path
    app=(Path(__file__).resolve().parents[1]/"app.py").read_text()
    code=app.split("@app.route('/api/base-signals/feed'",1)[1].split("_analyses_cache =",1)[0]
    constructor = "source = BaseSignalsFeed("
    assert code.index("if session.get('license_plan') == 'test'") < code.index(constructor)
    assert code.index("_legacy_license_session_valid()") < code.index(constructor)
    assert code.index("resolve_account_session()") < code.index(constructor)
    assert "os.environ.get('SUPABASE_SERVICE_ROLE_KEY'" in code
    assert "source.read(first, days=int(days_text), archive=(mode == 'archive'))" in code
    assert "LegacySignalsFeed(" not in code
