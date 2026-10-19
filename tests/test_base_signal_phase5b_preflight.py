"""Part5B EXPLAIN diagnostics and health payload safety."""
from pathlib import Path

import pytest

from base_signal_engine.performance_preflight import snapshot_index_evidence
from base_signal_engine.storage import DurableStoreError, SupabaseCheckpointStore


def plan(node):
    return [{"Plan":node}]


def test_expected_index_is_reported_only_when_actual_plan_uses_it():
    good=plan({"Node Type":"Limit","Plans":[
        {"Node Type":"Index Scan","Index Name":"idx_sxf_base_mw_snapshot_uid_time"}]})
    r=snapshot_index_evidence(good)
    assert r["expected_index_used"] and r["result"]=="PROPOSED_INDEX_USED"
    assert not r["production_plan_verified"]
    fallback=plan({"Node Type":"Seq Scan","Relation Name":"moneyway_snapshots"})
    out=snapshot_index_evidence(fallback)
    assert not out["expected_index_used"] and out["seq_scan_present"]
    assert out["result"]=="INDEX_USAGE_NOT_CONFIRMED"


def test_other_index_never_passes_proposed_composite_index_gate():
    r=snapshot_index_evidence(plan({"Node Type":"Index Scan",
                                   "Index Name":"moneyway_snapshots_pkey"}))
    assert r["other_index_used"] and not r["expected_index_used"]


def test_malformed_plan_is_not_accepted():
    for bad in (None,{},[],[{}],[{"Plan":{"Plans":[42],"Node Type":"Limit"}}]):
        with pytest.raises(ValueError):
            snapshot_index_evidence(bad)


class Session:
    def __init__(self, value): self.value=value
    def post(self,url,*,json,headers,timeout):
        return type("R",(),{"status_code":200,"json":lambda _x:self.value})()


def test_source_health_explicitly_labels_captured_not_commit_timestamp():
    valid={"captured_at_semantics":"TRIGGER_TIME_NOT_COMMIT_TIME",
           "source_commit_watermark":None,"source_delivery":{"total":5},
           "event_kinds":{"SNAPSHOT_INSERT":2}}
    store=SupabaseCheckpointStore("https://example.supabase.co","server-token",
                                 session=Session(valid))
    assert store.source_health()["source_commit_watermark"] is None
    for fake in (
        {**valid,"source_commit_watermark":"invented-time"},
        {**valid,"captured_at_semantics":"COMMIT_TIME"},
        {"source_delivery":{"total":5}}):
        with pytest.raises(DurableStoreError):
            SupabaseCheckpointStore("https://example.supabase.co","server-token",
                                    session=Session(fake)).source_health()


def test_proposed_index_remains_independent_from_transactional_migrations():
    root=Path(__file__).resolve().parents[1]
    text=(root/"migrations/2026_10_18_sxf_base_snapshot_index_APPROVAL_REQUIRED.sql").read_text()
    assert "CREATE INDEX CONCURRENTLY" in text
    assert "(fixture_uid, scraped_at_utc, id)" in text
    assert "BEGIN;" not in text
    sql=(root/"migrations/2026_10_19_sxf_base_phase5b_source_health.sql").read_text()
    assert "SECURITY INVOKER" in sql
    assert "source_commit_watermark',NULL" in sql
    assert "FROM PUBLIC,anon,authenticated" in sql
