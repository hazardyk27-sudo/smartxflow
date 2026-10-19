"""Hetzner one-shot probe uses real Base lifecycle with no write pathways."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from base_signal_engine.hetzner_probe import main, probe_fixture
from base_signal_engine.rules import Fixture, Quote, Snapshot

UID="74acc8bd-665e-488c-b1e7-32f95674ccdd"
KICKOFF=datetime(2026,10,19,17,tzinfo=timezone.utc)
FX=Fixture(UID,KICKOFF)


class ReadOnlyFixture:
    def __init__(self,snaps):
        self.snaps=tuple(snaps)
        self.calls=[]
    def load_fixture(self,uid):
        assert uid==UID
        self.calls.append("GET:fixtures")
        return FX,"e961dfd96a25"
    def load_checkpoints(self,fixture,*,hours,as_of_utc,
                         include_v2_history=True,expected_legacy_hash=""):
        assert fixture==FX and expected_legacy_hash=="e961dfd96a25"
        assert as_of_utc==KICKOFF-timedelta(hours=min(hours))+timedelta(minutes=10)
        assert include_v2_history
        self.calls.append("GET:moneyway_snapshots")
        valid=tuple(s for s in self.snaps if s.observed_at<=as_of_utc)
        return SimpleNamespace(snapshots=valid,fetched_rows=3*len(valid),
                               discarded_groups=0,hash_drift_rows=0)


def market(hour=6):
    at=KICKOFF-timedelta(hours=hour,minutes=5)
    return Snapshot("1X2",at,{
        "1":Quote("3.15","71.62","32.60"),
        "X":Quote("3.40","49.34","22.50"),
        "2":Quote("2.56","98.80","44.90")})


def test_one_uid_probe_never_writes_and_proves_t6_authority():
    fake=ReadOnlyFixture([market(8),market(6)])
    report=probe_fixture(fake,UID,checkpoint=6,
                         now=KICKOFF-timedelta(hours=5,minutes=45))
    assert fake.calls==["GET:fixtures","GET:moneyway_snapshots"]
    assert report["operation"]=="SINGLE_FIXTURE_READ_ONLY_PROBE"
    assert report["markets"]["1X2"]=="AUTHORITATIVE_T6"
    assert report["coverage"]=="PARTIAL"
    assert report["requires_reconciliation"]
    assert report["signal_count"]==0
    assert report["writes_performed"] is False
    assert report["production_approved"] is False


def test_empty_historical_source_is_explicit_waiting_data():
    report=probe_fixture(ReadOnlyFixture([]),UID,now=KICKOFF)
    assert report["status"]=="WAITING_DATA"
    assert report["source_rows"]==0 and report["signal_count"]==0
    assert report["writes_performed"] is False


def test_probe_rejects_premature_and_ambiguous_fixture_identity():
    with pytest.raises(ValueError,match="not yet due"):
        probe_fixture(ReadOnlyFixture([market(6)]),UID,
                      now=KICKOFF-timedelta(hours=7))
    with pytest.raises(ValueError):
        probe_fixture(ReadOnlyFixture([market(6)]),UID,checkpoint=5)
    with pytest.raises(ValueError):
        probe_fixture(ReadOnlyFixture([]),"invalid-uid")


def test_cli_refuses_execution_without_explicit_one_shot_approval(monkeypatch):
    monkeypatch.delenv("SXF_BASE_SINGLE_PROBE_APPROVED",raising=False)
    with pytest.raises(SystemExit,match="2"):
        main(["--fixture-uid",UID])


def test_service_is_one_shot_not_enabled_or_inserted_into_default_deploy():
    root=Path(__file__).resolve().parents[1]
    service=(root/"deploy/systemd/smartxflow-base-probe@.service").read_text()
    sync=(root/"deploy/sync_runtime_units.sh").read_text()
    assert "Type=oneshot" in service
    assert "Restart=no" in service
    assert "NoNewPrivileges=yes" in service
    assert "ProtectSystem=strict" in service
    assert "User=smartxflow" in service
    assert "EnvironmentFile=-/etc/smartxflow/base-probe.env" in service
    assert "SXF_BASE_SINGLE_PROBE_APPROVED=yes" not in service
    assert "[Install]" not in service
    assert "smartxflow-base-probe" not in sync
