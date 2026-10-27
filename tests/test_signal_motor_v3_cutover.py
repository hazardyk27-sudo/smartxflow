"""Prospective V3 switch: older events remain immutable and cannot be reprocessed.

These checks are source contracts; production migration is operator-controlled.
"""
from pathlib import Path

from base_signal_engine.scheduler import RULESET_VERSION

ROOT = Path(__file__).resolve().parents[1]
V2 = "SXF_SIGNAL_MOTOR_V2_2026_10_22"
V3 = "SXF_SIGNAL_MOTOR_V3_2026_10_24"


def test_v3_new_jobs_have_separate_identity():
    assert RULESET_VERSION == V3
    sql = (ROOT / "migrations/2026_10_24_signal_motor_v3_versioned_cutover.sql").read_text()
    assert f"v_ruleset NOT IN ('SXF_BASE_V1_2026_10_18', '{V2}', '{V3}')" in sql
    assert f"AND j.ruleset_version='{V3}'" in sql
    assert f"WHERE j.ruleset_version='{V3}'" in sql
    assert "SXF_BASE_V1_2026_10_18" in sql
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert sql.strip().endswith("COMMIT;")


def test_in_flight_v2_skips_preserved_and_v2_reconcile_not_claimed_by_v3():
    sql = (ROOT / "migrations/2026_10_24_signal_motor_v3_versioned_cutover.sql").read_text()
    assert f"j.ruleset_version IN ('{V2}', '{V3}')" in sql
    assert f"e.ruleset_version='{V3}'" in sql
    assert "CREATE OR REPLACE FUNCTION public.sxf_base_claim_reconcile" in sql


def test_v3_cutover_never_rewrites_existing_events_or_jobs():
    sql = (ROOT / "migrations/2026_10_24_signal_motor_v3_versioned_cutover.sql").read_text().upper()
    for forbidden in ("DELETE FROM PUBLIC.SXF_BASE_", "TRUNCATE ", "DROP TABLE",
                      "UPDATE PUBLIC.SXF_BASE_SIGNAL_EVENTS", "DISABLE TRIGGER"):
        assert forbidden not in sql


def test_retired_ruleset_events_remain_auditable_but_are_never_served():
    source = (ROOT / "base_signal_engine/feed.py").read_text()
    assert "LEGACY_RULESET_VERSION" not in source
    assert '("ruleset_version", "eq." + RULESET_VERSION)' in source
    assert 'if row.get("ruleset_version") != RULESET_VERSION:' in source
    assert '"ruleset_status": "CURRENT"' in source
    assert '"ruleset_mode":"CURRENT"' in source
    assert "archive: bool = False" not in source
    assert 'and (uid, market, kickoff,' in source
    assert 'history = retention.get((uid, kickoff, selection, source_h,' in source


def test_v3_health_ignores_historical_backlog_without_erasing_it():
    sql = (ROOT / "migrations/2026_10_24_signal_motor_v3_health_scope.sql").read_text()
    assert f"WHERE ruleset_version='{V3}'" in sql
    assert f"WHERE e.ruleset_version='{V3}'" in sql
    assert "'historical_pending_due'" in sql
    assert "CREATE OR REPLACE FUNCTION public.sxf_base_health_snapshot" in sql
    assert "DELETE FROM" not in sql.upper()
    assert "UPDATE public.sxf_base_checkpoint_jobs" not in sql
