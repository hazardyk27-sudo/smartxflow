"""Isolated disposable PostgreSQL integration for proposed Phase 4 migrations.

Requires SXF_TEST_DATABASE_URL explicitly; CI supplies a throwaway Postgres.
NEVER point this at production, staging, or an existing Supabase project.
"""
from concurrent.futures import ThreadPoolExecutor
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
from psycopg2.extras import RealDictCursor

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
