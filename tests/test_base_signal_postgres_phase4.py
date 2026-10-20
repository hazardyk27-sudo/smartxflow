"""Isolated disposable PostgreSQL integration for proposed Phase 4 migrations.

Requires SXF_TEST_DATABASE_URL explicitly; CI supplies a throwaway Postgres.
NEVER point this at production, staging, or an existing Supabase project.
"""
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest

if not os.environ.get("SXF_TEST_DATABASE_URL"):
    pytest.skip("Only run against a disposable CI PostgreSQL database", allow_module_level=True)

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

URL = os.environ["SXF_TEST_DATABASE_URL"]
ROOT = Path(__file__).resolve().parents[1]
RULESET = "SXF_BASE_V1_2026_10_18"
UID = str(uuid4())
OTHER_UID = str(uuid4())
KICKOFF = datetime(2026, 10, 17, 18, tzinfo=timezone.utc)
OTHER_KICKOFF = KICKOFF + timedelta(minutes=30)


def connect():
    conn = psycopg2.connect(URL, connect_timeout=5)
    conn.autocommit = True
    return conn


def query(sql, params=(), *, role=None):
    with connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if role:
                cur.execute("SET ROLE " + role)
            cur.execute(sql, params)
            if cur.description:
                return [dict(row) for row in cur.fetchall()]
            return []


def job_data(uid=UID, kickoff=KICKOFF):
    return {
        "job_key": f"{RULESET}:{uid}:{kickoff.isoformat()}:BASE:T-6",
        "ruleset_version": RULESET,
        "fixture_uid": uid, "kickoff_utc": kickoff.isoformat(),
        "checkpoint_hours": 6, "family": "BASE",
    }


def claim(worker):
    return query("SELECT * FROM public.sxf_base_claim_due_jobs(%s,%s,%s)",
                 (worker, 1, 180), role="service_role")


def complete(job, payload):
    return query("SELECT public.sxf_base_complete_job(%s::uuid,%s::uuid,%s::jsonb) AS completed",
                 (str(job["job_id"]), str(job["lease_token"]), json.dumps(payload)),
                 role="service_role")[0]["completed"]


def payload_for(job, *, no_evidence=False, invalid_engine=False):
    signal = {"engine": "UNKNOWN_ENGINE", "side": "1", "checkpoint": 6} if invalid_engine else None
    markets = {m: {"checkpoint": None, "state": "INSUFFICIENT_DATA"}
               for m in ("1X2", "OU25", "BTTS")}
    if not no_evidence:
        markets["1X2"] = {"checkpoint": 6, "state": "AUTHORITATIVE_T6"}
    return {
        "key": job["job_key"], "ruleset": RULESET,
        "fixture_uid": str(job["fixture_uid"]),
        "kickoff_utc": job["kickoff_utc"].isoformat(),
        "checkpoint": job["checkpoint_hours"], "family": job["family"],
        "signals": [signal] if signal else [], "markets": markets,
    }


@pytest.fixture(scope="module", autouse=True)
def initialize_empty_test_database():
    # Fail-closed preflight: only the known disposable database name is accepted.
    parsed = psycopg2.extensions.parse_dsn(URL)
    if parsed.get("dbname") != "sxf_test" or parsed.get("host") not in ("127.0.0.1", "localhost"):
        raise RuntimeError("PostgreSQL integration refused nonlocal/non-disposable DB")
    query("""CREATE ROLE anon NOLOGIN;
             CREATE ROLE authenticated NOLOGIN;
             CREATE ROLE service_role NOLOGIN BYPASSRLS;""")
    query("""CREATE TABLE public.fixtures(
                fixture_uid uuid NOT NULL UNIQUE, kickoff_utc timestamptz NOT NULL,
                match_id_hash varchar);
             CREATE TABLE public.moneyway_snapshots(
                id integer PRIMARY KEY, fixture_uid uuid, match_id_hash varchar,
                market varchar, selection varchar,
                odds numeric, volume numeric, share numeric, scraped_at_utc timestamptz);
             GRANT SELECT ON public.fixtures, public.moneyway_snapshots TO service_role;""")
    migration_paths = (
        "migrations/2026_10_18_sxf_base_durable_queue.sql",
        "migrations/2026_10_19_sxf_base_phase4a_waiting_data_hardening.sql",
        "migrations/2026_10_19_sxf_base_phase4b_reconciliation_rpc.sql",
        "migrations/2026_10_19_sxf_base_phase4c_reconcile_queue.sql",
        "migrations/2026_10_19_sxf_base_phase4c_discovery_cursor.sql",
        "migrations/2026_10_19_sxf_base_phase4c4_kickoff_drift.sql",
        "migrations/2026_10_19_sxf_base_phase4c4_discovery_heartbeat.sql",
        "migrations/2026_10_19_sxf_base_phase4c4_health.sql",
        "migrations/2026_10_19_sxf_base_phase4c4_projection.sql",
        "migrations/2026_10_19_sxf_base_checkpoint_live_priority.sql",
        "migrations/2026_10_20_sxf_base_claim_lanes_PROPOSED.sql",
        "migrations/2026_10_20_sxf_base_pre_kickoff_priority_lane_fix_PROPOSED.sql",
        "migrations/2026_10_19_sxf_base_phase5a_source_capture_PROPOSED.sql",
        "migrations/2026_10_19_sxf_base_phase5b_source_health.sql",
    )
    for name in migration_paths:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute((ROOT/name).read_text())
    query("INSERT INTO public.fixtures(fixture_uid,kickoff_utc,match_id_hash) "
          "VALUES(%s::uuid,%s,%s),(%s::uuid,%s,%s)",
          (UID,KICKOFF,"same-legacy-hash",OTHER_UID,OTHER_KICKOFF,"same-legacy-hash"))
    t6 = KICKOFF - timedelta(hours=6, minutes=5)
    t6_other = OTHER_KICKOFF - timedelta(hours=6, minutes=5)
    records = [
        (1,UID,"1X2","1",1.75,1500,80,t6),
        (2,UID,"1X2","X",3.3,100,10,t6),
        (3,UID,"1X2","2",4.2,100,10,t6),
        (4,OTHER_UID,"1X2","1",1.75,1500,80,t6_other),
        (5,OTHER_UID,"1X2","X",3.3,100,10,t6_other),
        (6,OTHER_UID,"1X2","2",4.2,100,10,t6_other),
    ]
    for ident,uid,market,side,odds,amount,share,observed in records:
        query("""INSERT INTO public.moneyway_snapshots
                (id,fixture_uid,market,selection,odds,volume,share,scraped_at_utc)
                VALUES(%s,%s::uuid,%s,%s,%s,%s,%s,%s)""",
              (ident,uid,market,side,odds,amount,share,observed))


def test_01_idempotent_enqueue_and_concurrent_worker_claim():
    job=job_data()
    p=json.dumps([job])
    assert query("SELECT public.sxf_base_enqueue_jobs(%s::jsonb) AS added",(p,),
                 role="service_role")[0]["added"]==1
    assert query("SELECT public.sxf_base_enqueue_jobs(%s::jsonb) AS added",(p,),
                 role="service_role")[0]["added"]==0
    barrier=Barrier(2)
    def concurrent(worker):
        barrier.wait(timeout=10)
        return claim(worker)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(concurrent,"worker-A")
        b=pool.submit(concurrent,"worker-B")
        winners=a.result(timeout=20)+b.result(timeout=20)
    assert len(winners)==1, "FOR UPDATE SKIP LOCKED claimed same job twice"
    test_01_idempotent_enqueue_and_concurrent_worker_claim.claim=winners[0]


def test_02_missing_data_wait_and_stale_lease():
    job=test_01_idempotent_enqueue_and_concurrent_worker_claim.claim
    wait=query("SELECT public.sxf_base_wait_for_data(%s::uuid,%s::uuid,%s,%s) AS ok",
               (str(job["job_id"]),str(job["lease_token"]),"SOURCE_INCOMPLETE",60),
               role="service_role")
    assert wait[0]["ok"] is True
    assert query("SELECT count(*) AS n FROM public.sxf_base_checkpoint_attempts "
                 "WHERE outcome='WAITING_DATA'")[0]["n"]==1
    assert query("SELECT public.sxf_base_wait_for_data(%s::uuid,%s::uuid,%s,%s) AS ok",
                 (str(job["job_id"]),str(job["lease_token"]),"SOURCE_INCOMPLETE",60),
                 role="service_role")[0]["ok"] is False
    query("UPDATE public.sxf_base_checkpoint_jobs "
          "SET next_attempt_at=now()-interval '1 minute' WHERE job_id=%s::uuid",
          (str(job["job_id"]),))
    next_claim=claim("worker-C")
    assert len(next_claim)==1
    assert str(next_claim[0]["lease_token"])!=str(job["lease_token"])
    with pytest.raises(psycopg2.Error):
        complete(job,payload_for(job))
    test_02_missing_data_wait_and_stale_lease.claim=next_claim[0]


def test_03_no_evidence_fails_and_atomic_completion_then_idempotent_replay():
    job=test_02_missing_data_wait_and_stale_lease.claim
    with pytest.raises(psycopg2.Error):
        complete(job,payload_for(job,no_evidence=True))
    assert query("SELECT count(*) AS n FROM public.sxf_base_checkpoint_evaluations")[0]["n"]==0
    assert query("SELECT count(*) AS n FROM public.sxf_base_signal_events")[0]["n"]==0
    assert complete(job,payload_for(job)) is True
    assert query("SELECT count(*) AS n FROM public.sxf_base_checkpoint_evaluations")[0]["n"]==1
    assert query("SELECT count(*) AS n FROM public.sxf_base_signal_events")[0]["n"]==3
    assert query("SELECT count(*) AS n FROM public.sxf_base_checkpoint_attempts "
                 "WHERE outcome='COMPLETED'")[0]["n"]==1
    with pytest.raises(psycopg2.Error):
        complete(job,payload_for(job))
    assert query("SELECT count(*) AS n FROM public.sxf_base_signal_events")[0]["n"]==3
    assert claim("worker-D")==[]


def test_04_append_only_correction_with_full_t6_source_and_replay():
    orig=query("""SELECT event_key FROM public.sxf_base_signal_events
                  WHERE kind='MARKET_DECISION' AND market='1X2' LIMIT 1""")[0]["event_key"]
    sql="""SELECT public.sxf_base_append_reconciliation(
             %s,%s,%s::bigint[],%s::jsonb,%s,%s) AS inserted"""
    args=(orig,"CORRECTED",[3,1,2],json.dumps({"reason":"LATE_T6"}),
          "1X2_CONCENTRATION_V1","1")
    assert query(sql,args,role="service_role")[0]["inserted"] is True
    # Snapshot ID ordering must not duplicate the same event.
    args_sorted=(orig,"CORRECTED",[1,2,3],json.dumps({"reason":"LATE_T6"}),
                 "1X2_CONCENTRATION_V1","1")
    assert query(sql,args_sorted,role="service_role")[0]["inserted"] is False
    count=query("SELECT count(*) AS n FROM public.sxf_base_signal_events "
                "WHERE kind='CORRECTED'")[0]["n"]
    assert count==1
    with pytest.raises(psycopg2.Error):
        query(sql,(orig,"CORRECTED",[4,5,6],json.dumps({"reason":"CROSS_FIXTURE"}),
                   "1X2_CONCENTRATION_V1","1"),role="service_role")
    with pytest.raises(psycopg2.Error):
        query(sql,(orig,"INVALIDATED",[1,2,3],json.dumps({"reason":"NOT_PRELIMINARY"}),
                   None,None),role="service_role")
    with pytest.raises(psycopg2.Error):
        query("UPDATE public.sxf_base_signal_events SET details='{}'::jsonb "
              "WHERE kind='CORRECTED'")


def test_05_transport_rollback_and_expired_lease_reclaim():
    second=job_data(OTHER_UID, OTHER_KICKOFF)
    query("SELECT public.sxf_base_enqueue_jobs(%s::jsonb)",
          (json.dumps([second]),),role="service_role")
    job=claim("worker-E")[0]
    with pytest.raises(psycopg2.Error):
        complete(job,payload_for(job,invalid_engine=True))
    assert query("SELECT count(*) AS n FROM public.sxf_base_checkpoint_evaluations")[0]["n"]==1
    assert query("SELECT count(*) AS n FROM public.sxf_base_signal_events")[0]["n"]==4
    query("UPDATE public.sxf_base_checkpoint_jobs "
          "SET lease_expires_at=now()-interval '1 second' WHERE job_id=%s::uuid",
          (str(job["job_id"]),))
    rerun=claim("worker-F")[0]
    assert rerun["attempt_count"]==2
    assert str(rerun["lease_token"])!=str(job["lease_token"])
    assert query("SELECT count(*) AS n FROM public.sxf_base_checkpoint_attempts "
                 "WHERE outcome='LEASE_EXPIRED'")[0]["n"]==1
    with pytest.raises(psycopg2.Error):
        complete(job,payload_for(job))


def test_06_permissions_no_public_access_or_execution():
    with pytest.raises(psycopg2.Error):
        query("SELECT count(*) FROM public.sxf_base_signal_events",role="anon")
    with pytest.raises(psycopg2.Error):
        query("SELECT public.sxf_base_append_reconciliation("
              "%s,%s,%s::bigint[],%s::jsonb,%s,%s)",
              ("untrusted","CORRECTED",[1,2,3],"{}",None,None),role="authenticated")


def test_07_reconcile_enqueue_is_atomic_with_original_market_decisions():
    global THIRD_UID, THIRD_KICKOFF
    THIRD_UID=str(uuid4())
    THIRD_KICKOFF=KICKOFF+timedelta(hours=1)
    query("INSERT INTO public.fixtures(fixture_uid,kickoff_utc,match_id_hash) "
          "VALUES(%s::uuid,%s,%s)",(THIRD_UID,THIRD_KICKOFF,"same-legacy-hash"))
    job=job_data(THIRD_UID,THIRD_KICKOFF)
    assert query("SELECT public.sxf_base_enqueue_jobs(%s::jsonb) AS n",
                 (json.dumps([job]),),role="service_role")[0]["n"]==1
    claimed=claim("worker-orig")[0]
    assert str(claimed["fixture_uid"])==THIRD_UID
    payload=payload_for(claimed)
    payload["markets"]["1X2"]={"checkpoint":8,"state":"FALLBACK_T8"}
    assert complete(claimed,payload) is True
    rows=query("SELECT market,origin_event_key FROM public.sxf_base_reconcile_jobs "
               "WHERE fixture_uid=%s::uuid ORDER BY market",(THIRD_UID,))
    assert {x["market"] for x in rows}=={"1X2","OU25","BTTS"}
    # Only one test claim eligible, even though other fixtures need reconcile.
    query("UPDATE public.sxf_base_reconcile_jobs SET next_attempt_at=now()+interval '365 days' "
          "WHERE NOT (fixture_uid=%s::uuid AND market='1X2')",(THIRD_UID,))


def test_08_concurrent_reconcile_claim_waits_for_late_source():
    barrier=Barrier(2)
    def concurrently(worker):
        barrier.wait(timeout=10)
        return query("SELECT * FROM public.sxf_base_claim_reconcile(%s,%s,%s)",
                     (worker,1,180),role="service_role")
    with ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(concurrently,"rec-A")
        b=pool.submit(concurrently,"rec-B")
        rows=a.result(timeout=20)+b.result(timeout=20)
    assert len(rows)==1 and rows[0]["market"]=="1X2"
    claim_row=rows[0]
    assert str(claim_row["fixture_uid"])==THIRD_UID
    answer=query("SELECT public.sxf_base_retry_reconcile(%s,%s::uuid,%s,%s) AS ok",
                 (claim_row["reconciliation_id"],str(claim_row["lease_token"]),
                  "SOURCE_INCOMPLETE",60),role="service_role")
    assert answer[0]["ok"] is True
    assert query("SELECT state FROM public.sxf_base_reconcile_jobs "
                 "WHERE reconciliation_id=%s",(claim_row["reconciliation_id"],))[0]["state"]=="WAITING_DATA"
    assert query("SELECT public.sxf_base_retry_reconcile(%s,%s::uuid,%s,%s) AS ok",
                 (claim_row["reconciliation_id"],str(claim_row["lease_token"]),
                  "SOURCE_INCOMPLETE",60),role="service_role")[0]["ok"] is False
    query("UPDATE public.sxf_base_reconcile_jobs SET next_attempt_at=now()-interval '1 minute' "
          "WHERE reconciliation_id=%s",(claim_row["reconciliation_id"],))
    reclaims=query("SELECT * FROM public.sxf_base_claim_reconcile(%s,%s,%s)",
                   ("rec-C",1,180),role="service_role")
    assert len(reclaims)==1
    assert str(reclaims[0]["lease_token"])!=str(claim_row["lease_token"])
    test_08_concurrent_reconcile_claim_waits_for_late_source.claim=reclaims[0]


def test_09_reconcile_batch_is_atomic_idempotent_and_provenanced():
    job=test_08_concurrent_reconcile_claim_waits_for_late_source.claim
    t6=THIRD_KICKOFF-timedelta(hours=6,minutes=5)
    for i,side,odd,amount,share in (
        (10,"1",1.75,1500,80),(11,"X",3.3,100,10),(12,"2",4.2,100,10)):
        query("""INSERT INTO public.moneyway_snapshots
                 (id,fixture_uid,market,selection,odds,volume,share,scraped_at_utc)
                 VALUES(%s,%s::uuid,%s,%s,%s,%s,%s,%s)""",
              (i,THIRD_UID,"1X2",side,odd,amount,share,t6))
    valid={"engine":"1X2_CONCENTRATION_V1","side":"1","checkpoint":6,
           "odds":"1.75","amount":"1500","share":"80","observed_at":t6.isoformat(),
           "label":"SIGNAL","selection_status":"ELIGIBLE"}
    invalid={**valid,"engine":"SURPRISE_TEAM","amount":"BAD"}
    rpc="""SELECT public.sxf_base_complete_reconcile(
              %s,%s::uuid,%s::bigint[],%s::jsonb,%s::jsonb) AS done"""
    orig_count=query("SELECT count(*) AS n FROM public.sxf_base_signal_events "
                     "WHERE kind='CORRECTED'")[0]["n"]
    with pytest.raises(psycopg2.Error):
        query(rpc,(job["reconciliation_id"],str(job["lease_token"]),[10,11,12],
                   json.dumps([valid,invalid]),json.dumps({"reason":"LATE_T6"})),
              role="service_role")
    assert query("SELECT count(*) AS n FROM public.sxf_base_signal_events "
                 "WHERE kind='CORRECTED'")[0]["n"]==orig_count
    state=query("SELECT state FROM public.sxf_base_reconcile_jobs WHERE reconciliation_id=%s",
                (job["reconciliation_id"],))[0]["state"]
    assert state=="LEASED"
    assert query(rpc,(job["reconciliation_id"],str(job["lease_token"]),[12,10,11],
                     json.dumps([valid]),json.dumps({"reason":"LATE_T6"})),
                 role="service_role")[0]["done"] is True
    assert query("SELECT count(*) AS n FROM public.sxf_base_signal_events "
                 "WHERE kind='CORRECTED'")[0]["n"]==orig_count+1
    assert query("SELECT state FROM public.sxf_base_reconcile_jobs WHERE reconciliation_id=%s",
                 (job["reconciliation_id"],))[0]["state"]=="COMPLETED"
    with pytest.raises(psycopg2.Error):
        query(rpc,(job["reconciliation_id"],str(job["lease_token"]),[10,11,12],
                   json.dumps([valid]),"{}"),role="service_role")
    with pytest.raises(psycopg2.Error):
        query("SELECT public.sxf_base_claim_reconcile(%s,%s,%s)",("anon-recon",1,180),
              role="anon")


def test_10_operator_initialized_discovery_cursor_is_immutable():
    start=KICKOFF-timedelta(days=7)
    sql="SELECT public.sxf_base_init_discovery(%s) AS result"
    assert query(sql,(start,),role="service_role")[0]["result"] is True
    assert query(sql,(start,),role="service_role")[0]["result"] is False
    with pytest.raises(psycopg2.Error):
        query(sql,(start-timedelta(days=1),),role="service_role")
    row=query("SELECT completed_through,bootstrap_start FROM public.sxf_base_discovery_cursors "
              "WHERE cursor_name='BASE_FIXTURES'")[0]
    assert row["completed_through"]==row["bootstrap_start"]==start


def test_11_two_discovery_workers_claim_one_lease_and_fence_old_owner():
    barrier=Barrier(2)
    def claim_cursor(worker):
        barrier.wait(timeout=10)
        return query("SELECT * FROM public.sxf_base_claim_discovery(%s,%s)",
                     (worker,180),role="service_role")
    with ThreadPoolExecutor(max_workers=2) as pool:
        one=pool.submit(claim_cursor,"disc-A")
        two=pool.submit(claim_cursor,"disc-B")
        winners=one.result(timeout=20)+two.result(timeout=20)
    assert len(winners)==1
    first=winners[0]
    start=first["completed_through"]
    stop=start+timedelta(hours=24)
    with pytest.raises(psycopg2.Error):
        query("SELECT public.sxf_base_advance_discovery(%s::uuid,%s,%s,%s)",
              (str(first["lease_token"]),start,stop+timedelta(days=1),1),
              role="service_role")
    assert query("SELECT completed_through FROM public.sxf_base_discovery_cursors")[0]["completed_through"]==start
    query("UPDATE public.sxf_base_discovery_cursors SET lease_expires_at=now()-interval '1 second'")
    newer=query("SELECT * FROM public.sxf_base_claim_discovery(%s,%s)",
                ("disc-C",180),role="service_role")
    assert len(newer)==1
    assert newer[0]["lease_token"]!=first["lease_token"]
    assert query("SELECT public.sxf_base_advance_discovery(%s::uuid,%s,%s,%s) AS ok",
                 (str(first["lease_token"]),start,stop,2),
                 role="service_role")[0]["ok"] is False
    test_11_two_discovery_workers_claim_one_lease_and_fence_old_owner.newer=newer[0]


def test_12_advance_only_contiguous_window_and_client_denied():
    owner=test_11_two_discovery_workers_claim_one_lease_and_fence_old_owner.newer
    start=owner["completed_through"]
    stop=start+timedelta(hours=24)
    assert query("SELECT public.sxf_base_advance_discovery(%s::uuid,%s,%s,%s) AS ok",
                 (str(owner["lease_token"]),start,stop,12),
                 role="service_role")[0]["ok"] is True
    assert query("SELECT completed_through,last_window_fixtures "
                 "FROM public.sxf_base_discovery_cursors")[0]=={
                     "completed_through":stop,"last_window_fixtures":12}
    assert query("SELECT public.sxf_base_advance_discovery(%s::uuid,%s,%s,%s) AS ok",
                 (str(owner["lease_token"]),start,stop,12),
                 role="service_role")[0]["ok"] is False
    with pytest.raises(psycopg2.Error):
        query("SELECT * FROM public.sxf_base_discovery_cursors",role="anon")
    with pytest.raises(psycopg2.Error):
        query("SELECT public.sxf_base_claim_discovery(%s,%s)",
              ("public",180),role="authenticated")


def test_13_kickoff_reschedule_is_immutable_and_quarantined():
    moved=THIRD_KICKOFF+timedelta(hours=2)
    old_events=query("SELECT count(*) AS n FROM public.sxf_base_signal_events "
                     "WHERE fixture_uid=%s::uuid",(THIRD_UID,))[0]["n"]
    assert old_events>=4
    query("UPDATE public.fixtures SET kickoff_utc=%s WHERE fixture_uid=%s::uuid",
          (moved,THIRD_UID))
    quarantined=query("SELECT public.sxf_base_quarantine_fixture_drift(%s) AS total",
                      (1000,),role="service_role")[0]["total"]
    assert quarantined>=1
    assert query("SELECT public.sxf_base_quarantine_fixture_drift(%s) AS total",
                 (1000,),role="service_role")[0]["total"]==0
    assert query("SELECT count(*) AS n FROM public.sxf_base_signal_events "
                 "WHERE fixture_uid=%s::uuid",(THIRD_UID,))[0]["n"]==old_events
    assert query("SELECT state FROM public.sxf_base_checkpoint_jobs WHERE "
                 "fixture_uid=%s::uuid AND kickoff_utc=%s",
                 (THIRD_UID,THIRD_KICKOFF))[0]["state"]=="SUPERSEDED"
    assert query("SELECT count(*) AS n FROM public.sxf_base_fixture_drift_events "
                 "WHERE fixture_uid=%s::uuid",(THIRD_UID,))[0]["n"]==1
    with pytest.raises(psycopg2.Error):
        query("DELETE FROM public.sxf_base_fixture_drift_events "
              "WHERE fixture_uid=%s::uuid",(THIRD_UID,))
    with pytest.raises(psycopg2.Error):
        query("SELECT * FROM public.sxf_base_fixture_drift_events",role="anon")


def test_14_kickoff_changing_while_leased_cannot_append_stale_signal():
    uid=str(uuid4())
    original=KICKOFF+timedelta(hours=2)
    current=original+timedelta(hours=1)
    query("INSERT INTO public.fixtures(fixture_uid,kickoff_utc) VALUES(%s::uuid,%s)",
          (uid,original))
    assert query("SELECT public.sxf_base_enqueue_jobs(%s::jsonb) AS total",
                 (json.dumps([job_data(uid,original)]),),
                 role="service_role")[0]["total"]==1
    lease=claim("old-kickoff-worker")[0]
    assert str(lease["fixture_uid"])==uid
    query("UPDATE public.fixtures SET kickoff_utc=%s WHERE fixture_uid=%s::uuid",
          (current,uid))
    with pytest.raises(psycopg2.Error):
        complete(lease,payload_for(lease))
    assert query("SELECT count(*) AS n FROM public.sxf_base_checkpoint_evaluations "
                 "WHERE job_id=%s::uuid",(str(lease["job_id"]),))[0]["n"]==0
    assert query("SELECT count(*) AS n FROM public.sxf_base_signal_events "
                 "WHERE job_id=%s::uuid",(str(lease["job_id"]),))[0]["n"]==0
    assert query("SELECT public.sxf_base_quarantine_fixture_drift(%s) AS total",
                 (1000,),role="service_role")[0]["total"]>=1
    assert query("SELECT state FROM public.sxf_base_checkpoint_jobs "
                 "WHERE job_id=%s::uuid",(str(lease["job_id"]),))[0]["state"]=="SUPERSEDED"
    # Same physical UID with updated kickoff gets a distinct queue identity.
    assert query("SELECT public.sxf_base_enqueue_jobs(%s::jsonb) AS total",
                 (json.dumps([job_data(uid,current)]),),
                 role="service_role")[0]["total"]==1


def test_15_discovery_heartbeat_fences_stale_or_foreign_tokens():
    lease=query("SELECT * FROM public.sxf_base_claim_discovery(%s,%s)",
                ("renew-worker",120),role="service_role")
    assert len(lease)==1
    token=str(lease[0]["lease_token"])
    sql="SELECT public.sxf_base_renew_discovery(%s::uuid,%s) AS renewed"
    assert query(sql,(token,120),role="service_role")[0]["renewed"] is True
    assert query(sql,(str(uuid4()),120),role="service_role")[0]["renewed"] is False
    with pytest.raises(psycopg2.Error):
        query(sql,(token,30),role="service_role")
    with pytest.raises(psycopg2.Error):
        query(sql,(token,120),role="anon")
    query("UPDATE public.sxf_base_discovery_cursors "
          "SET lease_expires_at=now()-interval '1 second' "
          "WHERE lease_token=%s::uuid",(token,))
    assert query(sql,(token,120),role="service_role")[0]["renewed"] is False


def test_16_health_rpc_is_server_only_and_never_fabricates_ingest_latency():
    rows=query("SELECT public.sxf_base_health_snapshot() AS report",
               role="service_role")
    report=rows[0]["report"]
    assert report["checkpoint_queue"]["total"]>=1
    assert report["checkpoint_queue"]["superseded"]>=1
    assert report["reconciliation_queue"]["total"]>=1
    assert report["discovery_cursor"]["initialized"] is True
    assert report["fixture_identity"]["drift_events"]>=1
    assert report["snapshot_ingestion_watermark"] is None
    with pytest.raises(psycopg2.Error):
        query("SELECT public.sxf_base_health_snapshot()",role="anon")


def test_17_current_projection_rpc_excludes_superseded_and_is_server_only():
    from base_signal_engine.projection import project_market_events
    sql="SELECT public.sxf_base_read_market_events(%s::uuid,%s) AS result"
    current=query(sql,(UID,KICKOFF),role="service_role")[0]["result"]
    assert current["fixture_authoritative"] is True
    assert len(current["events"])>=3
    assert project_market_events(current)["markets"]["1X2"]["status"]=="AUTHORITATIVE_T6_NO_HIT"
    stale=query(sql,(THIRD_UID,THIRD_KICKOFF),role="service_role")[0]["result"]
    assert stale=={"fixture_authoritative":False,"events":[]}
    projected=project_market_events(stale)
    assert projected["markets"]["1X2"]["status"]=="IDENTITY_NOT_CURRENT"
    with pytest.raises(psycopg2.Error):
        query(sql,(UID,KICKOFF),role="anon")


def test_18_source_change_capture_covers_insert_update_delete_and_snapshot_mutation():
    global FEED_UID
    FEED_UID=str(uuid4())
    before=KICKOFF+timedelta(days=1)
    after=before+timedelta(hours=3)
    query("INSERT INTO public.fixtures(fixture_uid,kickoff_utc,match_id_hash) "
          "VALUES(%s::uuid,%s,%s)",(FEED_UID,before,"legacy"))
    query("UPDATE public.fixtures SET kickoff_utc=%s WHERE fixture_uid=%s::uuid",
          (after,FEED_UID))
    query("INSERT INTO public.moneyway_snapshots "
          "(id,fixture_uid,market,selection,odds,volume,share,scraped_at_utc) "
          "VALUES(%s,%s::uuid,%s,%s,%s,%s,%s,%s)",
          (101,FEED_UID,"1X2","1",1.75,1000,70,after-timedelta(hours=6)))
    query("UPDATE public.moneyway_snapshots SET volume=1100 WHERE id=101")
    query("DELETE FROM public.moneyway_snapshots WHERE id=101")
    query("DELETE FROM public.fixtures WHERE fixture_uid=%s::uuid",(FEED_UID,))
    events=query("SELECT event_kind,captured_at,fixture_uid,previous_fixture_uid "
                 "FROM public.sxf_base_source_changes WHERE fixture_uid=%s::uuid "
                 "ORDER BY change_id",(FEED_UID,))
    assert [e["event_kind"] for e in events]==[
        "FIXTURE_INSERT","FIXTURE_CHANGE","SNAPSHOT_INSERT",
        "SNAPSHOT_CHANGE","SNAPSHOT_DELETE","FIXTURE_DELETE"]
    assert all(e["captured_at"] is not None for e in events)
    assert query("SELECT public.sxf_base_source_fixture_state(%s::uuid) AS kickoff",
                 (FEED_UID,),role="service_role")[0]["kickoff"] is None
    assert query("SELECT count(*) AS n FROM public.sxf_base_source_deliveries d "
                 "JOIN public.sxf_base_source_changes c ON c.change_id=d.change_id "
                 "WHERE c.fixture_uid=%s::uuid",(FEED_UID,))[0]["n"]==6
    with pytest.raises(psycopg2.Error):
        query("UPDATE public.sxf_base_source_changes SET event_kind='FIXTURE_INSERT' "
              "WHERE fixture_uid=%s::uuid",(FEED_UID,))
    with pytest.raises(psycopg2.Error):
        query("SELECT * FROM public.sxf_base_source_changes",role="anon")


def test_19_source_outbox_multiworker_claim_and_token_fencing():
    latest=query("SELECT max(change_id) AS id FROM public.sxf_base_source_changes "
                 "WHERE fixture_uid=%s::uuid",(FEED_UID,))[0]["id"]
    query("UPDATE public.sxf_base_source_deliveries SET state='DONE' "
          "WHERE change_id<>%s",(latest,))
    barrier=Barrier(2)
    def take(worker):
        barrier.wait(timeout=10)
        return query("SELECT * FROM public.sxf_base_claim_source_changes(%s,%s,%s)",
                     (worker,1,180),role="service_role")
    with ThreadPoolExecutor(max_workers=2) as pool:
        one=pool.submit(take,"source-A")
        two=pool.submit(take,"source-B")
        rows=one.result(timeout=20)+two.result(timeout=20)
    assert len(rows)==1 and rows[0]["change_id"]==latest
    job=rows[0]
    assert query("SELECT public.sxf_base_ack_source_change(%s,%s::uuid) AS ok",
                 (latest,str(uuid4())),role="service_role")[0]["ok"] is False
    assert query("SELECT public.sxf_base_ack_source_change(%s,%s::uuid) AS ok",
                 (latest,str(job["lease_token"])),role="service_role")[0]["ok"] is True
    assert query("SELECT public.sxf_base_ack_source_change(%s,%s::uuid) AS ok",
                 (latest,str(job["lease_token"])),role="service_role")[0]["ok"] is False
    assert query("SELECT state FROM public.sxf_base_source_deliveries WHERE change_id=%s",
                 (latest,))[0]["state"]=="DONE"


def test_20_deleted_fixture_jobs_quarantined_without_source_row():
    uid=str(uuid4())
    kickoff=KICKOFF+timedelta(days=2)
    query("INSERT INTO public.fixtures(fixture_uid,kickoff_utc) VALUES(%s::uuid,%s)",
          (uid,kickoff))
    assert query("SELECT public.sxf_base_enqueue_jobs(%s::jsonb) AS n",
                 (json.dumps([job_data(uid,kickoff)]),),
                 role="service_role")[0]["n"]==1
    query("DELETE FROM public.fixtures WHERE fixture_uid=%s::uuid",(uid,))
    assert query("SELECT public.sxf_base_quarantine_obsolete_uid(%s::uuid,%s) AS n",
                 (uid,250),role="service_role")[0]["n"]==1
    assert query("SELECT public.sxf_base_quarantine_obsolete_uid(%s::uuid,%s) AS n",
                 (uid,250),role="service_role")[0]["n"]==0
    assert query("SELECT state FROM public.sxf_base_checkpoint_jobs "
                 "WHERE fixture_uid=%s::uuid",(uid,))[0]["state"]=="SUPERSEDED"
    with pytest.raises(psycopg2.Error):
        query("SELECT public.sxf_base_quarantine_obsolete_uid(%s::uuid,%s)",
              (uid,250),role="authenticated")


def test_21_source_retry_does_not_lose_immutable_event_and_is_reclaimable():
    last=query("SELECT max(change_id) AS id FROM public.sxf_base_source_changes")[0]["id"]
    query("UPDATE public.sxf_base_source_deliveries SET state='DONE' WHERE change_id<>%s",
          (last,))
    event=query("SELECT * FROM public.sxf_base_claim_source_changes(%s,%s,%s)",
                ("source-retry",1,180),role="service_role")[0]
    assert event["change_id"]==last
    sql="SELECT public.sxf_base_retry_source_change(%s,%s::uuid,%s,%s) AS ok"
    assert query(sql,(last,str(event["lease_token"]),"SOURCE_MUTATION_REVIEW",60),
                 role="service_role")[0]["ok"] is True
    assert query(sql,(last,str(event["lease_token"]),"SOURCE_MUTATION_REVIEW",60),
                 role="service_role")[0]["ok"] is False
    query("UPDATE public.sxf_base_source_deliveries "
          "SET next_attempt_at=now()-interval '1 second' WHERE change_id=%s",(last,))
    reclaimed=query("SELECT * FROM public.sxf_base_claim_source_changes(%s,%s,%s)",
                    ("source-retry2",1,180),role="service_role")[0]
    assert reclaimed["attempt_count"]==event["attempt_count"]+1
    assert reclaimed["lease_token"]!=event["lease_token"]
    assert query("SELECT count(*) AS n FROM public.sxf_base_source_changes "
                 "WHERE change_id=%s",(last,))[0]["n"]==1


def test_22_source_health_reports_backlog_and_honest_capture_timestamp():
    report=query("SELECT public.sxf_base_source_health() AS payload",
                 role="service_role")[0]["payload"]
    assert report["captured_at_semantics"]=="TRIGGER_TIME_NOT_COMMIT_TIME"
    assert report["source_commit_watermark"] is None
    assert report["source_delivery"]["total"]>=1
    assert report["event_kinds"]["FIXTURE_INSERT"]>=1
    assert report["event_kinds"]["SNAPSHOT_INSERT"]>=1
    with pytest.raises(psycopg2.Error):
        query("SELECT public.sxf_base_source_health()",role="authenticated")


def test_23_source_trigger_and_delivery_rollback_together_on_failed_tx():
    uid=str(uuid4())
    conn=psycopg2.connect(URL,connect_timeout=5)
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO public.fixtures(fixture_uid,kickoff_utc) VALUES(%s::uuid,%s)",
                        (uid,KICKOFF))
            cur.execute("SELECT count(*) FROM public.sxf_base_source_changes WHERE fixture_uid=%s::uuid",
                        (uid,))
            assert cur.fetchone()[0]==1
        conn.rollback()
    finally:
        conn.close()
    assert query("SELECT count(*) AS n FROM public.fixtures WHERE fixture_uid=%s::uuid",(uid,))[0]["n"]==0
    assert query("SELECT count(*) AS n FROM public.sxf_base_source_changes "
                 "WHERE fixture_uid=%s::uuid",(uid,))[0]["n"]==0


def test_24_out_of_order_source_commits_remain_reclaimable_without_id_watermark():
    # Sequence IDs are assigned before COMMIT; a high-water cursor would drop
    # a slower earlier transaction. Pending outbox rows cannot suffer this gap.
    query("UPDATE public.sxf_base_source_deliveries SET state='DONE' "
          "WHERE state<>'DONE'")
    slow_uid=str(uuid4())
    fast_uid=str(uuid4())
    conn=psycopg2.connect(URL,connect_timeout=5)
    try:
        cur=conn.cursor()
        cur.execute("INSERT INTO public.fixtures(fixture_uid,kickoff_utc) VALUES(%s::uuid,%s)",
                    (slow_uid,KICKOFF+timedelta(days=4)))
        cur.execute("SELECT change_id FROM public.sxf_base_source_changes "
                    "WHERE fixture_uid=%s::uuid",(slow_uid,))
        slow_id=cur.fetchone()[0]
        query("INSERT INTO public.fixtures(fixture_uid,kickoff_utc) VALUES(%s::uuid,%s)",
              (fast_uid,KICKOFF+timedelta(days=4,minutes=1)))
        fast_id=query("SELECT change_id FROM public.sxf_base_source_changes "
                      "WHERE fixture_uid=%s::uuid",(fast_uid,))[0]["change_id"]
        assert fast_id>slow_id
        fast_claim=query("SELECT * FROM public.sxf_base_claim_source_changes(%s,%s,%s)",
                         ("fast-committer",1,180),role="service_role")[0]
        assert fast_claim["change_id"]==fast_id
        assert query("SELECT public.sxf_base_ack_source_change(%s,%s::uuid) AS ok",
                     (fast_id,str(fast_claim["lease_token"])),
                     role="service_role")[0]["ok"] is True
        conn.commit()
    finally:
        conn.close()
    delayed=query("SELECT * FROM public.sxf_base_claim_source_changes(%s,%s,%s)",
                  ("slow-committer",1,180),role="service_role")[0]
    assert delayed["change_id"]==slow_id
    assert query("SELECT public.sxf_base_ack_source_change(%s,%s::uuid) AS ok",
                 (slow_id,str(delayed["lease_token"])),role="service_role")[0]["ok"] is True


def test_25_snapshot_index_proposal_has_real_disposable_pg_plan_evidence():
    from base_signal_engine.performance_preflight import snapshot_index_evidence
    query("CREATE INDEX idx_sxf_base_mw_snapshot_uid_time ON "
          "public.moneyway_snapshots(fixture_uid,scraped_at_utc,id)")
    index=query("SELECT indexdef FROM pg_indexes WHERE schemaname='public' AND "
                "indexname='idx_sxf_base_mw_snapshot_uid_time'")
    assert len(index)==1
    assert "fixture_uid, scraped_at_utc, id" in index[0]["indexdef"]
    result=query("EXPLAIN (FORMAT JSON) SELECT id,market,selection FROM "
                 "public.moneyway_snapshots WHERE fixture_uid=%s::uuid "
                 "AND scraped_at_utc>=%s AND scraped_at_utc<=%s "
                 "ORDER BY scraped_at_utc ASC,id ASC LIMIT 750",
                 (UID,KICKOFF-timedelta(hours=8),KICKOFF))
    plan=result[0]["QUERY PLAN"]
    assessment=snapshot_index_evidence(plan)
    assert assessment["result"] in ("INDEX_USAGE_NOT_CONFIRMED","PROPOSED_INDEX_USED")
    assert not assessment["production_plan_verified"]


def test_26_disposable_pg_bulk_source_outbox_atomic_fanout():
    """CI-only fixture/snapshot insert benchmark; no real production volumes."""
    global SOAK_UID
    SOAK_UID=str(uuid4())
    kickoff=KICKOFF+timedelta(days=11)
    query("UPDATE public.sxf_base_source_deliveries SET state='DONE' "
          "WHERE state<>'DONE'")
    query("INSERT INTO public.fixtures(fixture_uid,kickoff_utc) VALUES(%s::uuid,%s)",
          (SOAK_UID,kickoff))
    rows=[]
    for i in range(240):
        stamp=kickoff-timedelta(hours=8,minutes=(i%20)+1,seconds=i//20)
        rows.append((50000+i,SOAK_UID,"1X2","1",1.74,2000,80,stamp))
    elapsed_start=perf_counter()
    with connect() as conn:
        with conn.cursor() as cur:
            execute_values(cur,
                "INSERT INTO public.moneyway_snapshots "
                "(id,fixture_uid,market,selection,odds,volume,share,scraped_at_utc) "
                "VALUES %s",rows,page_size=240)
    milliseconds=(perf_counter()-elapsed_start)*1000
    count=query("SELECT count(*) AS n FROM public.sxf_base_source_changes "
                "WHERE fixture_uid=%s::uuid AND event_kind='SNAPSHOT_INSERT'",
                (SOAK_UID,))[0]["n"]
    assert count==240
    pending=query("SELECT count(*) AS n FROM public.sxf_base_source_deliveries d "
                  "JOIN public.sxf_base_source_changes c ON c.change_id=d.change_id "
                  "WHERE c.fixture_uid=%s::uuid AND c.event_kind='SNAPSHOT_INSERT' "
                  "AND d.state='PENDING'",(SOAK_UID,))[0]["n"]
    assert pending==240
    assert milliseconds>=0
    print("CI_DISPOSABLE_ONLY snapshot_trigger_batch=240 elapsed_ms=" +
          str(round(milliseconds,2)) + " not_a_production_sla")


def test_27_disposable_pg_parallel_source_delivery_claims_are_disjoint():
    """Four workers claim 25 rows each without skipping/duplicating events."""
    # Isolate the 240 snapshot events from the fixture-insert event created
    # during setup. This test targets parallel snapshot delivery only.
    query("UPDATE public.sxf_base_source_deliveries SET state='DONE' WHERE change_id IN "
          "(SELECT change_id FROM public.sxf_base_source_changes "
          "WHERE fixture_uid=%s::uuid AND event_kind='FIXTURE_INSERT')",
          (SOAK_UID,))
    barrier=Barrier(4)
    def worker(name):
        barrier.wait(timeout=15)
        return query("SELECT * FROM public.sxf_base_claim_source_changes(%s,%s,%s)",
                     (name,25,180),role="service_role")
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(worker,"soak-"+str(i)) for i in range(4)]
        groups=[f.result(timeout=25) for f in futures]
    claimed=[r for group in groups for r in group]
    assert len(claimed)==100
    assert len({r["change_id"] for r in claimed})==100
    assert all(str(r["fixture_uid"])==SOAK_UID for r in claimed)
    for record in claimed:
        assert query("SELECT public.sxf_base_ack_source_change(%s,%s::uuid) AS ok",
                     (record["change_id"],str(record["lease_token"])),
                     role="service_role")[0]["ok"] is True
    remaining=query("SELECT count(*) AS n FROM public.sxf_base_source_deliveries d "
                    "JOIN public.sxf_base_source_changes c ON c.change_id=d.change_id "
                    "WHERE c.fixture_uid=%s::uuid AND c.event_kind='SNAPSHOT_INSERT' "
                    "AND d.state='PENDING'",(SOAK_UID,))[0]["n"]
    assert remaining==140


def test_28_restricted_source_writer_trigger_isolation():
    """Normal writer may insert source rows but cannot read/write Base outbox."""
    uid=str(uuid4())
    kickoff=KICKOFF+timedelta(days=16)
    query("CREATE ROLE sxf_source_writer_test NOLOGIN")
    query("GRANT USAGE ON SCHEMA public TO sxf_source_writer_test")
    query("GRANT SELECT,INSERT,UPDATE,DELETE ON public.fixtures,"
          "public.moneyway_snapshots TO sxf_source_writer_test")
    query("INSERT INTO public.fixtures(fixture_uid,kickoff_utc,match_id_hash) "
          "VALUES(%s::uuid,%s,%s)",(uid,kickoff,"restricted"),role="sxf_source_writer_test")
    assert query("SELECT count(*) AS n FROM public.sxf_base_source_changes "
                 "WHERE fixture_uid=%s::uuid AND event_kind='FIXTURE_INSERT'",
                 (uid,))[0]["n"]==1
    for sql in (
        "SELECT count(*) FROM public.sxf_base_source_changes",
        "SELECT count(*) FROM public.sxf_base_source_deliveries",
        "INSERT INTO public.sxf_base_source_changes(event_kind,fixture_uid) "
        "VALUES('FIXTURE_INSERT',gen_random_uuid())",
        "UPDATE public.sxf_base_source_deliveries SET state='DONE'",
    ):
        with pytest.raises(psycopg2.Error):
            query(sql,role="sxf_source_writer_test")
    with pytest.raises(psycopg2.Error):
        query("SELECT * FROM public.sxf_base_claim_source_changes(%s,%s,%s)",
              ("reader",1,180),role="sxf_source_writer_test")


def test_29_source_trigger_drop_rollback_is_nondestructive_and_restores_capture():
    """DBA dry-run drop happens only in rollbacked disposable PG transaction."""
    uid=str(uuid4())
    kickoff=KICKOFF+timedelta(days=17)
    baseline=query("SELECT count(*) AS n FROM public.sxf_base_source_changes")[0]["n"]
    conn=psycopg2.connect(URL,connect_timeout=5)
    try:
        conn.autocommit=False
        with conn.cursor() as cur:
            cur.execute("DROP TRIGGER sxf_base_fixture_source_capture ON public.fixtures")
            cur.execute("DROP TRIGGER sxf_base_snapshot_source_capture ON public.moneyway_snapshots")
            cur.execute("INSERT INTO public.fixtures(fixture_uid,kickoff_utc) VALUES(%s::uuid,%s)",
                        (uid,kickoff))
            cur.execute("SELECT count(*) FROM public.sxf_base_source_changes")
            assert cur.fetchone()[0]==baseline
        conn.rollback()
    finally:
        conn.close()
    triggers=query("SELECT tgname FROM pg_trigger "
                   "WHERE tgname IN ('sxf_base_fixture_source_capture',"
                   "'sxf_base_snapshot_source_capture') ORDER BY tgname")
    assert [r["tgname"] for r in triggers]==[
        "sxf_base_fixture_source_capture","sxf_base_snapshot_source_capture"]
    assert query("SELECT count(*) AS n FROM public.sxf_base_source_changes")[0]["n"]==baseline
    query("INSERT INTO public.fixtures(fixture_uid,kickoff_utc) VALUES(%s::uuid,%s)",
          (uid,kickoff))
    assert query("SELECT count(*) AS n FROM public.sxf_base_source_changes "
                 "WHERE fixture_uid=%s::uuid AND event_kind='FIXTURE_INSERT'",
                 (uid,))[0]["n"]==1
    assert query("SELECT count(*) AS n FROM public.sxf_base_source_changes")[0]["n"]==baseline+1


def test_30_null_uid_moneyway_rows_never_break_existing_source_writes():
    """Live source schema explicitly permits NULL fixture_uid; capture must not abort."""
    sid=932004001
    before=query("SELECT count(*) AS n FROM public.sxf_base_source_changes")[0]["n"]
    query("INSERT INTO public.moneyway_snapshots "
          "(id,fixture_uid,market,selection,scraped_at_utc) "
          "VALUES(%s,NULL,'1X2','1',now())",(sid,))
    query("DELETE FROM public.moneyway_snapshots WHERE id=%s",(sid,))
    after=query("SELECT count(*) AS n FROM public.sxf_base_source_changes")[0]["n"]
    assert after==before


def test_31_null_to_uid_and_uid_to_null_changes_preserve_identity():
    """When identity arrives or disappears, capture still has a physical UID."""
    sid=932004002
    uid=str(uuid4())
    query("INSERT INTO public.moneyway_snapshots "
          "(id,fixture_uid,market,selection,scraped_at_utc) "
          "VALUES(%s,NULL,'1X2','1',now())",(sid,))
    query("UPDATE public.moneyway_snapshots SET fixture_uid=%s::uuid WHERE id=%s",
          (uid,sid))
    change=query("SELECT event_kind,fixture_uid,previous_fixture_uid "
                 "FROM public.sxf_base_source_changes WHERE snapshot_id=%s ORDER BY change_id",
                 (sid,))
    assert len(change)==1 and change[0]["event_kind"]=="SNAPSHOT_CHANGE"
    assert str(change[0]["fixture_uid"])==uid and change[0]["previous_fixture_uid"] is None
    query("UPDATE public.moneyway_snapshots SET fixture_uid=NULL WHERE id=%s",(sid,))
    last=query("SELECT event_kind,fixture_uid,previous_fixture_uid "
               "FROM public.sxf_base_source_changes WHERE snapshot_id=%s ORDER BY change_id",
               (sid,))
    assert len(last)==2 and str(last[-1]["fixture_uid"])==uid
    assert str(last[-1]["previous_fixture_uid"])==uid
    query("DELETE FROM public.moneyway_snapshots WHERE id=%s",(sid,))


def test_32_live_checkpoints_claim_before_stale_bootstrap_debt():
    """Fresh due T-6 claims beat old T-6 jobs, without deleting either."""
    now=datetime.now(timezone.utc)
    uid_old=str(uuid4())
    uid_live=str(uuid4())
    old_kickoff=now+timedelta(hours=1)
    live_kickoff=now+timedelta(hours=5,minutes=45)
    query("INSERT INTO public.fixtures(fixture_uid,kickoff_utc) VALUES "
          "(%s::uuid,%s),(%s::uuid,%s)",
          (uid_old,old_kickoff,uid_live,live_kickoff))
    for uid,kick in ((uid_old,old_kickoff),(uid_live,live_kickoff)):
        assert query("SELECT public.sxf_base_enqueue_jobs(%s::jsonb) AS added",
                     (json.dumps([job_data(uid,kick)]),),role="service_role")[0]["added"]==1
    result=claim("priority-smoke")
    assert len(result)==1
    assert str(result[0]["fixture_uid"])==uid_live
    # One claim must not lose or overwrite the other due job.
    assert query("SELECT state FROM public.sxf_base_checkpoint_jobs "
                 "WHERE fixture_uid=%s::uuid",(uid_old,))[0]["state"]=="PENDING"
    assert query("SELECT state FROM public.sxf_base_checkpoint_jobs "
                 "WHERE fixture_uid=%s::uuid",(uid_live,))[0]["state"]=="LEASED"
