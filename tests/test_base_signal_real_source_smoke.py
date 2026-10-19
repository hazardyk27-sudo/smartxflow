"""Bounded real-source snapshot smoke, captured read-only on 2026-10-19.

Degerfors vs Kalmar FF kickoff 2026-10-19T17:00Z. Snapshot values below
are exactly those returned from public.moneyway_snapshots in two historical
5-minute T-8/T-6 windows; test execution is completely offline with an
in-memory GET-only PostgREST substitute. This is not a live worker or bet.
"""
from datetime import datetime, timedelta, timezone

from base_signal_engine.reader import SupabaseMoneywayReader
from base_signal_engine.scheduler import CheckpointJob, FixtureRef, evaluate_job
from base_signal_engine.source_quality import CapturingReader, source_coverage

UID="74acc8bd-665e-488c-b1e7-32f95674ccdd"
HASH="e961dfd96a25"
KICKOFF=datetime(2026,10,19,17,tzinfo=timezone.utc)
FIXTURE=FixtureRef(UID,KICKOFF,HASH)

# id, observed HH:MM:SS UTC, market, side, odds, volume, share.
# Recorded values retain provider decimals; no synthetic odds are inserted.
_RAW=(
 (55927515,"08:54:54","BTTS","Y","1.88","44.68","79.30"),
 (55927516,"08:54:54","BTTS","N","2.08","11.65","20.70"),
 (55927517,"08:54:54","1X2","1","3.15","71.62","32.60"),
 (55927518,"08:54:54","1X2","X","3.40","49.34","22.50"),
 (55927519,"08:54:54","1X2","2","2.56","98.80","45.00"),
 (55927520,"08:54:54","OU25","O","2.18","164.00","29.20"),
 (55927521,"08:54:54","OU25","U","1.85","396.75","70.80"),
 (55956642,"10:55:49","BTTS","Y","1.89","47.60","49.10"),
 (55956643,"10:55:49","BTTS","N","2.12","49.29","50.90"),
 (55956644,"10:55:49","1X2","1","3.05","137.09","36.90"),
 (55956645,"10:55:49","1X2","X","3.45","54.67","14.70"),
 (55956646,"10:55:49","1X2","2","2.62","179.45","48.30"),
 (55956647,"10:55:49","OU25","O","2.18","409.72","43.00"),
 (55956648,"10:55:49","OU25","U","1.85","542.96","57.00"),
)


def _data():
    return [
        {"id":ident,"fixture_uid":UID,"match_id_hash":HASH,
         "scraped_at_utc":f"2026-10-19T{clock}+00:00",
         "market":market,"selection":side,"odds":odds,
         "volume":volume,"share":share}
        for ident,clock,market,side,odds,volume,share in _RAW]


class _Reply:
    status_code=200
    def __init__(self,rows): self.rows=rows
    def json(self): return self.rows


class _BoundedReadOnlySession:
    def __init__(self,source_rows): self.source_rows=source_rows;self.calls=[]
    def get(self,url,*,params,headers,timeout):
        assert url.startswith("https://source.example/rest/v1/")
        self.calls.append((url,tuple(params)))
        args=dict(params)
        assert args["fixture_uid"]=="eq."+UID
        if url.endswith("/fixtures"):
            return _Reply([{"fixture_uid":UID,"match_id_hash":HASH,
                            "kickoff_utc":KICKOFF.isoformat()}])
        assert url.endswith("/moneyway_snapshots")
        low=high=None
        for key,value in params:
            if key=="scraped_at_utc" and value.startswith("gte."):
                low=datetime.fromisoformat(value[4:])
            if key=="scraped_at_utc" and value.startswith("lte."):
                high=datetime.fromisoformat(value[4:])
        assert low is not None and high is not None
        rows=[r for r in self.source_rows
              if low<=datetime.fromisoformat(r["scraped_at_utc"])<=high]
        rows.sort(key=lambda x:(x["scraped_at_utc"],x["id"]))
        offset=int(args.get("offset",0))
        limit=int(args["limit"])
        return _Reply(rows[offset:offset+limit])


def _evaluate(rows):
    session=_BoundedReadOnlySession(rows)
    reader=SupabaseMoneywayReader("https://source.example","isolated-test-only",
                                  session=session,page_size=5)
    capture=CapturingReader(reader)
    payload=evaluate_job(CheckpointJob(FIXTURE,6,"BASE"),capture)
    coverage=source_coverage(CheckpointJob(FIXTURE,6,"BASE"),
                             capture.source,payload)
    return payload,coverage,capture.source,session


def test_actual_t6_three_market_snapshot_groups_are_complete_and_authoritative():
    payload,coverage,source,session=_evaluate(_data())
    assert source.fetched_rows==14
    assert source.discarded_groups==0 and len(source.snapshots)==6
    assert {s.market for s in source.snapshots}=={"1X2","OU25","BTTS"}
    assert source.fixture.fixture_uid==UID
    assert coverage["disposition"]=="EVALUATE"
    assert coverage["state"]=="COMPLETE"
    assert coverage["missing_t6_markets"]==[]
    assert not coverage["requires_reconciliation"]
    assert {market:record["state"] for market,record in payload["markets"].items()}=={
        "1X2":"AUTHORITATIVE_T6","OU25":"AUTHORITATIVE_T6",
        "BTTS":"AUTHORITATIVE_T6"}
    assert all(record["checkpoint"]==6 for record in payload["markets"].values())
    assert payload["signals"]==[]
    assert session.calls and all(
        url.endswith("/fixtures") or url.endswith("/moneyway_snapshots")
        for url,_ in session.calls)


def test_one_missing_t6_market_side_is_not_fabricated_from_another_timestamp():
    rows=[r for r in _data() if r["id"]!=55956648]
    payload,coverage,source,_=_evaluate(rows)
    assert source.discarded_groups==1
    assert payload["markets"]["OU25"]["state"]=="FALLBACK_T8"
    assert payload["markets"]["OU25"]["checkpoint"]==8
    assert payload["markets"]["1X2"]["state"]=="AUTHORITATIVE_T6"
    assert payload["markets"]["BTTS"]["state"]=="AUTHORITATIVE_T6"
    assert coverage["missing_t6_markets"]==["OU25"]
    assert coverage["requires_reconciliation"]


def test_t8_history_cannot_be_mistaken_for_missing_t6_current_authority():
    rows=[r for r in _data() if r["scraped_at_utc"].endswith("08:54:54+00:00")]
    payload,coverage,source,_=_evaluate(rows)
    assert source.fetched_rows==7
    assert all(record["state"]=="FALLBACK_T8" for record in payload["markets"].values())
    assert sorted(coverage["missing_t6_markets"])==["1X2","BTTS","OU25"]
    assert coverage["requires_reconciliation"]
