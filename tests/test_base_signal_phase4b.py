"""Synthetic Part4B source coverage, retry and identity tests (no DB writes)."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from base_signal_engine.rules import Fixture, Quote, Snapshot
from base_signal_engine.scheduler import CheckpointJob, FixtureRef
from base_signal_engine.storage import ClaimedCheckpoint, DurableStoreError, SupabaseCheckpointStore
from base_signal_engine.source_quality import source_coverage
from base_signal_engine.durable_runtime import execute_claims

KO = datetime(2026, 10, 20, 18, tzinfo=timezone.utc)
UID = "ef5c99bf-e002-451b-b401-af9174ad53f0"
REF = FixtureRef(UID, KO)
JOB6 = CheckpointJob(REF, 6, "BASE")


def snap(market, hour, strong=True):
    if market == "1X2":
        q = {"1": Quote("1.75", "1800" if strong else "5", "82"),
             "X": Quote("3.7", "100", "8"), "2": Quote("4.2", "50", "10")}
    elif market == "OU25":
        q = {"O": Quote("1.75", "3000", "80"),
             "U": Quote("2.25", "400", "20")}
    else:
        q = {"Y": Quote("1.75", "950", "70"),
             "N": Quote("2.1", "400", "30")}
    return Snapshot(market, KO-timedelta(hours=hour, minutes=5), q)


class Reader:
    def __init__(self, snapshots):
        self.snapshots = snapshots
    def load_fixture(self, uid):
        assert uid == UID
        return Fixture(uid, KO), "legacy-hash"
    def load_checkpoints(self, fixture, *, hours, as_of_utc, include_v2_history, expected_legacy_hash):
        return SimpleNamespace(
            snapshots=tuple(s for s in self.snapshots if s.observed_at <= as_of_utc),
            fetched_rows=len(self.snapshots)*3, discarded_groups=0, hash_drift_rows=0)


class Response:
    def __init__(self, payload, status=200):
        self.status_code, self.payload = status, payload
    def json(self): return self.payload


class Rpc:
    def __init__(self, job=JOB6, results=None, statuses=None):
        self.calls = []
        self.results = {"sxf_base_claim_due_jobs": [dict(
            job_id=str(uuid4()), lease_token=str(uuid4()), job_key=job.key,
            ruleset_version="SXF_BASE_V1_2026_10_18",
            fixture_uid=UID,kickoff_utc=KO.isoformat(),checkpoint_hours=job.hours,
            family=job.family,checkpoint_at=job.timestamp.isoformat(),attempt_count=1)],
            "sxf_base_wait_for_data": True, "sxf_base_renew_lease": True,
            "sxf_base_complete_job": True, "sxf_base_fail_job": True}
        self.results.update(results or {})
        self.statuses = statuses or {}
    def post(self, url, *, json, headers, timeout):
        op = url.rsplit("/", 1)[-1]
        self.calls.append((op,json))
        return Response(self.results[op], self.statuses.get(op, 200))


def store(rpc):
    return SupabaseCheckpointStore("https://example.supabase.co","UNPRINTABLE_SECRET",session=rpc)


def test_t6_source_coverage_is_market_independent_and_no_fallback_when_t6_valid():
    reader=Reader([snap("1X2",6,strong=False),snap("1X2",8),
                   snap("OU25",8)])
    from base_signal_engine.source_quality import CapturingReader
    from base_signal_engine.scheduler import evaluate_job
    captured=CapturingReader(reader)
    payload=evaluate_job(JOB6,captured)
    state=source_coverage(JOB6,captured.source,payload)
    assert state["disposition"]=="EVALUATE"
    assert state["state"]=="PARTIAL"
    assert state["markets"]["1X2"]["authority"]=="T6"
    assert state["markets"]["OU25"]["authority"]=="T8_FALLBACK"
    assert state["markets"]["BTTS"]["authority"]=="MISSING"
    assert state["missing_t6_markets"]==["OU25","BTTS"]
    assert not any(s["engine"]=="1X2_CONCENTRATION_V1" for s in payload["signals"])


def test_t8_has_no_future_t6_inspection():
    from base_signal_engine.source_quality import CapturingReader
    from base_signal_engine.scheduler import evaluate_job
    job=CheckpointJob(REF,8,"BASE")
    captured=CapturingReader(Reader([snap("1X2",8),snap("1X2",6)]))
    payload=evaluate_job(job,captured)
    state=source_coverage(job,captured.source,payload)
    assert state["markets"]["1X2"]["authority"]=="T8_PRELIMINARY"
    assert state["markets"]["OU25"]["authority"]=="MISSING"
    assert state["disposition"]=="EVALUATE"


def test_empty_base_sources_wait_and_never_complete():
    rpc=Rpc()
    metrics=execute_claims(Reader([]),store(rpc),worker_id="worker")
    assert metrics["waiting_data"]==1 and metrics["completed"]==0
    assert [name for name,_ in rpc.calls]==[
        "sxf_base_claim_due_jobs","sxf_base_wait_for_data"]
    assert rpc.calls[1][1]["p_reason"]=="SOURCE_INCOMPLETE"


def test_partial_base_source_commits_evidence_and_reports_reconciliation_need():
    rpc=Rpc()
    metrics=execute_claims(Reader([snap("1X2",6),snap("OU25",8)]),store(rpc),worker_id="worker")
    assert metrics["completed"]==1 and metrics["waiting_data"]==0
    assert [name for name,_ in rpc.calls]==[
        "sxf_base_claim_due_jobs","sxf_base_renew_lease","sxf_base_complete_job"]
    p=rpc.calls[-1][1]["p_payload"]
    assert p["source_coverage"]["requires_reconciliation"]
    assert p["source_coverage"]["missing_markets"]==["BTTS"]
    assert p["markets"]["1X2"]["state"]=="AUTHORITATIVE_T6"


def test_early_t12_missing_source_waits_but_complete_no_hit_is_final():
    job=CheckpointJob(REF,12,"EARLY_T12")
    rpc=Rpc(job=job)
    assert execute_claims(Reader([]),store(rpc),worker_id="w")["waiting_data"]==1
    rpc=Rpc(job=job)
    answer=execute_claims(Reader([snap("1X2",12,strong=False)]),store(rpc),worker_id="w")
    assert answer["completed"]==1
    assert rpc.calls[-1][1]["p_payload"]["status"]=="NO_SIGNAL"


def test_early_core_requires_proven_earlier_checkpoints_for_first_hit():
    from base_signal_engine.source_quality import CapturingReader
    from base_signal_engine.scheduler import evaluate_job
    job=CheckpointJob(REF,60,"EARLY_CORE")
    captured=CapturingReader(Reader([snap("1X2",60)]))
    payload=evaluate_job(job,captured)
    quality=source_coverage(job,captured.source,payload)
    assert quality["missing_1x2_checkpoints"]==[72]
    assert quality["disposition"]=="WAITING_DATA"
    captured=CapturingReader(Reader([snap("1X2",72),snap("1X2",60)]))
    payload=evaluate_job(job,captured)
    assert source_coverage(job,captured.source,payload)["disposition"]=="EVALUATE"


def test_wait_rpc_rejects_invalid_params_and_redacts_secrets():
    rpc=Rpc()
    s=store(rpc)
    claim=s.claim("worker")[0]
    s.wait_for_data(claim,reason="SOURCE_LAG",delay_seconds=600)
    assert rpc.calls[-1][1]["p_lease_token"]==claim.lease_token
    for kwargs in ({"reason":"SECRET token"}, {"delay_seconds":2}):
        with pytest.raises(ValueError):
            s.wait_for_data(claim,**kwargs)
    rpc.statuses["sxf_base_wait_for_data"]=503
    with pytest.raises(DurableStoreError) as e:
        s.wait_for_data(claim)
    assert "UNPRINTABLE_SECRET" not in str(e.value)


def test_complete_response_timeout_is_uncertain_not_a_fake_retry():
    rpc=Rpc(statuses={"sxf_base_complete_job":503})
    report=execute_claims(Reader([snap("1X2",6)]),store(rpc),worker_id="w")
    assert report["commit_uncertain"]==1 and report["completed"]==0
    assert report["retry"]==0 and report["lease_lost"]==0
    assert not any(n=="sxf_base_fail_job" for n,_ in rpc.calls)


def test_guard_multiple_unstarted_claims_without_heartbeat():
    rpc=Rpc()
    with pytest.raises(ValueError,match="claim batch"):
        execute_claims(Reader([]),store(rpc),worker_id="w",limit=2)
    assert not rpc.calls


def test_wrong_fixture_uid_cannot_be_reconciled_by_hash():
    other=CheckpointJob(FixtureRef(str(uuid4()),KO),6,"BASE")
    quality=source_coverage(other,SimpleNamespace(snapshots=[snap("1X2",6)]),
                            {"markets":{"1X2":{"checkpoint":6},"OU25":{"checkpoint":None},
                                        "BTTS":{"checkpoint":None}}})
    assert quality["state"]=="PARTIAL"  # never derive fixture identity from legacy hash
