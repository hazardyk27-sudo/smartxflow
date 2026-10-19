"""Part 5A source outbox and immutable mutation review tests."""
from datetime import datetime, timezone, timedelta
from uuid import uuid4

import pytest
from base_signal_engine.source_change_runtime import process_source_change_once
from base_signal_engine.storage import DurableStoreError

KO=datetime(2026,10,20,18,tzinfo=timezone.utc)
UID=str(uuid4())
OLD_UID=str(uuid4())
BASE={"change_id":4,"lease_token":str(uuid4()),
      "fixture_uid":UID,"previous_fixture_uid":None,
      "event_kind":"FIXTURE_INSERT","source_observed_at":None,"market":None}


class Store:
    def __init__(self, event=None, *, exists=True):
        self.event=event or BASE
        self.exists=exists
        self.calls=[]
        self.keys=set()
        self.fail_ack=False
        self.remaining=0
    def claim_source_changes(self,worker_id,*,lease_seconds):
        self.calls.append("claim")
        return [self.event] if self.event else []
    def source_fixture_state(self,uid):
        self.calls.append(("state",uid))
        return KO if self.exists else None
    def enqueue(self,items):
        self.calls.append("enqueue")
        keys={x.fixture_uid+str(x.kickoff_utc) for x in items}
        added=len(keys-self.keys)*11
        self.keys.update(keys)
        return added
    def quarantine_obsolete_uid(self,uid,*,limit):
        self.calls.append(("quarantine",uid))
        return self.remaining
    def wake_late_t6(self,uid,market,observed_at):
        self.calls.append(("wake",market))
        return 1
    def ack_source_change(self,item):
        self.calls.append("ack")
        if self.fail_ack:
            raise DurableStoreError("ambiguous HTTP response")
    def retry_source_change(self,item,*,reason,delay_seconds):
        self.calls.append(("retry",reason,delay_seconds))


def test_fixture_insert_enqueues_once_and_acks_only_after_drift_check():
    store=Store()
    first=process_source_change_once(store,worker_id="operator")
    assert first["acknowledged"]==1 and first["retry"]==0
    assert store.calls==["claim",("state",UID),"enqueue",("quarantine",UID),"ack"]
    before=len(store.keys)
    second=process_source_change_once(store,worker_id="operator")
    assert second["acknowledged"]==1 and len(store.keys)==before


def test_removed_uid_is_quarantined_even_when_source_fixture_absent():
    store=Store({**BASE,"event_kind":"FIXTURE_DELETE"},exists=False)
    result=process_source_change_once(store,worker_id="w")
    assert result["acknowledged"]==1
    assert "enqueue" not in store.calls
    assert ("quarantine",UID) in store.calls


def test_uid_remap_quarantines_both_previous_and_current_uid():
    store=Store({**BASE,"event_kind":"FIXTURE_CHANGE",
                 "previous_fixture_uid":OLD_UID})
    answer=process_source_change_once(store,worker_id="w")
    assert answer["acknowledged"]==1
    assert {x[1] for x in store.calls if isinstance(x,tuple) and x[0]=="quarantine"}=={UID,OLD_UID}


def test_bounded_quarantine_never_acks_possible_remaining_jobs():
    store=Store()
    store.remaining=250
    result=process_source_change_once(store,worker_id="w")
    assert result["retry"]==1 and result["acknowledged"]==0
    assert store.calls[-1]==("retry","RUNTIMEERROR",300)


def test_snapshot_arrival_wakes_reconcile_without_modifying_event():
    s=Store({**BASE,"event_kind":"SNAPSHOT_INSERT",
             "market":"1X2","snapshot_id":1001,
             "source_observed_at":KO-timedelta(hours=6,minutes=5)})
    result=process_source_change_once(s,worker_id="w")
    assert result["acknowledged"]==1
    assert ("wake","1X2") in s.calls
    assert "enqueue" not in s.calls


def test_modified_snapshot_stays_in_review_not_silently_acked():
    for event in ("SNAPSHOT_CHANGE","SNAPSHOT_DELETE"):
        s=Store({**BASE,"event_kind":event})
        result=process_source_change_once(s,worker_id="w")
        assert result["manual_review"]==1 and result["acknowledged"]==0
        assert s.calls[-1]==("retry","SOURCE_MUTATION_REVIEW",3600)


def test_ack_timeout_is_ambiguous_not_success_or_failure():
    s=Store();s.fail_ack=True
    result=process_source_change_once(s,worker_id="w")
    assert result["uncertain"]==1 and result["acknowledged"]==0
    assert "ack" in s.calls
    assert not any(isinstance(x,tuple) and x[0]=="retry" for x in s.calls)


def test_outbox_input_guard_refuses_invalid_quarantine_limit():
    with pytest.raises(ValueError):
        process_source_change_once(Store(),worker_id="w",quarantine_limit=0)


def test_ledger_sql_is_explicitly_source_trigger_proposal():
    from pathlib import Path
    sql=(Path(__file__).resolve().parents[1]/
         "migrations/2026_10_19_sxf_base_phase5a_source_capture_PROPOSED.sql").read_text()
    for expected in ("sxf_base_source_changes","sxf_base_source_deliveries",
                     "sxf_base_capture_snapshot_change",
                     "sxf_base_capture_fixture_change","FOR UPDATE SKIP LOCKED",
                     "sxf_base_quarantine_obsolete_uid","sxf_base_wake_late_t6",
                     "sxf_base_source_fixture_state","sxf_base_source_changes_immutable",
                     "SECURITY DEFINER","SECURITY INVOKER","TO service_role"):
        assert expected in sql
    assert "UPDATE public.moneyway_snapshots" not in sql
    assert "DELETE FROM public.moneyway_snapshots" not in sql
