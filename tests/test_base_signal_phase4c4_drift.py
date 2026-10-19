"""Part 4C4A recurring overlap and kickoff identity safety."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from base_signal_engine.discovery import rolling_rescan_once
from base_signal_engine.scheduler import FixtureRef
from base_signal_engine.storage import DurableStoreError, SupabaseCheckpointStore

NOW=datetime(2026,10,20,15,tzinfo=timezone.utc)
UID=str(uuid4())


class Catalog:
    def __init__(self):
        self.rows=[FixtureRef(UID,NOW+timedelta(days=1))]
        self.calls=[]
    def list_between(self,start,end):
        self.calls.append((start,end))
        return self.rows[:]


class Store:
    def __init__(self):
        self.keys=set()
        self.calls=[]
        self.fail=None
    def enqueue(self,fixtures):
        self.calls.append("enqueue")
        if self.fail=="enqueue":
            raise RuntimeError("database write failed")
        keys={f.fixture_uid+f.kickoff_utc.isoformat() for f in fixtures}
        added=len(keys-self.keys)*11
        self.keys.update(keys)
        return added
    def quarantine_fixture_drift(self,*,limit):
        self.calls.append("quarantine")
        if self.fail=="quarantine":
            raise DurableStoreError("timeout")
        return 11


def test_repeated_window_only_adds_new_uid_kickoff_jobs_once():
    catalog=Catalog()
    store=Store()
    first=rolling_rescan_once(object(),store,now=NOW,catalog=catalog)
    second=rolling_rescan_once(object(),store,now=NOW,catalog=catalog)
    assert first["enqueued"]==11 and second["enqueued"]==0
    assert first["superseded_jobs"]==11
    assert first["complete_ingestion_history"] is False
    assert catalog.calls[0][0]==NOW-timedelta(days=14)
    assert catalog.calls[0][1]==NOW+timedelta(hours=74)


def test_kickoff_reschedule_gets_new_jobs_and_old_jobs_are_quarantined():
    catalog=Catalog()
    store=Store()
    rolling_rescan_once(object(),store,now=NOW,catalog=catalog)
    catalog.rows=[FixtureRef(UID,NOW+timedelta(days=2))]
    status=rolling_rescan_once(object(),store,now=NOW,catalog=catalog)
    assert status["enqueued"]==11 and status["superseded_jobs"]==11


def test_failure_cannot_silently_advance_or_claim_coverage():
    catalog=Catalog()
    store=Store()
    store.fail="enqueue"
    with pytest.raises(RuntimeError):
        rolling_rescan_once(object(),store,now=NOW,catalog=catalog)
    assert store.calls==["enqueue"]
    store.fail="quarantine"
    with pytest.raises(DurableStoreError):
        rolling_rescan_once(object(),store,now=NOW,catalog=catalog)


def test_window_bounds_and_untrusted_inputs_rejected():
    for k in (0,31,True,1.5):
        with pytest.raises(ValueError):
            rolling_rescan_once(object(),Store(),now=NOW,catalog=Catalog(),lookback_days=k)
    for k in (0,1001,True):
        with pytest.raises(ValueError):
            rolling_rescan_once(object(),Store(),now=NOW,catalog=Catalog(),drift_limit=k)


def test_sql_rpc_bounded_and_service_role_only():
    from pathlib import Path
    script=(Path(__file__).resolve().parents[1]/
            "migrations/2026_10_19_sxf_base_phase4c4_kickoff_drift.sql").read_text()
    assert "sxf_base_insert_identity_guard" in script
    assert "sxf_base_quarantine_fixture_drift" in script
    assert "FOR UPDATE OF j SKIP LOCKED" in script
    assert "state='SUPERSEDED'" in script
    assert "sxf_base_fixture_drift_events_immutable" in script
    assert "GRANT EXECUTE ON FUNCTION" in script
    assert "TO service_role" in script
    assert "UPDATE public.moneyway_snapshots" not in script
