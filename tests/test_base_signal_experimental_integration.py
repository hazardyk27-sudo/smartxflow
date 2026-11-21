"""Prospective worker/feed contract, fully offline and disabled by default."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from pathlib import Path

from base_signal_engine.rules import Fixture, Quote, Snapshot
from base_signal_engine.scheduler import CheckpointJob, FixtureRef, evaluate_job
from base_signal_engine.experimental_engines import EXPERIMENTAL_RULESET

KO = datetime(2026, 11, 22, 20, tzinfo=timezone.utc)
UID = "e9048215-4653-4c68-aa51-5332758c76ec"
FX = Fixture(UID, KO)
JOB = CheckpointJob(FixtureRef(UID, KO), 6, "BASE")


def rows():
    def snap(market, h, quotes):
        return Snapshot(market, KO-timedelta(hours=h, minutes=3),
                        {k: Quote(*v) for k, v in quotes.items()})
    history = [
        snap("1X2", 8, {"1": ("1.75", "1600", "80"), "X": ("3.50", "200", "10"), "2": ("4.20", "200", "10")}),
        snap("1X2", 7, {"1": ("1.75", "1960", "81.66666666666667"), "X": ("3.50", "220", "9.16666666666667"), "2": ("4.20", "220", "9.16666666666667")}),
        snap("1X2", 6, {"1": ("1.70", "2320", "82.85714285714286"), "X": ("3.50", "240", "8.57142857142857"), "2": ("4.20", "240", "8.57142857142857")}),
        snap("OU25", 8, {"O": ("1.60", "3000", "84"), "U": ("2.40", "100", "16")}),
        snap("OU25", 6, {"O": ("1.60", "3800", "83"), "U": ("2.40", "100", "17")}),
        snap("BTTS", 6, {"Y": ("1.78", "1900", "70"), "N": ("2.20", "500", "30")}),
    ]
    return tuple(history)


class Reader:
    def __init__(self, data):
        self.data = data

    def load_fixture(self, fixture_uid):
        assert fixture_uid == UID
        return FX, ""

    def load_checkpoints(self, fixture, *, hours, as_of_utc,
                         include_v2_history=True, expected_legacy_hash=""):
        assert hours == (8, 6) and as_of_utc == KO-timedelta(hours=6)+timedelta(minutes=10)
        return SimpleNamespace(snapshots=tuple(s for s in self.data if s.observed_at <= as_of_utc),
                               fetched_rows=18, discarded_groups=0, hash_drift_rows=0)


def test_experiments_disabled_by_default(monkeypatch):
    monkeypatch.delenv("SXF_EXPERIMENTAL_ENGINES", raising=False)
    monkeypatch.delenv("SXF_EXPERIMENTAL_ACTIVATED_AT_UTC", raising=False)
    payload = evaluate_job(JOB, Reader(rows()))
    engines = {s["engine"] for s in payload["signals"]}
    assert "EKOL_3" not in engines and "OVER_STRONG" not in engines
    assert {"1X2_CONCENTRATION_V1", "STABLE_OVER_2_5", "PREMIUM_OVER_2_5"} <= engines


def test_future_t6_emit_both_tags_and_preserve_core(monkeypatch):
    monkeypatch.setenv("SXF_EXPERIMENTAL_ENGINES", "1")
    monkeypatch.setenv("SXF_EXPERIMENTAL_ACTIVATED_AT_UTC", "2026-11-22T00:00:00Z")
    payload = evaluate_job(JOB, Reader(rows()))
    engines = {s["engine"] for s in payload["signals"]}
    assert {"EKOL_3", "OVER_STRONG", "1X2_CONCENTRATION_V1",
            "PREMIUM_OVER_2_5", "STABLE_OVER_2_5"} <= engines
    assert payload["experimental_ruleset_version"] == EXPERIMENTAL_RULESET
    assert payload["experimental_states"] == {"EKOL_3": "PASS", "OVER_STRONG": "PASS"}
    assert all(s["checkpoint"] == 6 for s in payload["signals"] if s["engine"] in ("EKOL_3", "OVER_STRONG"))


def test_historical_t6_not_relabelled_after_activation(monkeypatch):
    monkeypatch.setenv("SXF_EXPERIMENTAL_ENGINES", "1")
    monkeypatch.setenv("SXF_EXPERIMENTAL_ACTIVATED_AT_UTC", "2026-11-23T00:00:00Z")
    payload = evaluate_job(JOB, Reader(rows()))
    assert not any(s["engine"] in ("EKOL_3", "OVER_STRONG") for s in payload["signals"])


def test_registry_sql_is_t6_fenced_and_same_payload_revision():
    sql = Path("migrations/2026_11_21_experimental_signal_registry.sql").read_text()
    assert "'EKOL_3'" in sql and "'OVER_STRONG'" in sql
    assert "j.checkpoint_hours <> 6" in sql
    assert "s->>'experimental_ruleset'" in sql
    assert "p_payload->>'experimental_ruleset_version'" in sql
    assert "s->>'label' IS DISTINCT FROM 'EXPERIMENTAL'" in sql
