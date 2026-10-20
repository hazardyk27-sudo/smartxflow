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
    now=datetime.now(timezone.utc)
    live_uid,old_uid=str(uuid4()),str(uuid4())
    live_kick=now+timedelta(hours=5,minutes=45)
    old_kick=now+timedelta(minutes=45)
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
