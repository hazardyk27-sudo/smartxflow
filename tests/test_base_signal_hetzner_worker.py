"""Hetzner durable worker glue: no auto-activation or legacy writes."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from base_signal_engine import hetzner_worker as app


class FakeStore:
    def health_snapshot(self):
        return {"checkpoint_queue":{"pending_due":2,"expired_leases":0},
                "reconciliation_queue":{"pending_due":1,"expired_leases":0}}


def test_hetzner_worker_bounded_real_components_and_debt(monkeypatch):
    called=[]
    def discovery(reader,store,*,lookback_days):
        called.append(("discovery",lookback_days))
        return {"enqueued":7,"fixtures_discovered":3,"superseded_jobs":0}
    jobs=[{"claimed":1,"completed":1,"waiting_data":0,"retry":0,
           "lease_lost":0,"commit_uncertain":0},
          {"claimed":0,"completed":0,"waiting_data":0,"retry":0,
           "lease_lost":0,"commit_uncertain":0}]
    def claim(reader,store,*,worker_id,limit):
        assert limit==1 and worker_id=="hetzner-base-one"
        return jobs.pop(0)
    def reconcile(reader,store,*,worker_id):
        called.append(("reconcile",worker_id))
        return {"claimed":0,"completed":0,"waiting_data":0,"retried":0,
                "lease_uncertain":0,"commit_uncertain":0}
    monkeypatch.setattr(app,"rolling_rescan_once",discovery)
    monkeypatch.setattr(app,"execute_claims",claim)
    monkeypatch.setattr(app,"reconcile_once",reconcile)
    report=app.run_cycle(object(),FakeStore(),worker_id="hetzner-base-one")
    assert report["discovery"]=="OK" and report["enqueued"]==7
    assert report["completed"]==1 and report["claimed"]==1
    assert report["checkpoint_pending_due"]==2 and report["reconcile_pending_due"]==1
    assert report["healthy_cycle"] and report["source_capture_enabled"] is False
    assert report["production_release_verified"] is False
    assert called==[("discovery",1),("reconcile","hetzner-base-one")]


def test_catalog_error_does_not_hide_previously_durable_job(monkeypatch):
    def broken(*args,**kwargs):
        raise RuntimeError("simulated read-only fixture discovery outage")
    monkeypatch.setattr(app,"rolling_rescan_once",broken)
    monkeypatch.setattr(app,"execute_claims",lambda *args,**kw:
        {"claimed":0,"completed":0,"waiting_data":0,"retry":0,
         "lease_lost":0,"commit_uncertain":0})
    monkeypatch.setattr(app,"reconcile_once",lambda *args,**kw:
        {"claimed":0,"completed":0,"waiting_data":0,"retried":0,
         "lease_uncertain":0,"commit_uncertain":0})
    report=app.run_cycle(object(),FakeStore(),worker_id="worker",max_jobs=1)
    assert report["discovery"]=="ERROR_RUNTIMEERROR"
    assert not report["healthy_cycle"]


def test_durable_cycle_rejects_unsafe_work_bounds():
    for kwargs in ({"max_jobs":0},{"max_jobs":31},{"max_reconcile":6},
                   {"lookback_days":0},{"worker_id":""}):
        with pytest.raises(ValueError):
            app.run_cycle(None,None,**({"worker_id":"worker"} | kwargs))


def test_corrupt_health_is_never_reported_as_zero(monkeypatch):
    monkeypatch.setattr(app,"execute_claims",lambda *a,**k:
        {"claimed":0,"completed":0,"waiting_data":0,"retry":0,
         "lease_lost":0,"commit_uncertain":0})
    class Corrupt:
        def health_snapshot(self):
            return {"checkpoint_queue":{"pending_due":None,"expired_leases":0},
                    "reconciliation_queue":{"pending_due":0,"expired_leases":0}}
    with pytest.raises(ValueError,match="health metric"):
        app.run_cycle(None,Corrupt(),worker_id="worker",discover=False,max_reconcile=0)


def test_cli_requires_explicit_approval(monkeypatch):
    monkeypatch.delenv("SXF_BASE_DURABLE_WORKER_APPROVED",raising=False)
    with pytest.raises(SystemExit,match="2"):
        app.main(["--once"])


def test_hetzner_worker_is_isolated_and_cannot_auto_start_before_approval():
    root=Path(__file__).resolve().parents[1]
    s=(root/"deploy/systemd/smartxflow-base-worker.service").read_text()
    sync=(root/"deploy/sync_runtime_units.sh").read_text()
    assert "ExecStart=/opt/smartxflow/venv/bin/python -m base_signal_engine.hetzner_worker" in s
    assert "User=smartxflow" in s and "ProtectSystem=strict" in s
    assert "MemoryMax=320M" in s and "Restart=on-failure" in s
    assert "SXF_BASE_DURABLE_WORKER_APPROVED=yes" not in s
    assert "smartxflow-base-worker.service" not in sync
    assert "systemctl start" not in s


def test_one_shot_pending_job_mode_skips_discovery_and_reconciliation(monkeypatch,capsys):
    """The Hetzner pending-job smoke cannot accidentally bulk-enqueue fixtures."""
    monkeypatch.setenv("SXF_BASE_DURABLE_WORKER_APPROVED","yes")
    monkeypatch.setenv("SXF_BASE_COMPOSITE_INDEX_VERIFIED","yes")
    monkeypatch.setenv("SUPABASE_URL","https://source.invalid")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY","isolated-test-value")
    monkeypatch.setattr(app,"SupabaseMoneywayReader",lambda *a,**k: object())
    monkeypatch.setattr(app,"SupabaseCheckpointStore",lambda *a,**k: object())
    called=[]
    def fake_cycle(reader,store,*,worker_id,discover,max_jobs,max_reconcile,lookback_days):
        called.append((worker_id,discover,max_jobs,max_reconcile,lookback_days))
        return {"discovery":"SKIPPED","claimed":1,"completed":1,
                "lease_uncertain":0,"commit_uncertain":0,"reconcile_uncertain":0}
    monkeypatch.setattr(app,"run_cycle",fake_cycle)
    assert app.main(["--once","--no-discovery","--max-jobs","1",
                     "--max-reconcile","0"])==0
    assert called==[("hetzner-base-one",False,1,0,1)]
    assert '"completed": 1' in capsys.readouterr().out


def test_no_discovery_requires_single_cycle_even_if_worker_approved(monkeypatch):
    monkeypatch.setenv("SXF_BASE_DURABLE_WORKER_APPROVED","yes")
    monkeypatch.setenv("SXF_BASE_COMPOSITE_INDEX_VERIFIED","yes")
    with pytest.raises(SystemExit,match="2"):
        app.main(["--no-discovery"])


def test_uncertain_checkpoint_commit_stops_further_claims_and_reconciliation(monkeypatch):
    """Do not continue to mutate the queue when an ACK may be ambiguous."""
    calls=[]
    monkeypatch.setattr(app,"execute_claims",lambda *args,**kwargs:
        (calls.append("checkpoint") or
         {"claimed":1,"completed":0,"waiting_data":0,"retry":0,
          "lease_lost":0,"commit_uncertain":1}))
    monkeypatch.setattr(app,"reconcile_once",lambda *args,**kwargs:
        (calls.append("reconcile") or
         {"claimed":0,"completed":0,"waiting_data":0,"retried":0,
          "lease_uncertain":0,"commit_uncertain":0}))
    result=app.run_cycle(object(),FakeStore(),worker_id="worker",
                         discover=False,max_jobs=12,max_reconcile=5)
    assert calls==["checkpoint"]
    assert result["claimed"]==1
    assert result["commit_uncertain"]==1
    assert result["reconcile_claimed"]==0
    assert result["healthy_cycle"] is False


def test_lost_checkpoint_lease_blocks_reconcile_and_further_claims(monkeypatch):
    calls=[]
    monkeypatch.setattr(app,"execute_claims",lambda *args,**kwargs:
        (calls.append("checkpoint") or
         {"claimed":1,"completed":0,"waiting_data":0,"retry":0,
          "lease_lost":1,"commit_uncertain":0}))
    monkeypatch.setattr(app,"reconcile_once",lambda *args,**kwargs:
        (calls.append("reconcile") or {}))
    result=app.run_cycle(object(),FakeStore(),worker_id="worker",
                         discover=False,max_jobs=30,max_reconcile=5)
    assert calls==["checkpoint"]
    assert result["lease_uncertain"]==1
    assert result["healthy_cycle"] is False


def test_reconcile_uncertainty_stops_batch(monkeypatch):
    calls=[]
    monkeypatch.setattr(app,"execute_claims",lambda *args,**kwargs:
        {"claimed":0,"completed":0,"waiting_data":0,"retry":0,
         "lease_lost":0,"commit_uncertain":0})
    monkeypatch.setattr(app,"reconcile_once",lambda *args,**kwargs:
        (calls.append("reconcile") or
         {"claimed":1,"completed":0,"waiting_data":0,"retried":0,
          "lease_uncertain":1,"commit_uncertain":0}))
    result=app.run_cycle(object(),FakeStore(),worker_id="worker",
                         discover=False,max_jobs=5,max_reconcile=5)
    assert calls==["reconcile"]
    assert result["reconcile_uncertain"]==1
    assert result["healthy_cycle"] is False


def test_one_shot_unhealthy_discovery_exits_nonzero(monkeypatch):
    monkeypatch.setenv("SXF_BASE_DURABLE_WORKER_APPROVED","yes")
    monkeypatch.setenv("SXF_BASE_COMPOSITE_INDEX_VERIFIED","yes")
    monkeypatch.setenv("SUPABASE_URL","https://source.invalid")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY","isolated-test-value")
    monkeypatch.setattr(app,"SupabaseMoneywayReader",lambda *a,**k: object())
    monkeypatch.setattr(app,"SupabaseCheckpointStore",lambda *a,**k: object())
    monkeypatch.setattr(app,"run_cycle",lambda *a,**k:
        {"discovery":"ERROR_CATALOGREADERROR","healthy_cycle":False,
         "lease_uncertain":0,"commit_uncertain":0,"reconcile_uncertain":0})
    assert app.main(["--once"])==2


def test_one_shot_ambiguous_commit_exits_operator_review(monkeypatch):
    monkeypatch.setenv("SXF_BASE_DURABLE_WORKER_APPROVED","yes")
    monkeypatch.setenv("SXF_BASE_COMPOSITE_INDEX_VERIFIED","yes")
    monkeypatch.setenv("SUPABASE_URL","https://source.invalid")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY","isolated-test-value")
    monkeypatch.setattr(app,"SupabaseMoneywayReader",lambda *a,**k: object())
    monkeypatch.setattr(app,"SupabaseCheckpointStore",lambda *a,**k: object())
    monkeypatch.setattr(app,"run_cycle",lambda *a,**k:
        {"discovery":"SKIPPED","healthy_cycle":False,
         "lease_uncertain":0,"commit_uncertain":1,"reconcile_uncertain":0})
    assert app.main(["--once","--no-discovery"])==3
