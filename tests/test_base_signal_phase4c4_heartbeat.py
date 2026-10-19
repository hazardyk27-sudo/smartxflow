"""Cooperative Base/reconcile heartbeat tests; no external network."""
from datetime import datetime, timezone
from types import SimpleNamespace
import pytest

from base_signal_engine.lease_heartbeat import CooperativeLeaseHeartbeat
from base_signal_engine.reader import SupabaseMoneywayReader
from base_signal_engine.storage import DurableStoreError


def test_pulse_is_rate_limited_and_renew_errors_are_fail_closed():
    now=[100.0]
    calls=[]
    pulse=CooperativeLeaseHeartbeat(lambda:calls.append(now[0]),
        lease_seconds=60,clock=lambda:now[0])
    assert pulse.pulse() is False
    now[0]=119
    assert pulse.pulse() is False
    now[0]=121
    assert pulse.pulse() is True and calls==[121]
    assert pulse.pulse() is False
    now[0]=122
    assert pulse.pulse(force=True) is True
    n=[0]
    def failing():
        n[0]+=1
        if n[0]==1: raise DurableStoreError("lost")
    hb=CooperativeLeaseHeartbeat(failing,lease_seconds=60,clock=lambda:now[0])
    now[0]=143
    with pytest.raises(DurableStoreError):
        hb.pulse()
    assert hb.pulse() is True and n[0]==2


def test_reader_progress_hook_invoked_before_source_page():
    reader=SupabaseMoneywayReader("https://example.supabase.co","unit-secret")
    pages=[]
    reader._get=lambda table,params: pages.append(table) or []
    f=SimpleNamespace(fixture_uid="ef5c99bf-e002-451b-b401-af9174ad53f0",
                      kickoff_utc=datetime(2026,10,20,18,tzinfo=timezone.utc))
    pulses=[]
    reader.load_checkpoints(f,hours=(8,6),as_of_utc=datetime(2026,10,20,14,tzinfo=timezone.utc),
                            progress_hook=lambda:pulses.append("renew"))
    assert pulses==["renew"]*len(pages)
    assert len(pages)>0


def test_reader_aborts_without_more_pages_on_lease_failure():
    reader=SupabaseMoneywayReader("https://example.supabase.co","unit-secret")
    reader._get=lambda *_:pytest.fail("should stop before GET")
    f=SimpleNamespace(fixture_uid="ef5c99bf-e002-451b-b401-af9174ad53f0",
                      kickoff_utc=datetime(2026,10,20,18,tzinfo=timezone.utc))
    with pytest.raises(DurableStoreError):
        reader.load_checkpoints(
            f,hours=(8,),as_of_utc=datetime(2026,10,20,14,tzinfo=timezone.utc),
            progress_hook=lambda:(_ for _ in ()).throw(DurableStoreError("lease-lost")))


def test_heartbeat_input_requires_safe_lease_range():
    with pytest.raises(ValueError):
        CooperativeLeaseHeartbeat(lambda:None,lease_seconds=10)
