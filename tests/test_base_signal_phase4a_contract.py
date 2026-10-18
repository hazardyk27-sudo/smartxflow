"""Part 4A migration static safety contract. Real Postgres testing is still required."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SQL = (ROOT / "migrations/2026_10_19_sxf_base_phase4a_waiting_data_hardening.sql").read_text()
BASELINE = (ROOT / "migrations/2026_10_18_sxf_base_durable_queue.sql").read_text()


def test_ordered_additive_migration_and_no_runtime_source_changes():
    assert SQL.lstrip().startswith("-- SmartXFlow Base Signals Part 4A")
    assert "BEGIN;" in SQL and SQL.rstrip().endswith("COMMIT;")
    assert "2026_10_18_sxf_base_durable_queue.sql" in SQL
    assert "UPDATE public.moneyway_snapshots" not in SQL
    assert "DELETE FROM public.fixtures" not in SQL
    assert "CREATE INDEX CONCURRENTLY" not in SQL


def test_waiting_data_is_nonterminal_and_claimable_with_fencing():
    assert "'WAITING_DATA','COMPLETED'" in SQL
    assert "WHERE state='WAITING_DATA'" in SQL
    assert "sxf_base_wait_for_data(" in SQL
    assert "state='WAITING_DATA',next_attempt_at=" in SQL
    assert "j.state IN('PENDING','RETRY','WAITING_DATA')" in SQL
    assert "FOR UPDATE SKIP LOCKED" in SQL
    assert "lease_token=gen_random_uuid()" in SQL
    assert "j.lease_token=p_lease_token" in SQL
    assert "j.lease_expires_at>now()" in SQL


def test_audit_is_append_only_and_is_atomic_with_status_transition():
    assert "CREATE TABLE IF NOT EXISTS public.sxf_base_checkpoint_attempts" in SQL
    assert "UNIQUE(job_id,attempt_number)" in SQL
    assert "AFTER UPDATE ON public.sxf_base_checkpoint_jobs" in SQL
    assert "OLD.state <> 'LEASED'" in SQL
    assert "OLD.lease_token IS DISTINCT FROM NEW.lease_token" in SQL
    assert "'LEASE_EXPIRED'" in SQL
    assert "sxf_base_checkpoint_attempts_immutable" in SQL
    assert "EXECUTE FUNCTION public.sxf_base_append_only_guard()" in SQL


def test_no_false_base_completion_and_event_evidence_frozen():
    assert "BEFORE INSERT ON public.sxf_base_checkpoint_evaluations" in SQL
    assert "BASE source evidence missing: use WAITING_DATA" in SQL
    assert "m.decision->>'checkpoint' IN ('6','8')" in SQL
    assert "sxf_base_event_no_lookahead" in SQL
    assert "NEW.details->>'observed_at'" in SQL
    assert "NEW.kickoff_utc - NEW.source_checkpoint_hours" in SQL
    assert "'INVALIDATED','CORRECTED','SETTLED'" in SQL
    assert "sxf_base_signal_events_immutable" in BASELINE


def test_service_role_only_and_rls_defense_in_depth():
    assert "ENABLE ROW LEVEL SECURITY" in SQL
    assert "FROM PUBLIC,anon,authenticated" in SQL
    assert "GRANT SELECT,INSERT ON public.sxf_base_checkpoint_attempts TO service_role" in SQL
    assert "GRANT EXECUTE ON FUNCTION public.sxf_base_wait_for_data" in SQL
    assert "SECURITY INVOKER" in SQL
    assert "SECURITY DEFINER" not in SQL
    assert not re.search(r"(?im)^\s*GRANT\b[^\n]*\bTO\s+(anon|authenticated)\b", SQL)
