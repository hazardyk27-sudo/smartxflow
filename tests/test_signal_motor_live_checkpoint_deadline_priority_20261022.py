"""Live T-checkpoint deadline priority must not starve valid signals behind replay."""
from pathlib import Path

SQL=(Path(__file__).resolve().parents[1]/
     "migrations/2026_10_22_signal_motor_live_checkpoint_deadline_priority.sql").read_text()


def test_today_first_then_due_still_timely():
    assert "CREATE OR REPLACE FUNCTION public.sxf_base_claim_due_jobs_lane" in SQL
    order=SQL.split("ORDER BY",1)[1].split("LIMIT p_limit",1)[0]
    today=order.index("(j.kickoff_utc AT TIME ZONE 'Europe/Istanbul')::date ASC")
    deadline=order.index("CASE WHEN j.checkpoint_at + INTERVAL '20 minutes' >= now()")
    kickoff=order.index("j.kickoff_utc ASC")
    assert today < deadline < kickoff
    assert "THEN 0 ELSE 1 END ASC" in order
    assert "THEN j.checkpoint_at ELSE NULL END ASC NULLS LAST" in order


def test_worker_safe_fencing_and_no_future_source_read():
    for marker in ("p_limit <> 1","j.next_attempt_at<=now()",
                   "j.run_after<=now()","FOR UPDATE SKIP LOCKED",
                   "j.lease_expires_at<now()",
                   "j.ruleset_version='SXF_SIGNAL_MOTOR_V2_2026_10_22'",
                   "GRANT EXECUTE ON FUNCTION",
                   "service_role"):
        assert marker in SQL,marker
    assert "DELETE FROM public." not in SQL
    assert "TRUNCATE" not in SQL.upper()
    assert "FIXTURE_SKIPPED_UPSTREAM_GAP" not in SQL
    assert "UPDATE public.sxf_base_checkpoint_jobs j" in SQL
    assert "SET state='LEASED'" in SQL
