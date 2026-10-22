"""2026-10-22: dense fixture windows must never stall Base discovery or lose fixtures."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from base_signal_engine.discovery import bounded_cursor_discovery_once

START = datetime(2026, 10, 24, 13, tzinfo=timezone.utc)
UTC = timezone.utc


class Catalog:
    def __init__(self, fixtures):
        self.fixtures=fixtures
        self.probed=[]
    def list_between(self, begin, end):
        self.probed.append((begin,end))
        return [f for f in self.fixtures if begin <= f.kickoff_utc <= end]


class Store:
    def __init__(self):
        self.cursor=START
        self.advanced=[]
        self.enqueued=[]
        self.errors=[]
    def health_snapshot(self):
        return {"checkpoint_queue":{"pending_due":0},
                "discovery_cursor":{"initialized":True}}
    def claim_discovery(self, worker_id):
        assert worker_id=="test"
        return {"completed_through":self.cursor}
    def enqueue(self, fixtures):
        self.enqueued.extend(f.fixture_uid for f in fixtures)
        return len(fixtures)*11
    def advance_discovery(self, item, *, end, fixture_count):
        assert end>self.cursor
        self.cursor=end
        self.advanced.append((end,fixture_count))
    def release_discovery(self, item, *, error_code=None):
        self.errors.append(error_code)


def fixture(uid, when):
    return SimpleNamespace(fixture_uid=str(uid),kickoff_utc=when)


def test_real_119_fixture_dense_hour_splits_and_resumes_without_drops():
    # Live 24 Oct 13:00-14:00 UTC: 19 at 13:00, 12 at 13:30,
    # 88 at 14:00. Earlier code rejected all 119, looped exit status 2.
    fixtures=(
        [fixture(i,START) for i in range(19)]
        +[fixture(19+i,START+timedelta(minutes=30)) for i in range(12)]
        +[fixture(31+i,START+timedelta(hours=1)) for i in range(88)]
    )
    cat=Catalog(fixtures)
    store=Store()
    first=bounded_cursor_discovery_once(
        None,store,worker_id="test",catalog=cat,
        max_fixtures=100,allow_high_backlog=True)
    assert first["status"]=="OK" and first["fixtures"]==31
    assert store.cursor == START+timedelta(minutes=30)
    assert store.advanced==[(store.cursor,31)]
    assert len(cat.probed)==2
    # Next cycle re-lists the boundary 13:30, which job keys de-duplicate.
    second=bounded_cursor_discovery_once(
        None,store,worker_id="test",catalog=cat,
        max_fixtures=100,allow_high_backlog=True)
    assert second["status"]=="OK" and second["fixtures"]==100
    assert store.cursor==START+timedelta(hours=1,minutes=30)
    assert len(set(store.enqueued))==119
    assert set(store.enqueued)=={str(i) for i in range(119)}
    assert not store.errors


def test_single_timestamp_over_limit_fails_closed_without_cursor_advance():
    cat=Catalog([fixture(i,START) for i in range(101)])
    store=Store()
    result=bounded_cursor_discovery_once(
        None,store,worker_id="test",catalog=cat,
        max_fixtures=100,allow_high_backlog=True)
    assert result["status"]=="RETRY"
    assert result["enqueued"]==0 and not result["uncertain"]
    assert store.cursor==START and store.advanced==[] and store.enqueued==[]
    assert store.errors==["RUNTIMEERROR"]


def test_small_window_keeps_single_hour_behavior():
    store=Store()
    cat=Catalog([fixture(1,START),fixture(2,START+timedelta(minutes=5))])
    result=bounded_cursor_discovery_once(
        None,store,worker_id="test",catalog=cat,
        max_fixtures=100,allow_high_backlog=True)
    assert result["status"]=="OK" and result["fixtures"]==2
    assert cat.probed==[(START,START+timedelta(hours=1))]
    assert store.cursor==START+timedelta(hours=1)
