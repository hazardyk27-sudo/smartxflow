"""Part 4C4B: fenced discovery lease renewal without production writes."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from base_signal_engine.discovery import discover_window_once
from base_signal_engine.runtime import SupabaseFixtureCatalog
from base_signal_engine.storage import DurableStoreError

NOW=datetime(2026,10,20,12,tzinfo=timezone.utc)


class Store:
    def __init__(self, fail=False):
        self.calls=[]
        self.fail=fail
    def claim_discovery(self,worker):
        self.calls.append("claim")
        return {"cursor_name":"BASE_FIXTURES",
                "completed_through": NOW-timedelta(days=3),
                "bootstrap_start": NOW-timedelta(days=7),
                "lease_token":"token","lease_attempts":1}
    def renew_discovery(self, item, *, lease_seconds):
        self.calls.append("renew")
        if self.fail: raise DurableStoreError("lost")
    def enqueue(self,fixtures):
        self.calls.append("enqueue")
        return len(fixtures)*11
    def advance_discovery(self,item,*,end,fixture_count):
        self.calls.append("advance")
    def release_discovery(self,item,*,error_code=None):
        self.calls.append("release")


class Catalog:
    def list_between(self,a,b): return []


def test_discovery_renews_lease_at_page_boundaries_and_before_advance():
    s=Store()
    report=discover_window_once(object(),s,worker_id="worker",now=NOW,catalog=Catalog())
    assert report["advanced"] is True
    assert s.calls==["claim","renew","renew","enqueue","renew","advance"]


def test_lost_discovery_renewal_prevents_watermark_advance():
    s=Store(fail=True)
    report=discover_window_once(object(),s,worker_id="worker",now=NOW,catalog=Catalog())
    assert not report["advanced"] and report["retry"]
    assert "advance" not in s.calls


def test_fixture_pagination_calls_progress_before_each_request():
    rows=[
      {"fixture_uid":"ef5c99bf-e002-451b-b401-af9174ad53f0",
       "kickoff_utc":NOW.isoformat(),"match_id_hash":"legacy"},
    ]
    class Fake:
        def __init__(self): self.calls=0
        def _get(self,table,params):
            self.calls+=1
            return rows if self.calls==1 else []
    reader=Fake()
    catalog=SupabaseFixtureCatalog(reader,page_size=1,max_pages=3)
    beats=[]
    results=catalog.list_between(NOW-timedelta(days=1),NOW+timedelta(days=1),
                                 progress_hook=lambda: beats.append(1))
    assert len(results)==1
    assert len(beats)==2 and reader.calls==2


def test_migration_has_grants_and_lease_token_fencing():
    from pathlib import Path
    sql=(Path(__file__).resolve().parents[1]/
         "migrations/2026_10_19_sxf_base_phase4c4_discovery_heartbeat.sql").read_text()
    assert "sxf_base_renew_discovery" in sql
    assert "c.lease_token=p_lease_token" in sql
    assert "c.lease_expires_at>now()" in sql
    assert "TO service_role" in sql
    assert "SECURITY DEFINER" not in sql
