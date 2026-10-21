"""Guard tests: no ambiguous write replay, no restart until DB leases expired."""
from datetime import datetime, timezone
import importlib.util
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("sxf_guarded_recovery",
    ROOT/"scripts/base_worker_guarded_recovery.py")
guard=importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
AT=datetime(2026,10,21,12,0,tzinfo=timezone.utc)
EXIT_US=60_000_000


def simulation(*, unit="failed", status="3", last=EXIT_US, elapsed=2400,
               active=None, db_error=False, env=True):
    values={"UnitFileState":"enabled","ActiveState":unit,
            "ExecMainStatus":status,"Result":"exit-code",
            "ExecMainExitTimestampMonotonic":str(last)}
    events=[]
    class Response:
        status_code=503 if db_error else 200
        def __init__(self, rows):self.rows=rows
        def json(self): return self.rows
    class Session:
        def get(self, url, *, params, headers, timeout):
            events.append(("db",url.rsplit("/",1)[-1]))
            if db_error:return Response([])
            return Response([{"lease_owner":"someone", "lease_expires_at":AT.isoformat()}]
                            if active==url.rsplit("/",1)[-1] else [])
    def run(*args):
        events.append(("cmd",args[1]))
        if args[1]=="show":return values[args[args.index("-p")+1]]
        if args[1]=="reset-failed":
            values["ActiveState"]="inactive"
        if args[1]=="start":
            values["ActiveState"]="active"
        return ""
    if env:
        from os import environ
        environ.update({"SXF_BASE_DURABLE_WORKER_APPROVED":"yes",
                        "SXF_BASE_COMPOSITE_INDEX_VERIFIED":"yes",
                        "SXF_BASE_PRIORITY_LANES_APPROVED":"yes",
                        "SUPABASE_URL":"https://example.invalid",
                        "SUPABASE_SERVICE_ROLE_KEY":"test-only"})
    result=guard.evaluate(run=run,session=Session(),now_mono=last/1e6+elapsed,utc_now=AT)
    return result,events


def test_idle_failed_worker_restarts_only_after_30min_and_empty_leases():
    result,events=simulation()
    assert result=="RECOVERY_STARTED"
    assert len([e for e in events if e[0]=="db"])==3
    assert ("cmd","reset-failed") in events and ("cmd","start") in events


def test_no_restart_before_cooling_period():
    result,events=simulation(elapsed=1200)
    assert result=="SKIP_COOLDOWN"
    assert not any(e[0]=="db" for e in events)
    assert ("cmd","start") not in events


@pytest.mark.parametrize("table",[
    "sxf_base_checkpoint_jobs","sxf_base_reconcile_jobs","sxf_base_discovery_cursors"])
def test_any_live_lease_blocks_recovery(table):
    result,events=simulation(active=table)
    assert result=="SKIP_ACTIVE_DB_LEASE"
    assert ("cmd","start") not in events


def test_rejected_database_read_blocks_restart():
    result,events=simulation(db_error=True)
    assert result=="SKIP_DB_READ_UNCERTAIN"
    assert ("cmd","start") not in events


@pytest.mark.parametrize("state,status",[("active","3"),("failed","4"),("failed","2"),
                                         ("inactive","3"),("activating","3")])
def test_nonfenced_or_current_state_does_not_restart(state,status):
    result,events=simulation(unit=state,status=status)
    assert result != "RECOVERY_STARTED"
    assert ("cmd","start") not in events


def test_recovery_unit_uses_existing_app_credentials_without_mutating_snapshots():
    service=(ROOT/"deploy/systemd/smartxflow-base-guarded-recovery.service").read_text()
    timer=(ROOT/"deploy/systemd/smartxflow-base-guarded-recovery.timer").read_text()
    assert "base_worker_guarded_recovery.py" in service
    assert "EnvironmentFile=/opt/smartxflow/.env" in service
    assert "EnvironmentFile=/etc/smartxflow/base-worker.env" in service
    assert "OnUnitActiveSec=5min" in timer
    assert "WantedBy=timers.target" in timer
    script=(ROOT/"scripts/base_worker_guarded_recovery.py").read_text()
    assert "DELETE FROM" not in script
    assert "TRUNCATE" not in script
    assert "MIN_COOLDOWN_SEC = 1800" in script
