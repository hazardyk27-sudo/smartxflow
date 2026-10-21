"""Step 2: every physical fixture gets all eleven frozen jobs, without a dependency on signal worker."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from base_signal_engine import fixture_discovery_worker as app
from base_signal_engine.scheduler import CHECKPOINT_TASKS, CheckpointJob, FixtureRef
from base_signal_engine.storage import ReadOnlyStoreError, SupabaseCheckpointStore

NOW = datetime(2026, 10, 21, 3, 0, tzinfo=timezone.utc)


def fixture(index, kickoff=None):
    return FixtureRef(str(UUID(int=index+1)), kickoff or NOW+timedelta(hours=65))


class Catalog:
    def __init__(self, fixtures):
        self.fixtures = fixtures
        self.windows = []
    def list_between(self, start, end):
        self.windows.append((start, end))
        return self.fixtures


class Store:
    def __init__(self, existing=None):
        self.keys = set(existing or ())
        self.calls = []
        self.drift = 0
    def health_snapshot(self):
        return {"discovery_cursor":{"initialized":True}}
    def active_job_keys_between(self, start, end):
        self.calls.append(("read",start,end))
        return set(self.keys)
    def enqueue(self, fixtures, *, batch_size=200):
        self.calls.append(("enqueue",len(fixtures),batch_size))
        before=len(self.keys)
        for f in fixtures:
            for hours,family in CHECKPOINT_TASKS:
                self.keys.add(CheckpointJob(f,hours,family).key)
        return len(self.keys)-before
    def quarantine_fixture_drift(self, *,limit=250):
        self.calls.append(("drift",limit))
        return self.drift


def test_full_80h_sweep_schedules_all_fixture_families_and_is_idempotent():
    fixtures=[fixture(i) for i in range(37)]
    catalog=Catalog(fixtures)
    store=Store()
    pings=[]
    result=app.scan_horizon_once(None,store,now=NOW,catalog=catalog,fixture_batch=12,
                                 progress_hook=lambda:pings.append("ack"))
    assert result["status"]=="SCANNED"
    assert result["fixtures"]==37
    assert result["new_jobs"]==37*11
    assert result["fixtures_needing_enqueue"]==37
    assert result["coverage_verified_for_snapshot"] is True
    assert len(store.keys)==37*11
    assert len([c for c in store.calls if c[0]=="enqueue"])==4
    assert len(pings)==5  # 4 acknowledged batches and drift finalization
    assert catalog.windows==[(NOW-timedelta(hours=2),NOW+timedelta(hours=80))]
    again=app.scan_horizon_once(None,store,now=NOW,catalog=catalog)
    assert again["fixtures_needing_enqueue"]==0
    assert again["new_jobs"]==0
    assert again["fully_scheduled_before"]==37


def test_partial_checkpoint_identity_is_not_mistaken_for_complete_fixture():
    f=fixture(1)
    keys={CheckpointJob(f,h,fam).key for h,fam in CHECKPOINT_TASKS[:-1]}
    report=app.scan_horizon_once(None,Store(keys),now=NOW,catalog=Catalog([f]))
    assert report["fixtures_needing_enqueue"]==1
    assert report["new_jobs"]==1


def test_rescheduled_kickoff_generates_new_identity_and_quarantines_old():
    f0=fixture(4,NOW+timedelta(hours=7))
    f1=fixture(4,NOW+timedelta(hours=62))
    old={CheckpointJob(f0,h,fam).key for h,fam in CHECKPOINT_TASKS}
    store=Store(old)
    store.drift=11
    report=app.scan_horizon_once(None,store,now=NOW,catalog=Catalog([f1]))
    assert report["new_jobs"]==11 and report["superseded_drift_jobs"]==11
    assert all(CheckpointJob(f1,h,fam).key in store.keys for h,fam in CHECKPOINT_TASKS)
    assert report["drift_may_remain"] is False


def test_incomplete_catalog_and_active_keys_block_all_mutations():
    store=Store()
    class BrokenCatalog:
        def list_between(self,*args):
            raise RuntimeError("incomplete catalog")
    with pytest.raises(RuntimeError):
        app.scan_horizon_once(None,store,now=NOW,catalog=BrokenCatalog())
    assert store.calls==[]
    class BrokenKeys(Store):
        def active_job_keys_between(self,*args):
            raise ReadOnlyStoreError("incomplete listing")
    broken=BrokenKeys()
    with pytest.raises(ReadOnlyStoreError):
        app.scan_horizon_once(None,broken,now=NOW,catalog=Catalog([fixture(1)]))
    assert not [e for e in broken.calls if e[0]=="enqueue"]


def test_overflow_and_uninitialized_cursor_never_silently_skip_matches():
    store=Store()
    with pytest.raises(app.FixtureHorizonUnverified):
        app.scan_horizon_once(None,store,now=NOW,catalog=Catalog([fixture(i) for i in range(4)]),
                              max_fixtures=3)
    assert store.calls==[]
    class NotInitialized(Store):
        def health_snapshot(self):
            return {"discovery_cursor":{"initialized":False}}
    s=NotInitialized()
    with pytest.raises(app.FixtureHorizonUnverified):
        app.scan_horizon_once(None,s,now=NOW,catalog=Catalog([fixture(3)]))
    assert not s.calls


def test_reject_unsafe_scan_configuration():
    for params in ({"forward_hours":73},{"forward_hours":100},
                   {"lookback_hours":25},{"fixture_batch":21},
                   {"max_fixtures":0}):
        with pytest.raises(ValueError):
            app.scan_horizon_once(None,Store(),now=NOW,**params)


class HttpResponse:
    status_code=200
    def __init__(self,rows):self.rows=rows
    def json(self):return self.rows


class HttpSession:
    def __init__(self,pages):
        self.pages=list(pages)
        self.calls=[]
    def get(self,url,*,params,headers,timeout):
        self.calls.append((url,dict(params)))
        return HttpResponse(self.pages.pop(0))


def test_existing_job_key_reader_fetches_all_pages_without_slicing():
    session=HttpSession([[{"job_key":"k1"},{"job_key":"k2"}],[{"job_key":"k3"}]])
    store=SupabaseCheckpointStore("https://db.invalid","test",session=session)
    keys=store.active_job_keys_between(NOW,NOW+timedelta(hours=80),page_size=2)
    assert keys=={"k1","k2","k3"}
    assert len(session.calls)==2
    assert session.calls[0][0].endswith("/rest/v1/sxf_base_checkpoint_jobs")
    assert session.calls[0][1]["state"]=="neq.SUPERSEDED"


def test_incomplete_or_duplicate_key_listing_must_fail_closed():
    for pages,max_pages in (
        ([[{"job_key":"a"}]],1),
        ([[{"job_key":"a"}],[{"job_key":"a"}]],2),
    ):
        s=HttpSession(pages)
        store=SupabaseCheckpointStore("https://db.invalid","test",session=s)
        with pytest.raises(ReadOnlyStoreError):
            store.active_job_keys_between(NOW,NOW+timedelta(hours=80),
                                          page_size=1,max_pages=max_pages)


def test_cli_is_gated_and_service_has_independent_restart_policy(monkeypatch):
    monkeypatch.delenv("SXF_BASE_FIXTURE_DISCOVERY_APPROVED",raising=False)
    with pytest.raises(SystemExit):
        app.main(["--once"])
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    unit=(root/"deploy/systemd/smartxflow-base-fixture-discovery.service").read_text()
    assert "ExecStart=/opt/smartxflow/venv/bin/python -m base_signal_engine.fixture_discovery_worker" in unit
    assert "RestartPreventExitStatus=3 4" in unit
    assert "Type=notify" in unit and "WatchdogSec=480" in unit
    assert "EnvironmentFile=/etc/smartxflow/base-fixture-discovery.env" in unit
