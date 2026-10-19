"""Checkpoint scheduler and shadow storage tests; synthetic immutable snapshots."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import json

import pytest

from base_signal_engine.rules import Fixture, Quote, Snapshot
from base_signal_engine.scheduler import (
    FixtureRef, due_jobs, evaluate_job, process_due_jobs, CheckpointJob,
    CHECKPOINT_TASKS, RULESET_VERSION,
)
from base_signal_engine.journal import CheckpointJsonlJournal, JournalCorruptError
from base_signal_engine.runtime import SupabaseFixtureCatalog, CatalogReadError, scan_once

KO = datetime(2026, 10, 19, 20, 0, tzinfo=timezone.utc)
UID = "ef5c99bf-e002-451b-b401-af9174ad53f0"
REF = FixtureRef(UID, KO, "legacy")
FX = Fixture(UID, KO)


def mkt(market, hour, *, strong=2000, share=85, odd="1.70"):
    if market == "1X2":
        q = {"1": Quote(odd, strong, str(share)), "X": Quote("3.50", "250", "10"),
             "2": Quote("4.20", "200", str(90-share))}
    elif market == "OU25":
        q = {"O": Quote("1.75", "3500", "80"), "U": Quote("2.10", "600", "20")}
    else:
        q = {"Y": Quote("1.75", "900", "65"), "N": Quote("2.10", "500", "35")}
    return Snapshot(market, KO-timedelta(hours=hour,minutes=5), q)


class MemoryJournal:
    def __init__(self):
        self.logs = {}
    def has_completed(self, key):
        return key in self.logs
    def commit(self, key, payload):
        if key in self.logs:
            return False
        self.logs[key] = payload
        return True


class FakeReader:
    def __init__(self, snapshots, fail=False):
        self.snaps = snapshots
        self.calls = []
        self.fail = fail
    def load_fixture(self, uid):
        assert uid == UID
        return FX, "legacy"
    def load_checkpoints(self, fixture, *, hours, as_of_utc, include_v2_history=True, expected_legacy_hash=""):
        self.calls.append((tuple(hours),as_of_utc,include_v2_history))
        if self.fail:
            raise RuntimeError("simulated transport outage")
        visible = [x for x in self.snaps if x.observed_at<=as_of_utc and any(
            fixture.kickoff_utc-timedelta(hours=h,minutes=30+(3*60 if include_v2_history and h in (8,6) else 0))
            <=x.observed_at<=fixture.kickoff_utc-timedelta(hours=h) for h in hours)]
        return SimpleNamespace(snapshots=tuple(visible),fetched_rows=len(visible)*3,
                               discarded_groups=0,hash_drift_rows=0)


def test_only_early_can_run_t5_t4_t3():
    assert not any(h in (5,4,3) and f=="BASE" for h,f in CHECKPOINT_TASKS)
    assert {(h,f) for h,f in CHECKPOINT_TASKS if h in (5,4,3)} == {
        (5,"EARLY_RETENTION"),(4,"EARLY_RETENTION"),(3,"EARLY_RETENTION")}


def test_jobs_are_due_after_grace_and_in_chronological_order():
    journal=MemoryJournal()
    early=due_jobs([REF],KO-timedelta(hours=60)+timedelta(minutes=9),journal)
    assert [x.hours for x in early]==[72]
    ontime=due_jobs([REF],KO-timedelta(hours=60)+timedelta(minutes=11),journal)
    assert [(x.hours,x.family) for x in ontime]==[(72,"EARLY_CORE"),(60,"EARLY_CORE")]
    assert len({x.key for x in ontime})==2


def test_jobs_recover_after_restart_without_duplicate_events(tmp_path):
    path=tmp_path/"events.jsonl"
    j=CheckpointJsonlJournal(path)
    due=due_jobs([REF],KO-timedelta(hours=8)+timedelta(minutes=11),j)
    assert any(x.hours==8 and x.family=="BASE" for x in due)
    item=next(x for x in due if x.hours==8 and x.family=="BASE")
    assert j.commit(item.key,{"key":item.key,"signals":[]})
    assert not j.commit(item.key,{"key":item.key,"signals":[]})
    recovered=CheckpointJsonlJournal(path)
    assert recovered.has_completed(item.key)
    assert item.key not in {x.key for x in due_jobs([REF],KO-timedelta(hours=7),recovered)}
    assert len(path.read_text().splitlines())==1


def test_journal_refuses_unterminated_crash_record(tmp_path):
    path=tmp_path/"events.jsonl";path.write_text('{"key":"half"')
    with pytest.raises(JournalCorruptError,match="unterminated"):
        CheckpointJsonlJournal(path)


def test_independent_market_t6_authority_vs_t8_fallback():
    history=[mkt("1X2",h) for h in (11,10,9,8,7,6)]
    history += [mkt("OU25",8),mkt("BTTS",8)]
    reader=FakeReader(history)
    job=CheckpointJob(REF,6,"BASE")
    p=evaluate_job(job,reader)
    assert p["markets"]["1X2"]["state"]=="AUTHORITATIVE_T6"
    assert p["markets"]["OU25"]["state"]=="FALLBACK_T8"
    assert p["markets"]["BTTS"]["state"]=="FALLBACK_T8"
    assert any(x["engine"]=="STABLE_OVER_2_5" and x["checkpoint"]==8 for x in p["signals"])
    assert any(x["engine"]=="1X2_CONCENTRATION_V1" and x["checkpoint"]==6 for x in p["signals"])
    assert reader.calls[0][1]==KO-timedelta(hours=6)+timedelta(minutes=10)


def test_t6_data_exists_but_fails_no_t8_rescue():
    reader=FakeReader([mkt("1X2",8),mkt("1X2",6,strong=100,share=85)])
    p=evaluate_job(CheckpointJob(REF,6,"BASE"),reader)
    assert p["markets"]["1X2"]["checkpoint"]==6
    assert p["markets"]["1X2"]["state"]=="AUTHORITATIVE_T6"
    assert not any(s["engine"]=="1X2_CONCENTRATION_V1" for s in p["signals"])


def test_preliminary_t8_does_not_inspect_t6_future_data():
    r=FakeReader([mkt("1X2",8),mkt("1X2",6,strong=999999)])
    p=evaluate_job(CheckpointJob(REF,8,"BASE"),r)
    assert p["markets"]["1X2"]["state"]=="PRELIMINARY_T8"
    assert all(int(s["checkpoint"])==8 for s in p["signals"])
    assert r.calls[0][1]<KO-timedelta(hours=6)


def test_early_core_t24_is_cohort_and_not_extra_independent_engine():
    r=FakeReader([mkt("1X2",24,strong=12000)])
    p=evaluate_job(CheckpointJob(REF,24,"EARLY_CORE"),r)
    assert p["t24_cohort"] is True
    assert p["signals"][0]["engine"]=="EARLY_MONEY_CORE"
    assert p["signals"][0]["checkpoint"]==24


def test_early_t12_is_independent():
    r=FakeReader([mkt("1X2",12,strong=2000)])
    p=evaluate_job(CheckpointJob(REF,12,"EARLY_T12"),r)
    assert p["signals"][0]["engine"]=="EARLY_MONEY_T12"


def test_early_retention_is_not_created_as_a_base_t5_signal():
    core=mkt("1X2",72,strong=12000)
    at5=mkt("1X2",5,strong=1100,share=54)
    at6=mkt("1X2",6,strong=1200)
    r=FakeReader([core,at5,at6])
    p=evaluate_job(CheckpointJob(REF,5,"EARLY_RETENTION"),r)
    assert p["family"]=="EARLY_RETENTION"
    assert p["retention"]["current_checkpoint_state"]=="RETENTION_BREAK"
    assert p["signals"]==[]


def test_retrieval_error_never_completes_checkpoint():
    j=MemoryJournal();r=FakeReader([],fail=True)
    stats=process_due_jobs([REF],KO-timedelta(hours=72)+timedelta(minutes=11),r,j)
    assert stats["failed"]==1 and stats["committed"]==0
    assert not j.logs and stats["errors"][0]["error_type"]=="RuntimeError"
    r.fail=False
    result=process_due_jobs([REF],KO-timedelta(hours=72)+timedelta(minutes=11),r,j)
    assert result["committed"]==1 and result["failed"]==0


def test_limited_backlog_drains_without_dropping_jobs():
    r=FakeReader([]);j=MemoryJournal()
    at=KO-timedelta(hours=3)+timedelta(minutes=11)
    for _ in range(len(CHECKPOINT_TASKS)):
        process_due_jobs([REF],at,r,j,limit=1)
    result=process_due_jobs([REF],at,r,j,limit=1)
    assert result["due"]==0
    assert len(j.logs)==len(CHECKPOINT_TASKS)


def test_fixture_catalog_fails_closed_when_paginated_missing_or_duplicate():
    class Session:
        def __init__(self,rows): self.rows=rows
        def _get(self,table,params):
            assert table=="fixtures"
            p=dict(params);offset=int(p["offset"]);length=int(p["limit"])
            return self.rows[offset:offset+length]
    rows=[{"fixture_uid":UID,"match_id_hash":"old","kickoff_utc":KO.isoformat()}]
    source=SupabaseFixtureCatalog(Session(rows),page_size=1,max_pages=2)
    assert source.list_between(KO-timedelta(hours=1),KO+timedelta(hours=1))[0].fixture_uid==UID
    with pytest.raises(CatalogReadError,match="duplicated"):
        SupabaseFixtureCatalog(Session(rows+rows),page_size=2).list_between(KO-timedelta(hours=1),KO+timedelta(hours=1))
    with pytest.raises(CatalogReadError,match="cap"):
        SupabaseFixtureCatalog(Session(rows+rows),page_size=1,max_pages=1).list_between(KO-timedelta(hours=1),KO+timedelta(hours=1))


def test_scan_once_never_writes_db_or_uses_infinite_batch():
    class Catalog:
        def list_between(self,start,end): return [REF]
    j=MemoryJournal();reader=FakeReader([])
    stats=scan_once(reader,j,now=KO-timedelta(hours=6)+timedelta(minutes=11),catalog=Catalog(),max_jobs=3)
    assert stats["due"]==3 and stats["committed"]==0 and stats["shadow_only"]
    assert stats["waiting_data"]==3 and stats["failed"]==0
    assert not j.logs  # No source != completed signal/history checkpoint.


def test_actual_shadow_retries_missing_t6_instead_of_marking_done():
    class Catalog:
        def list_between(self,start,end): return [REF]
    now=KO-timedelta(hours=5,minutes=49)
    empty=FakeReader([])
    journal=MemoryJournal()
    first=scan_once(empty,journal,now=now,catalog=Catalog(),max_jobs=9)
    assert first["due"]==8 and first["waiting_data"]==8 and first["committed"]==0
    assert journal.logs=={}
    # A later snapshot can be observed on next scan; immutable existing
    # checkpoint timestamps remain the same and motor rules are unchanged.
    history=[mkt("1X2",h) for h in (11,10,9,8,7,6)]
    history += [mkt("OU25",8),mkt("BTTS",8)]
    full=FakeReader(history)
    # Restrict one T6 checkpoint via an explicitly scoped fake completion port.
    job=CheckpointJob(REF,6,"BASE")
    source=full.load_checkpoints(FX,hours=(8,6),
                                 as_of_utc=KO-timedelta(hours=6)+timedelta(minutes=10))
    assert source.snapshots
    from base_signal_engine.source_quality import source_coverage
    from base_signal_engine.scheduler import evaluate_job
    payload=evaluate_job(job,full)
    assert source_coverage(job,source,payload)["disposition"]=="EVALUATE"
