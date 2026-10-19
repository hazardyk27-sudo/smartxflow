"""Part 4C4C health telemetry contract and server-only RPC."""
from pathlib import Path
import pytest
from base_signal_engine.storage import SupabaseCheckpointStore, DurableStoreError


class Response:
    def __init__(self, body): self.status_code=200; self.body=body
    def json(self): return self.body


class Session:
    def __init__(self, body): self.body=body; self.ops=[]
    def post(self,url,*,json,headers,timeout):
        self.ops.append(url.rsplit("/",1)[-1])
        return Response(self.body)


def test_health_is_service_only_and_contains_explicit_unknown_watermark():
    s=Session({"generated_at":"2026-10-19T00:00:00+00:00",
               "checkpoint_queue":{"total":0},
               "reconciliation_queue":{"total":0},
               "discovery_cursor":{"initialized":False},
               "fixture_identity":{"drift_events":0},
               "snapshot_ingestion_watermark":None})
    store=SupabaseCheckpointStore("https://example.supabase.co","private-server-key",session=s)
    report=store.health_snapshot()
    assert report["snapshot_ingestion_watermark"] is None
    assert s.ops==["sxf_base_health_snapshot"]


def test_health_malformed_rpc_is_not_misreported_as_healthy():
    s=Session({"status":"OK"})
    with pytest.raises(DurableStoreError):
        SupabaseCheckpointStore("https://example.supabase.co","private-key",session=s).health_snapshot()


def test_health_sql_never_grants_public_read_or_mutates_history():
    sql=(Path(__file__).resolve().parents[1]/
         "migrations/2026_10_19_sxf_base_phase4c4_health.sql").read_text()
    assert "SECURITY INVOKER" in sql and "STABLE" in sql
    assert "GRANT EXECUTE ON FUNCTION public.sxf_base_health_snapshot() TO service_role" in sql
    assert "FROM PUBLIC,anon,authenticated" in sql
    assert "'snapshot_ingestion_watermark',NULL" in sql
    assert "UPDATE public." not in sql and "DELETE FROM public." not in sql
