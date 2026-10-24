"""2026-10-24 DB safety contract: no destructive drift or returned-kickoff recovery."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAST = ROOT / "migrations/2026_10_24_base_drift_quarantine_fastpath.sql"
RETURN = ROOT / "migrations/2026_10_24_base_returned_kickoff_reactivate.sql"
HASH = ROOT / "migrations/2026_10_24_base_drift_quarantine_hash_join.sql"


def test_quarantine_noop_fastpath_keeps_atomic_fencing_and_append_only_audit():
    sql = FAST.read_text()
    assert "IF NOT EXISTS (" in sql
    assert "RETURN 0;" in sql
    assert "FOR UPDATE OF j SKIP LOCKED" in sql
    assert "lease_expires_at <= now()" in sql
    assert "ON CONFLICT (event_key) DO NOTHING" in sql
    assert "INSERT INTO public.sxf_base_fixture_drift_events" in sql
    assert "SET statement_timeout TO '12s'" in sql
    assert "DROP TABLE" not in sql.upper()
    assert "TRUNCATE" not in sql.upper()
    assert "DELETE FROM" not in sql.upper()


def test_returning_kickoff_reactivation_is_fenced_and_preserves_history():
    sql = RETURN.read_text()
    assert "v_existing.state='SUPERSEDED'" in sql
    assert "v_ruleset='SXF_SIGNAL_MOTOR_V3_2026_10_24'" in sql
    assert "v_kick>now()" in sql
    assert "returning kickoff has immutable signal events" in sql
    assert "sxf_base_checkpoint_evaluations e" in sql
    assert "THEN 'COMPLETED' ELSE 'PENDING'" in sql
    assert "j.state='SUPERSEDED'" in sql
    assert "f.fixture_uid=v_uid AND f.kickoff_utc=v_kick" in sql
    assert "RAISE EXCEPTION 'returning kickoff reactivation uncertain'" in sql
    assert "UPDATE public.sxf_base_checkpoint_evaluations" not in sql
    assert "UPDATE public.sxf_base_signal_events" not in sql
    assert "DELETE FROM " not in sql.upper()
    assert "TRUNCATE " not in sql.upper()
    assert "DROP TABLE" not in sql.upper()


def test_hash_join_quarantine_noop_avoids_exists_limit_1_scan_and_preserves_fences():
    sql = HASH.read_text()
    prefix, _, fenced = sql.partition("    WITH locked AS (")
    assert "SELECT COUNT(*) INTO v_drift_candidates" in prefix
    assert "IF v_drift_candidates = 0 THEN" in prefix
    assert "IF NOT EXISTS (" not in prefix
    assert "JOIN public.fixtures f ON f.fixture_uid = j.fixture_uid" in prefix
    assert "j.kickoff_utc IS DISTINCT FROM f.kickoff_utc" in prefix
    assert "j.state <> 'SUPERSEDED'" in prefix
    assert "j.state <> 'LEASED' OR j.lease_expires_at <= now()" in prefix
    assert "LIMIT 1" not in prefix.split("SELECT COUNT(*) INTO v_drift_candidates")[1]
    assert "FOR UPDATE OF j SKIP LOCKED" in fenced
    assert "ON CONFLICT (event_key) DO NOTHING" in fenced
    assert "INSERT INTO public.sxf_base_fixture_drift_events" in fenced
    assert "SET statement_timeout TO '12s'" in sql
    for forbidden in ("DROP TABLE", "TRUNCATE", "DELETE FROM"):
        assert forbidden not in sql.upper()
