"""Part5C1 explicit read-only shadow metric adapter; offline fake sources."""
from datetime import datetime,timezone
from uuid import uuid4
from types import SimpleNamespace

from base_signal_engine.shadow_observer import record_shadow_once
from base_signal_engine.shadow_evidence import ShadowEvidenceJournal

AT=datetime(2026,10,19,10,tzinfo=timezone.utc)


class FakeCatalog:
    def list_between(self,a,b):
        return []


class FakeHealth:
    def __init__(self,fail=False,missing=False):
        self.fail=fail
        self.missing=missing
    def health_snapshot(self):
        if self.fail: raise RuntimeError("health transport")
        return {
            "checkpoint_queue":{"pending_due":0,"waiting_data":0,
                                "expired_leases":0},
            "reconciliation_queue":{"pending_due":0,"waiting_data":0,
                                    "expired_leases":0}}
    def source_health(self):
        return {"source_commit_watermark":None,
                "captured_at_semantics":"TRIGGER_TIME_NOT_COMMIT_TIME",
                "source_delivery":{"pending_due":0,"review_required":0}
                    if self.missing else
                    {"pending_due":0,"review_required":0,"expired_leases":0}}


class FakeCheckpointJournal:
    def has_completed(self,key): return True
    def commit(self,key,payload): raise AssertionError("unexpected job")


def observe(tmp_path,health):
    evidence=ShadowEvidenceJournal(tmp_path/"cycles.jsonl",run_id=str(uuid4()),
                                   mode="SYNTHETIC")
    result=record_shadow_once(object(),FakeCheckpointJournal(),health,evidence,
                              now=AT,catalog=FakeCatalog())
    return result,evidence


def test_fully_populated_health_does_not_need_network_or_creds(tmp_path):
    result,evidence=observe(tmp_path,FakeHealth())
    assert result["success"] and result["error_code"] is None
    assert result["real_24h_verified"] is False
    counters=evidence.read()[0]["counters"]
    assert counters["checkpoint_pending_due"]==0
    assert counters["source_expired_leases"]==0
    assert counters["uncertain_commits"]==0
    assert counters["due"]==0


def test_health_unavailable_is_a_failed_observation_not_zero(tmp_path):
    result,evidence=observe(tmp_path,FakeHealth(fail=True))
    assert not result["success"] and result["error_code"]=="RUNTIMEERROR"
    assert evidence.read()[0]["counters"]=={"failed":1}


def test_partial_source_health_is_missing_not_empty_queue(tmp_path):
    result,evidence=observe(tmp_path,FakeHealth(missing=True))
    assert not result["success"]
    assert evidence.read()[0]["counters"]=={"failed":1}
