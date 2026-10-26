"""Synthetic Part 4C2 gated durable reconciliation dispatch tests."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from base_signal_engine.reconcile_runtime import reconcile_once, missing_source_reconcile_delay
from base_signal_engine.rules import Fixture, Quote, Snapshot

UID="ef5c99bf-e002-451b-b401-af9174ad53f0"
KO=datetime(2026,10,20,18,tzinfo=timezone.utc)


def claim():
    return {"reconciliation_id":3,"origin_event_key":"key:DECISION:1X2",
        "fixture_uid":UID,"kickoff_utc":KO,"market":"1X2",
        "lease_token":str(uuid4()),"attempt_count":1}


class Reader:
    def __init__(self, provided=True, malformed=False):
        self.provided,self.malformed=provided,malformed
    def load_fixture(self, uid):
        return Fixture(uid,KO),"legacy"
    def load_checkpoints(self,fixture,*,hours,as_of_utc,include_v2_history,expected_legacy_hash):
        q={"1":Quote("1.75",1500,80),"X":Quote("3.2",100,10),"2":Quote("4.1",100,10)}
        snap=Snapshot("1X2",KO-timedelta(hours=6,minutes=5),q)
        return SimpleNamespace(
            snapshots=(snap,) if self.provided else (),
            source_row_ids={("1X2",snap.observed_at):(1,2,3)} if self.provided and not self.malformed else {})


class Store:
    def __init__(self, rows=None, fail=None):
        self.rows=[claim()] if rows is None else rows
        self.calls=[]
        self.fail=fail
    def claim_reconcile(self,worker_id,*,lease_seconds):
        self.calls.append("claim")
        return self.rows
    def retry_reconcile(self,item,*,reason,delay_seconds):
        self.calls.append(("retry",reason,delay_seconds))
    def renew_reconcile(self,item,*,lease_seconds):
        self.calls.append("renew")
        if self.fail=="renew":
            from base_signal_engine.storage import DurableStoreError
            raise DurableStoreError("lost")
    def complete_reconcile(self,item,plan):
        self.calls.append(("complete",plan.source_snapshot_ids,len(plan.signals)))
        if self.fail=="commit":
            from base_signal_engine.storage import DurableStoreError
            raise DurableStoreError("timeout")


def test_missing_source_is_waiting_without_fake_completion():
    store=Store()
    result=reconcile_once(Reader(provided=False),store,worker_id="worker")
    assert result["waiting_data"]==1 and result["completed"]==0
    assert store.calls==["claim",("retry","SOURCE_INCOMPLETE",900)]


def test_complete_late_t6_uses_real_row_ids_and_frozen_rule_hits():
    store=Store()
    result=reconcile_once(Reader(),store,worker_id="worker")
    assert result["completed"]==1
    assert store.calls[0]=="claim" and store.calls[1]=="renew"
    assert store.calls[-1][0]=="complete" and store.calls[-1][1]==(1,2,3)
    assert store.calls[-1][2]>=1


def test_bad_provenance_retries_without_minting_signal():
    store=Store()
    result=reconcile_once(Reader(malformed=True),store,worker_id="worker")
    assert result["retried"]==1
    assert not any(isinstance(x,tuple) and x[0]=="complete" for x in store.calls)


def test_unknown_commit_result_is_not_counted_success_or_retry():
    store=Store(fail="commit")
    result=reconcile_once(Reader(),store,worker_id="worker")
    assert result["commit_uncertain"]==1 and result["completed"]==0
    assert not any(isinstance(x,tuple) and x[0]=="retry" for x in store.calls)


def test_lease_renewal_failure_prevents_late_event_write():
    store=Store(fail="renew")
    result=reconcile_once(Reader(),store,worker_id="worker")
    assert result["lease_uncertain"]==1 and result["completed"]==0
    assert not any(isinstance(x,tuple) and x[0]=="complete" for x in store.calls)


def test_no_reconcile_claims_do_not_read_source():
    store=Store(rows=[])
    result=reconcile_once(object(),store,worker_id="worker")
    assert result["claimed"]==0 and result["completed"]==0

def test_repeated_missing_t6_uses_bounded_backoff_to_unblock_pending():
    assert [missing_source_reconcile_delay(n) for n in (1, 3, 4, 6, 7, 146)] == [
        900, 900, 1800, 1800, 3600, 3600]
    for invalid in (0, -1, True, 1.5):
        with pytest.raises(ValueError):
            missing_source_reconcile_delay(invalid)

    old = claim()
    old["attempt_count"] = 146
    store = Store(rows=[old])
    result = reconcile_once(Reader(provided=False), store, worker_id="worker")
    assert result["waiting_data"] == 1
    assert store.calls == ["claim", ("retry", "SOURCE_INCOMPLETE", 3600)]


def test_due_time_claim_migration_prevents_old_waiting_data_starvation():
    from pathlib import Path
    sql=(Path(__file__).resolve().parents[1]/
         "migrations/2026_10_26_sxf_base_reconcile_due_time_fairness.sql"
         ).read_text(encoding="utf-8")
    assert "CREATE OR REPLACE FUNCTION public.sxf_base_claim_reconcile" in sql
    assert "WHEN r.state='LEASED' THEN r.lease_expires_at" in sql
    assert "ELSE r.next_attempt_at END ASC" in sql
    assert "r.reconciliation_id ASC" in sql
    assert "FOR UPDATE OF r SKIP LOCKED" in sql
    assert "e.ruleset_version='SXF_SIGNAL_MOTOR_V3_2026_10_24'" in sql
    assert "r.next_attempt_at<=now()" in sql
    assert "r.lease_expires_at<now()" in sql
    assert "attempt_count=r.attempt_count+1" in sql
    assert "SECURITY INVOKER" in sql and "TO service_role" in sql
    for token in ("DELETE FROM", "TRUNCATE", "DROP TABLE", "UPDATE public.sxf_base_signal_events"):
        assert token not in sql
