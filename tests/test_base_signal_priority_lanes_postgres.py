"""Disposable PostgreSQL only; prerequisite phase4 fixture, roles and migration.

The existing phase4 suite is run in the SAME pytest invocation by CI.
No live Supabase/Hetzner connection is allowed.
"""
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
if not os.environ.get("SXF_TEST_DATABASE_URL"):
    pytest.skip("disposable PostgreSQL integration only",allow_module_level=True)
from tests.test_base_signal_postgres_phase4 import query, job_data
import json

def test_99_priority_lanes_claim_separately_and_preserve_unclaimed_jobs():
    # Earlier Phase-4 tests intentionally leave due fixtures in this same
    # disposable DB. The widened real LIVE predicate correctly sees them.
    # Delay only those leftovers so priority-lane isolation is deterministic;
    # never perform this operation against a real database.
    query("UPDATE public.sxf_base_checkpoint_jobs "
          "SET next_attempt_at=now()+interval '30 days' "
          "WHERE state IN ('PENDING','RETRY','WAITING_DATA')")
    now=datetime.now(timezone.utc)
    live_uid,old_uid=str(uuid4()),str(uuid4())
    live_kick=now+timedelta(hours=5,minutes=45)
    old_kick=now-timedelta(minutes=45)  # Now a true post-start backlog job
    query("INSERT INTO public.fixtures(fixture_uid,kickoff_utc) VALUES "
          "(%s::uuid,%s),(%s::uuid,%s)",(live_uid,live_kick,old_uid,old_kick))
    jobs=[job_data(live_uid,live_kick),job_data(old_uid,old_kick)]
    for job in jobs:
        assert query("SELECT public.sxf_base_enqueue_jobs(%s::jsonb) AS n",
                     (json.dumps([job]),),role="service_role")[0]["n"]==1
    live=query("SELECT * FROM public.sxf_base_claim_due_jobs_lane(%s,%s,%s,%s)",
               ("test-priority-live","LIVE",1,900),role="service_role")
    assert len(live)==1 and str(live[0]["fixture_uid"])==live_uid
    old=query("SELECT * FROM public.sxf_base_claim_due_jobs_lane(%s,%s,%s,%s)",
              ("test-priority-backlog","BACKLOG",1,900),role="service_role")
    # The oldest backlog may be from another earlier fixture, but it must not
    # return the already leased live fixture and must have a different token.
    assert len(old)==1 and str(old[0]["fixture_uid"])!=live_uid
    assert str(old[0]["lease_token"])!=str(live[0]["lease_token"])
    live_row=query("SELECT lease_token,state FROM public.sxf_base_checkpoint_jobs "
                   "WHERE fixture_uid=%s::uuid",(live_uid,))[0]
    assert live_row["state"]=="LEASED"
    assert str(live_row["lease_token"])==str(live[0]["lease_token"])
    assert query("SELECT state FROM public.sxf_base_checkpoint_jobs "
                 "WHERE fixture_uid=%s::uuid",(old_uid,))[0]["state"] in ("PENDING","LEASED")
    with pytest.raises(Exception):
        query("SELECT * FROM public.sxf_base_claim_due_jobs_lane(%s,%s,%s,%s)",
              ("bad-worker","ALL",1,900),role="service_role")
    with pytest.raises(Exception):
        query("SELECT * FROM public.sxf_base_claim_due_jobs_lane(%s,%s,%s,%s)",
              ("bad-worker","LIVE",2,900),role="service_role")
    for role in ("anon","authenticated"):
        with pytest.raises(Exception):
            query("SELECT * FROM public.sxf_base_claim_due_jobs_lane(%s,%s,%s,%s)",
                  ("unauthorized","LIVE",1,900),role=role)


def test_99b_null_lane_or_timeout_is_rejected_before_claim():
    for args in (("worker",None,1,900),
                 ("worker","LIVE",None,900),
                 ("worker","BACKLOG",1,None)):
        with pytest.raises(Exception):
            query("SELECT * FROM public.sxf_base_claim_due_jobs_lane(%s,%s,%s,%s)",
                  args,role="service_role")


def test_99c_concurrent_same_lane_claims_do_not_duplicate_leases():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    now=datetime.now(timezone.utc)
    uid=str(uuid4())
    kickoff=now+timedelta(hours=5,minutes=45)
    query("INSERT INTO public.fixtures(fixture_uid,kickoff_utc) VALUES (%s::uuid,%s)",
          (uid,kickoff))
    assert query("SELECT public.sxf_base_enqueue_jobs(%s::jsonb) AS n",
                 (json.dumps([job_data(uid,kickoff)]),),role="service_role")[0]["n"]==1
    gate=Barrier(2)
    def claim(name):
        gate.wait(timeout=10)
        return query("SELECT * FROM public.sxf_base_claim_due_jobs_lane(%s,%s,%s,%s)",
                     (name,"LIVE",1,900),role="service_role")
    with ThreadPoolExecutor(max_workers=2) as pool:
        left=pool.submit(claim,"live-race-a")
        right=pool.submit(claim,"live-race-b")
        claimed=left.result(timeout=20)+right.result(timeout=20)
    assert len(claimed)==1, "two LIVE workers must never claim one job twice"
    assert str(claimed[0]["fixture_uid"])==uid
    # Existing lease token fence remains authoritative after prioritized claim.
    assert query("SELECT public.sxf_base_renew_lease(%s::uuid,%s::uuid,%s) AS ok",
        (str(claimed[0]["job_id"]),str(uuid4()),900),role="service_role")[0]["ok"] is False


def test_99d_pre_kickoff_t6_t8_remain_live_after_three_hours():
    now=datetime.now(timezone.utc)
    uid=str(uuid4())
    kickoff=now+timedelta(hours=2)
    query("INSERT INTO public.fixtures(fixture_uid,kickoff_utc) VALUES (%s::uuid,%s)",(uid,kickoff))
    t6=job_data(uid,kickoff)
    t8={**t6,"job_key":t6["job_key"].replace(":T-6",":T-8"),"checkpoint_hours":8}
    assert query("SELECT public.sxf_base_enqueue_jobs(%s::jsonb) AS n",
                 (json.dumps([t6,t8]),),role="service_role")[0]["n"]==2
    rows=query("SELECT checkpoint_hours,checkpoint_at FROM public.sxf_base_checkpoint_jobs "
               "WHERE fixture_uid=%s::uuid",(uid,))
    assert len(rows)==2
    assert all(x["checkpoint_at"]<now-timedelta(hours=3) for x in rows)
    first=query("SELECT * FROM public.sxf_base_claim_due_jobs_lane(%s,%s,%s,%s)",
                ("catchup-t6","LIVE",1,900),role="service_role")
    assert len(first)==1 and str(first[0]["fixture_uid"])==uid
    assert first[0]["checkpoint_hours"]==6
    second=query("SELECT * FROM public.sxf_base_claim_due_jobs_lane(%s,%s,%s,%s)",
                 ("catchup-t8","LIVE",1,900),role="service_role")
    assert len(second)==1 and str(second[0]["fixture_uid"])==uid
    assert second[0]["checkpoint_hours"]==8


def test_99e_started_match_is_only_backlog_not_live():
    now=datetime.now(timezone.utc)
    uid=str(uuid4())
    kickoff=now-timedelta(minutes=15)
    query("INSERT INTO public.fixtures(fixture_uid,kickoff_utc) VALUES (%s::uuid,%s)",(uid,kickoff))
    assert query("SELECT public.sxf_base_enqueue_jobs(%s::jsonb) AS n",
                 (json.dumps([job_data(uid,kickoff)]),),role="service_role")[0]["n"]==1
    eligible=query("SELECT (family='BASE' AND checkpoint_hours IN(8,6) AND "
                   "kickoff_utc>now() AND checkpoint_at<=now() AND "
                   "checkpoint_at>=now()-interval '8 hours') AS live_eligible "
                   "FROM public.sxf_base_checkpoint_jobs WHERE fixture_uid=%s::uuid",(uid,))[0]
    assert eligible["live_eligible"] is False
    got=query("SELECT * FROM public.sxf_base_claim_due_jobs_lane(%s,%s,%s,%s)",
              ("after-start-backlog","BACKLOG",1,900),role="service_role")
    assert len(got)==1 and str(got[0]["fixture_uid"])==uid
