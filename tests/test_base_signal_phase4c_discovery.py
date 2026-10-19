"""Part 4C3 durable discovery contiguous watermark and replay tests."""
from datetime import datetime,timedelta,timezone

import pytest

from base_signal_engine.discovery import discover_window_once
from base_signal_engine.scheduler import FixtureRef
from base_signal_engine.storage import DurableStoreError

NOW=datetime(2026,10,20,16,tzinfo=timezone.utc)
START=NOW-timedelta(days=14)
UID="ef5c99bf-e002-451b-b401-af9174ad53f0"


class Catalog:
    def __init__(self,fail=False): self.fail=fail;self.windows=[]
    def list_between(self,a,b):
        self.windows.append((a,b))
        if self.fail: raise RuntimeError("source outage")
        return [FixtureRef(UID,a+timedelta(hours=12))]


class Store:
    def __init__(self, start=START, fail=None):
        self.cursor=start
        self.fail=fail
        self.calls=[]
        self.ready=True
    def claim_discovery(self,worker_id):
        self.calls.append("claim")
        return {"cursor_name":"BASE_FIXTURES","bootstrap_start":START,
                "completed_through":self.cursor,"lease_token":"synthetic-token",
                "lease_attempts":1} if self.ready else None
    def enqueue(self, fixtures):
        self.calls.append("enqueue")
        if self.fail=="enqueue": raise RuntimeError("queue unavailable")
        return len(fixtures)*11
    def advance_discovery(self,item,*,end,fixture_count):
        self.calls.append("advance")
        if self.fail=="advance": raise DurableStoreError("ambiguous reply")
        assert self.cursor==item["completed_through"]
        self.cursor=end
    def release_discovery(self,item,*,error_code=None):
        self.calls.append(("release",error_code))


def test_discovery_advances_only_after_complete_catalog_and_enqueue():
    store=Store()
    cat=Catalog()
    answer=discover_window_once(object(),store,worker_id="w",now=NOW,catalog=cat)
    assert answer["advanced"] and not answer["retry"]
    assert store.cursor==START+timedelta(days=1)
    assert answer["fixtures"]==1 and answer["enqueued"]==11
    assert store.calls==["claim","enqueue","advance"]


def test_backfill_replay_after_partial_source_or_enqueue_failure():
    for failure in ("catalog","enqueue"):
        store=Store(fail="enqueue" if failure=="enqueue" else None)
        cat=Catalog(fail=failure=="catalog")
        result=discover_window_once(object(),store,worker_id="w",now=NOW,catalog=cat)
        assert result["retry"] and not result["advanced"]
        assert store.cursor==START
        assert store.calls[-1][0]=="release"
        store.fail=None;cat.fail=False
        second=discover_window_once(object(),store,worker_id="w",now=NOW,catalog=cat)
        assert second["advanced"] and store.cursor==START+timedelta(days=1)


def test_watermark_http_timeout_is_uncertain_not_false_success():
    store=Store(fail="advance")
    status=discover_window_once(object(),store,worker_id="w",now=NOW,catalog=Catalog())
    assert status["uncertain"] and not status["advanced"]
    assert store.cursor==START


def test_no_cursor_is_not_auto_bootstrapped():
    store=Store();store.ready=False
    status=discover_window_once(object(),store,worker_id="w",now=NOW,catalog=Catalog())
    assert status["idle"] and not status["claimed"]
    assert store.calls==["claim"]


def test_one_day_cap_and_future_cursor_idle():
    store=Store(start=NOW+timedelta(days=5))
    status=discover_window_once(object(),store,worker_id="w",now=NOW,catalog=Catalog())
    assert status["idle"] and ("release",None) in store.calls
    with pytest.raises(ValueError):
        discover_window_once(object(),store,worker_id="w",now=NOW,window_hours=48)
