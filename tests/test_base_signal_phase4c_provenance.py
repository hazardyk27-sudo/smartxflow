"""Read-only T6 provenance and conservative correction planning tests."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from base_signal_engine.reconciliation import plan_late_t6
from base_signal_engine.rules import Fixture, Quote, Snapshot

UID="ef5c99bf-e002-451b-b401-af9174ad53f0"
KO=datetime(2026,10,20,18,tzinfo=timezone.utc)


def snapshot(market, hour, *, volume=2000):
    if market=="1X2":
        q={"1":Quote("1.75",volume,80),"X":Quote("3.20",100,10),"2":Quote("4.50",100,10)}
    elif market=="OU25":
        q={"O":Quote("1.75",volume,80),"U":Quote("2.10",100,20)}
    else:
        q={"Y":Quote("1.75",volume,70),"N":Quote("2.10",100,30)}
    return Snapshot(market,KO-timedelta(hours=hour,minutes=5),q)


class FakeReader:
    def __init__(self, snapshots=(), *, provenance=True, mismatch=False):
        self.snaps=tuple(snapshots)
        self.provenance=provenance
        self.mismatch=mismatch
        self.calls=[]
    def load_fixture(self, uid):
        return Fixture(str(uuid4()) if self.mismatch else uid, KO), "old-hash"
    def load_checkpoints(self, fixture, *, hours, as_of_utc, include_v2_history, expected_legacy_hash):
        self.calls.append((hours,as_of_utc,include_v2_history,expected_legacy_hash))
        entries=tuple(s for s in self.snaps if s.observed_at<=as_of_utc)
        ids={(s.market,s.observed_at):tuple(range(1,4) if s.market=="1X2" else range(4,6)) for s in entries}
        return SimpleNamespace(snapshots=entries,source_row_ids=ids if self.provenance else {})


def plan(reader,market="1X2"):
    return plan_late_t6(reader,origin_event_key="origin",fixture_uid=UID,
                        kickoff_utc=KO,market=market)


def test_late_t6_requires_complete_snapshot_and_explicit_source_ids():
    assert plan(FakeReader()) is None
    s=snapshot("1X2",6)
    r=FakeReader([s])
    p=plan(r)
    assert p is not None and p.source_snapshot_ids==(1,2,3)
    assert p.fixture_uid==UID and p.source_observed_at==s.observed_at
    assert {x["engine"] for x in p.signals}>={"1X2_CONCENTRATION_V1"}
    assert r.calls[0][0]==(6,)
    assert r.calls[0][1]==KO-timedelta(hours=6)+timedelta(minutes=10)
    with pytest.raises(ValueError,match="source row IDs"):
        plan(FakeReader([s],provenance=False))


def test_frozen_motor_rule_no_hit_never_fabricates_replacement():
    p=plan(FakeReader([snapshot("1X2",6,volume=100)]))
    assert p is not None and p.signals==()


def test_market_independent_and_no_future_lookahead():
    r=FakeReader([snapshot("OU25",6),snapshot("1X2",6),
                  snapshot("1X2",5)])
    p=plan(r,"OU25")
    assert len(p.source_snapshot_ids)==2
    assert p.signals[0]["engine"]=="STABLE_OVER_2_5"
    assert all(datetime.fromisoformat(x["observed_at"])<=KO-timedelta(hours=6)
               for x in p.signals)
    assert not any(x["engine"].startswith("1X2") for x in p.signals)


def test_wrong_uid_and_identity_conflict_fail_closed():
    with pytest.raises(ValueError,match="fixture identity changed"):
        plan(FakeReader([snapshot("1X2",6)],mismatch=True))
    with pytest.raises(ValueError):
        plan_late_t6(FakeReader(),origin_event_key="orig",fixture_uid="bad-uid",
                     kickoff_utc=KO,market="1X2")
