"""Step 2: every physical fixture gets all eleven frozen jobs, without a dependency on signal worker."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from base_signal_engine import fixture_discovery_worker as app
from base_signal_engine.scheduler import CHECKPOINT_TASKS, CheckpointJob, FixtureRef
from base_signal_engine.storage import DurableStoreError, ReadOnlyStoreError, SupabaseCheckpointStore

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
    assert result["new_jobs"]==37*len(CHECKPOINT_TASKS)
    assert result["fixtures_needing_enqueue"]==37
    assert result["coverage_verified_for_snapshot"] is True
    assert len(store.keys)==37*len(CHECKPOINT_TASKS)
    assert len([c for c in store.calls if c[0]=="enqueue"])==4
    assert len(pings)==5  # 4 acknowledged batches and drift finalization
    assert catalog.windows==[(NOW,NOW+timedelta(hours=80))]
    again=app.scan_horizon_once(None,store,now=NOW,catalog=catalog)
    assert again["fixtures_needing_enqueue"]==0
    assert again["new_jobs"]==0
    assert again["fully_scheduled_before"]==37


def test_past_and_started_fixtures_never_get_new_jobs_even_when_catalog_returns_them():
    # Test the hard fence, not only the default catalog query bounds.
    past=fixture(21,NOW-timedelta(minutes=5))
    started_now=fixture(22,NOW)
    future=fixture(23,NOW+timedelta(minutes=5))
    store=Store()
    catalog=Catalog([past,started_now,future])
    result=app.scan_horizon_once(None,store,now=NOW,catalog=catalog,
                                 lookback_hours=2)
    assert catalog.windows==[(NOW-timedelta(hours=2),NOW+timedelta(hours=80))]
    assert result["fixtures"]==1
    assert result["fixtures_needing_enqueue"]==1
    assert result["new_jobs"]==len(CHECKPOINT_TASKS)
    assert ("enqueue",1,200) in store.calls
    assert all(CheckpointJob(future,h,fam).key in store.keys
               for h,fam in CHECKPOINT_TASKS)
    assert all(CheckpointJob(past,h,fam).key not in store.keys
               and CheckpointJob(started_now,h,fam).key not in store.keys
               for h,fam in CHECKPOINT_TASKS)


def test_default_discovery_uses_only_future_kickoff_window():
    catalog=Catalog([])
    result=app.scan_horizon_once(None,Store(),now=NOW,catalog=catalog)
    assert result["status"]=="SCANNED"
    assert result["range_start"]==NOW.isoformat()
    assert catalog.windows==[(NOW,NOW+timedelta(hours=80))]


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
    store.drift=len(CHECKPOINT_TASKS)
    report=app.scan_horizon_once(None,store,now=NOW,catalog=Catalog([f1]))
    assert report["new_jobs"]==len(CHECKPOINT_TASKS) and report["superseded_drift_jobs"]==len(CHECKPOINT_TASKS)
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



def test_immutable_returning_kickoff_only_quarantines_its_own_fixture():
    blocked = fixture(2)
    fixtures = [fixture(1), blocked, fixture(3)]

    class CollisionStore(Store):
        def enqueue(self, group, *, batch_size=200):
            self.calls.append(("attempt", len(group)))
            if any(f.fixture_uid == blocked.fixture_uid for f in group):
                raise DurableStoreError("sxf_base_enqueue_jobs failed: HTTP 400")
            return super().enqueue(group, batch_size=batch_size)

        def is_protected_returning_fixture(self, f):
            self.calls.append(("proof", f.fixture_uid))
            return f.fixture_uid == blocked.fixture_uid

    store = CollisionStore()
    report = app.scan_horizon_once(None, store, now=NOW,
                                   catalog=Catalog(fixtures))
    assert report["status"] == "SCANNED_WITH_PROTECTED_EXCEPTIONS"
    assert report["protected_returning_fixtures"] == 1
    assert report["coverage_verified_for_snapshot"] is False
    assert report["verified_fixtures"] == 2
    assert report["new_jobs"] == 2*len(CHECKPOINT_TASKS)
    assert ("proof", blocked.fixture_uid) in store.calls
    for f in (fixtures[0], fixtures[2]):
        assert all(CheckpointJob(f, h, fam).key in store.keys
                   for h, fam in CHECKPOINT_TASKS)
    assert not any(CheckpointJob(blocked, h, fam).key in store.keys
                   for h, fam in CHECKPOINT_TASKS)


@pytest.mark.parametrize("http_error", [
    "sxf_base_enqueue_jobs failed: HTTP 500",
    "sxf_base_enqueue_jobs unavailable (Timeout)",
    "sxf_base_enqueue_jobs failed: HTTP 503",
])
def test_uncertain_discovery_errors_still_stop_without_retry(http_error):
    class UnsafeStore(Store):
        def enqueue(self, group, *, batch_size=200):
            self.calls.append(("attempt", len(group)))
            raise DurableStoreError(http_error)
        def is_protected_returning_fixture(self, f):
            raise AssertionError("must not consult immutable exceptions")
    store = UnsafeStore()
    with pytest.raises(DurableStoreError):
        app.scan_horizon_once(None, store, now=NOW,
                              catalog=Catalog([fixture(1), fixture(2)]))
    assert [x[0] for x in store.calls].count("attempt") == 1


def test_unproven_http_400_fails_closed_instead_of_skipping():
    class InvalidStore(Store):
        def enqueue(self, group, *, batch_size=200):
            self.calls.append(("attempt", len(group)))
            raise DurableStoreError("sxf_base_enqueue_jobs failed: HTTP 400")
        def is_protected_returning_fixture(self, f):
            return False
    store=InvalidStore()
    with pytest.raises(DurableStoreError):
        app.scan_horizon_once(None, store, now=NOW,
                              catalog=Catalog([fixture(1),fixture(2)]))


def test_readonly_protection_proof_requires_old_job_and_immutable_event():
    uid = str(uuid4())
    for pages, expected in (
        ([[{"job_id":uid}],[{"event_id":1}]],True),
        ([[{"job_id":uid}],[]],False),
        ([[],],False),
    ):
        session=HttpSession(pages)
        store=SupabaseCheckpointStore("https://db.invalid","test",session=session)
        assert store.is_protected_returning_fixture(fixture(1)) is expected
        assert session.calls[0][0].endswith("sxf_base_checkpoint_jobs")
        assert session.calls[0][1]["state"] == "eq.SUPERSEDED"
        if expected:
            assert session.calls[1][0].endswith("sxf_base_signal_events")


def test_production_feed_smoke_is_read_only_and_gated_to_exact_sha():
    from pathlib import Path
    workflow = (Path(__file__).resolve().parents[1] /
                ".github/workflows/sxf-signal-feed-production-smoke.yml").read_text()
    assert "EXPECTED_SHA" in workflow
    assert 'test "$synced" = 1' in workflow
    assert 'BaseSignalsFeed(url,key).read(start,days=21)' in workflow
    assert 'FEED_PRIVATE_21DAY_OK' in workflow
    assert 'systemctl restart' not in workflow
    assert 'systemctl reset-failed' not in workflow


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


def test_reschedule_quarantine_sql_preserves_live_worker_leases():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    migration=(root/"migrations/2026_10_21_sxf_base_quarantine_preserve_live_leases.sql").read_text()
    assert "AND (j.state <> 'LEASED' OR j.lease_expires_at <= now())" in migration
    assert "INSERT INTO public.sxf_base_fixture_drift_events" in migration
    assert "DELETE FROM " not in migration
    assert "TRUNCATE " not in migration
    assert "DROP " not in migration


def test_concurrent_fixture_reschedule_retries_instead_of_killing_discovery():
    old = fixture(10, NOW + timedelta(hours=40))
    changed = fixture(10, NOW + timedelta(hours=41))

    class RescheduledCatalog:
        def __init__(self):
            self.calls = 0
        def list_between(self, start, end):
            self.calls += 1
            return [old] if self.calls == 1 else [changed]

    # An acknowledged enqueue may be superseded by another service between
    # enqueue and the final key read. The old frozen identity is no longer
    # authoritative. Never claim full coverage, but next scan must recover.
    class ConcurrentStore(Store):
        def active_job_keys_between(self, start, end):
            self.calls.append(("read", start, end))
            if len([c for c in self.calls if c[0] == "read"]) == 2:
                return set()
            return set(self.keys)

    store = ConcurrentStore()
    cat = RescheduledCatalog()
    with pytest.raises(app.FixtureCatalogChanged, match="identity changed"):
        app.scan_horizon_once(None, store, now=NOW, catalog=cat)
    assert cat.calls == 2
    assert ("enqueue", 1, 200) in store.calls
    assert len(store.keys) == len(CHECKPOINT_TASKS)
    # No historical record is deleted; the fresh kickoff creates its own
    # independent, idempotent 10-job identity in the following sweep.
    result = app.scan_horizon_once(None, store, now=NOW, catalog=cat)
    assert result["status"] == "SCANNED"
    assert result["coverage_verified_for_snapshot"]
    assert result["new_jobs"] == len(CHECKPOINT_TASKS)
    assert len(store.keys) == 2*len(CHECKPOINT_TASKS)


def test_stable_fixture_missing_jobs_never_masquerades_as_catalog_race():
    candidate = fixture(11)
    class FailedStore(Store):
        def enqueue(self, fixtures, *, batch_size=200):
            self.calls.append(("enqueue", len(fixtures), batch_size))
            return 0
    with pytest.raises(app.FixtureHorizonUnverified,
                       match="post-enqueue checkpoint coverage incomplete"):
        app.scan_horizon_once(None, FailedStore(), now=NOW,
                              catalog=Catalog([candidate]))


def test_superceded_job_keys_cannot_produce_false_complete_coverage():
    class CannotRestoreHistoricalJob(Store):
        def enqueue(self, fixtures, *, batch_size=200):
            self.calls.append(("enqueue",len(fixtures),batch_size))
            return 0  # old SUPERSEDED identity conflicts with immutable key
    store=CannotRestoreHistoricalJob()
    with pytest.raises(app.FixtureHorizonUnverified,
                       match="post-enqueue checkpoint coverage incomplete"):
        app.scan_horizon_once(None,store,now=NOW,catalog=Catalog([fixture(7)]))
    assert ("drift",250) in store.calls


def test_complete_snapshot_has_post_enqueue_verification():
    store=Store()
    app.scan_horizon_once(None,store,now=NOW,catalog=Catalog([fixture(8)]))
    assert len([c for c in store.calls if c[0]=="read"])==2
