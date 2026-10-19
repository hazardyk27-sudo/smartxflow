"""Phase 4B2 SQL and adapter safety; no access to live Supabase."""
from pathlib import Path
from uuid import uuid4

import pytest

from base_signal_engine.storage import SupabaseCheckpointStore, DurableStoreError

ROOT=Path(__file__).resolve().parents[1]
SQL=(ROOT/"migrations/2026_10_19_sxf_base_phase4b_reconciliation_rpc.sql").read_text()


class Response:
    def __init__(self, payload, status=200):
        self.status_code, self.payload= status, payload
    def json(self): return self.payload


class Rpc:
    def __init__(self, result=True, status=200):
        self.calls=[]
        self.result,self.status=result,status
    def post(self,url,*,json,headers,timeout):
        self.calls.append((url,json))
        return Response(self.result,self.status)


def test_rpc_is_allowlisted_and_exact_replays_are_not_new_signals():
    fake=Rpc(result=False)
    client=SupabaseCheckpointStore("https://example.supabase.co","SECRET_DO_NOT_LOG",session=fake)
    result=client.append_reconciliation(origin_event_key="origin",kind="CORRECTED",
        source_snapshot_ids=[11,12,13],details={"reason":"LATE_T6"},
        engine="1X2_CONCENTRATION_V1",selection="1")
    assert result is False
    assert fake.calls[0][0].endswith("/rpc/sxf_base_append_reconciliation")
    assert fake.calls[0][1]["p_source_snapshot_ids"]==[11,12,13]
    fake.result=True
    assert client.append_reconciliation(origin_event_key="origin",kind="INVALIDATED",
        source_snapshot_ids=[11,12,13],details={"reason":"NO_T6_HIT"}) is True


def test_rpc_rejects_illegal_kind_partial_engine_malformed_source():
    client=SupabaseCheckpointStore("https://example.supabase.co","SECRET",session=Rpc())
    bad=[
        dict(kind="SETTLED",source_snapshot_ids=[1,2]),
        dict(kind="CORRECTED",source_snapshot_ids=[1]),
        dict(kind="CORRECTED",source_snapshot_ids=[1,1]),
        dict(kind="CORRECTED",source_snapshot_ids=[0,2]),
        dict(kind="CORRECTED",source_snapshot_ids=[True,2]),
        dict(kind="INVALIDATED",source_snapshot_ids=[1,2],engine="BTTS_YES",selection="Y"),
        dict(kind="CORRECTED",source_snapshot_ids=[1,2],engine="BTTS_YES"),
    ]
    for value in bad:
        with pytest.raises(ValueError):
            client.append_reconciliation(origin_event_key="origin",details={},**value)


def test_nonboolean_or_failed_transport_never_claims_append_success():
    fake=Rpc(result={"event_id":8})
    client=SupabaseCheckpointStore("https://example.supabase.co","SECRET_DO_NOT_LOG",session=fake)
    with pytest.raises(DurableStoreError):
        client.append_reconciliation(origin_event_key="orig",kind="CORRECTED",
            source_snapshot_ids=[1,2],details={})
    fake.status=503
    with pytest.raises(DurableStoreError) as exc:
        client.append_reconciliation(origin_event_key="orig",kind="CORRECTED",
            source_snapshot_ids=[1,2],details={})
    assert "SECRET_DO_NOT_LOG" not in str(exc.value)


def test_sql_rpc_checks_immutable_source_evidence_and_idempotency():
    assert SQL.lstrip().startswith("-- SmartXFlow Base Signals Part 4B2")
    assert "BEGIN;" in SQL and SQL.rstrip().endswith("COMMIT;")
    for phrase in (
        "SECURITY INVOKER", "CREATE OR REPLACE FUNCTION public.sxf_base_append_reconciliation",
        "v_origin.family<>'BASE'", "v_origin.kind<>'MARKET_DECISION'",
        "v_origin.kind<>'PRELIMINARY_SIGNAL'", "p_source_snapshot_ids",
        "s.id=ANY(p_source_snapshot_ids)", "s.fixture_uid=v_origin.fixture_uid",
        "s.market=v_origin.market", "count(DISTINCT s.scraped_at_utc)",
        "v_sides<>v_expected", "v_share NOT BETWEEN 99.5 AND 100.5",
        "v_observed NOT BETWEEN v_at - INTERVAL '30 minutes' AND v_at",
        "ON CONFLICT (event_key) DO NOTHING", "v_previous.details IS DISTINCT FROM v_details",
        "'origin_event_id'", "'source_snapshot_ids'", "'source_observed_at'",
        "GRANT EXECUTE ON FUNCTION public.sxf_base_append_reconciliation",
        "TO service_role"
    ):
        assert phrase in SQL
    assert "DELETE FROM public." not in SQL
    assert "UPDATE public.moneyway_snapshots" not in SQL
    assert "SECURITY DEFINER" not in SQL
    assert "FROM PUBLIC,anon,authenticated" in SQL
