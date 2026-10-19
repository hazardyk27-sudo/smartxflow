"""Pre-shadow must never claim full source capture or write to SQL."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from base_signal_engine import pre_shadow


class FakeReader:
    def __init__(self,rows):
        self.rows=rows
        self.calls=[]
    def _get(self,table,params):
        self.calls.append((table,params))
        return self.rows


class FakeStore:
    def __init__(self, health=None):
        self.health=health if health is not None else {
            "checkpoint_queue":{"pending_due":2,"waiting_data":1,
                                "expired_leases":0},
            "reconciliation_queue":{"pending_due":0,"waiting_data":0,
                                    "expired_leases":0}}
        self.calls=0
    def health_snapshot(self):
        self.calls+=1
        return self.health


class FakeJournal:
    def __init__(self):
        self.calls=[]
    def append(self,*,recorded_at,counters,error_code):
        self.calls.append((recorded_at,counters,error_code))
        return len(self.calls)


def test_observer_reads_health_and_latest_snapshot_only():
    at=datetime(2026,10,19,20,0,tzinfo=timezone.utc)
    reader=FakeReader([{"scraped_at_utc":"2026-10-19T19:55:00+00:00",
                        "id":100}])
    store=FakeStore()
    journal=FakeJournal()
    report=pre_shadow.observe_once(reader,store,journal,now=at)
    assert store.calls==1 and len(reader.calls)==1
    assert reader.calls[0][0]=="moneyway_snapshots"
    assert reader.calls[0][1]==[
        ("select","scraped_at_utc,id"),
        ("order","scraped_at_utc.desc,id.desc"),("limit","1")]
    assert report["source_snapshot_age_seconds"]==300
    assert report["checkpoint_pending_due"]==2
    assert report["db_writes_performed"] is False
    assert report["real_24h_verified"] is False
    assert report["source_commit_watermark"] is None
    assert journal.calls[0][2]=="SOURCE_CAPTURE_UNVERIFIED"
    assert "source_pending_due" not in journal.calls[0][1]


def test_pre_shadow_invalid_health_never_writes_evidence():
    reader=FakeReader([{"scraped_at_utc":"2026-10-19T19:55:00+00:00"}])
    journal=FakeJournal()
    bad=FakeStore({"checkpoint_queue":{"pending_due":None},
                   "reconciliation_queue":{}})
    with pytest.raises(ValueError,match="health counter"):
        pre_shadow.observe_once(reader,bad,journal,
            now=datetime(2026,10,19,20,0,tzinfo=timezone.utc))
    assert journal.calls==[] and reader.calls==[]


def test_pre_shadow_rejects_missing_and_future_snapshot_without_fake_freshness():
    at=datetime(2026,10,19,20,0,tzinfo=timezone.utc)
    for rows in ([], [{"scraped_at_utc":"2026-10-19T20:20:00+00:00"}]):
        reader=FakeReader(rows)
        journal=FakeJournal()
        with pytest.raises(ValueError):
            pre_shadow.observe_once(reader,FakeStore(),journal,now=at)
        assert journal.calls==[]


def test_cli_refuses_without_server_only_opt_in(monkeypatch):
    monkeypatch.delenv("SXF_BASE_READ_ONLY_OBSERVATION_APPROVED",raising=False)
    with pytest.raises(SystemExit,match="2"):
        pre_shadow.main(["--journal","/tmp/never-created.jsonl",
                         "--run-id","74acc8bd-665e-488c-b1e7-32f95674ccdd",
                         "--once"])


def test_shadow_24h_release_gates_reject_missing_source_capture(tmp_path):
    from base_signal_engine.shadow_evidence import ShadowEvidenceJournal,assess_shadow
    from datetime import timedelta
    journal=ShadowEvidenceJournal(tmp_path/"pre.jsonl",
        run_id="74acc8bd-665e-488c-b1e7-32f95674ccdd",
        mode="OPERATOR_READ_ONLY")
    store=FakeStore()
    reader=FakeReader([{"scraped_at_utc":"2026-10-19T19:55:00+00:00"}])
    start=datetime(2026,10,19,20,0,tzinfo=timezone.utc)
    for i in range(2):
        pre_shadow.observe_once(reader,store,journal,
            now=start+timedelta(minutes=i*2))
    report=assess_shadow(journal.read(),min_duration_hours=1)
    assert not report["meets_observation_gates"]
    assert "MISSING_HEALTH_METRICS" in report["blockers"]
    assert "ERROR_DURING_SHADOW" in report["blockers"]
    assert report["production_approved"] is False
