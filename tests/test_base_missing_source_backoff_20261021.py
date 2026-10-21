"""Missing real market history stays WAITING_DATA, with bounded age-aware retry."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import pytest

from base_signal_engine.durable_runtime import source_wait_delay_seconds, execute_claims
from base_signal_engine.rules import Fixture
from base_signal_engine.scheduler import FixtureRef, CheckpointJob
from base_signal_engine.storage import SupabaseCheckpointStore

NOW=datetime(2026,10,21,15,0,tzinfo=timezone.utc)
UID=str(uuid4())
KO=NOW+timedelta(hours=1)


def job(hours,age_hours):
    kickoff=NOW+timedelta(hours=hours-age_hours)
    return CheckpointJob(FixtureRef(UID,kickoff),hours,"EARLY_CORE" if hours>=24 else "BASE")


def test_age_based_missing_source_policy_only():
    cases=[(72,-1,180),(72,0,180),(72,2,180),
           (72,2.01,3600),(72,24,3600),(72,24.01,21600),
           (72,100,21600),(6,0.1,180),(6,3,3600)]
    for hours,age,delay in cases:
        assert source_wait_delay_seconds(job(hours,age),at=NOW)==delay


def test_missing_snapshot_terminally_skipped_once_with_fenced_ack():
    # The database skip RPC rejects matches at or after kickoff. A mocked
    # store must exercise only the still-future LIVE-lane fixture contract.
    old=job(72,71)
    assert old.timestamp < NOW < old.fixture.kickoff_utc
    class Reader:
        def load_fixture(self,fixture_uid):
            return Fixture(old.fixture.fixture_uid,old.fixture.kickoff_utc),"original-hash"
        def load_checkpoints(self,*a,**kw):
            return SimpleNamespace(snapshots=(),fetched_rows=0,discarded_groups=0,
                                   hash_drift_rows=0)
    class Store:
        def __init__(self):self.skipped=[]
        def claim(self,*a,**kw):
            return [SimpleNamespace(job=old,job_id=str(uuid4()),
                                    lease_token=str(uuid4()),attempt_count=1)]
        def skip_missing_source(self,item,*,reason):
            self.skipped.append(reason)
        def fail(self,*args,**kw):
            raise AssertionError("Missing source is not a computation error")
        def complete(self,*a,**kw):
            raise AssertionError("Missing source must never complete")
    store=Store()
    result=execute_claims(Reader(),store,worker_id="w")
    assert result["waiting_data"]==0 and result["skipped_data"]==1
    assert result["completed"]==0
    assert store.skipped==["SOURCE_INCOMPLETE"]


def test_missing_source_writer_limit_only_increased_for_wait():
    src=(Path(__file__).resolve().parents[1]/"base_signal_engine/storage.py").read_text()
    assert 'if not 60 <= delay_seconds <= 21600:' in src
    assert 'if not 10 <= delay_seconds <= 3600:' in src
    sql=(Path(__file__).resolve().parents[1]/
         "migrations/2026_10_21_sxf_base_waiting_data_age_retry.sql").read_text()
    assert "p_retry_seconds NOT BETWEEN 60 AND 21600" in sql
    assert "END $function$;\nREVOKE" in sql
    assert "j.lease_token=p_lease_token" in sql
    assert "j.lease_expires_at>now()" in sql
    assert "DELETE FROM" not in sql
    assert "TRUNCATE " not in sql


def test_wait_window_never_estimated_from_naive_clock():
    with pytest.raises(ValueError):
        source_wait_delay_seconds(job(72,1),at=datetime(2026,10,21,15))
