"""Independent signal-family evaluation and safe release/restoration contracts."""
from pathlib import Path

from base_signal_engine.scheduler import CHECKPOINT_TASKS

ROOT=Path(__file__).resolve().parents[1]
MIGRATION=ROOT/"migrations/2026_10_22_signal_motor_independent_checkpoints.sql"
RECOVERY=ROOT/"deploy/signal_motor_v2_restore_sibling_jobs_20261022.sql"


def test_all_t_checkpoints_are_family_specific_not_fixture_wide():
    assert CHECKPOINT_TASKS == (
        (72, "EARLY_CORE"), (60, "EARLY_CORE"), (40, "EARLY_CORE"),
        (24, "EARLY_CORE"), (12, "EARLY_T12"),
        (8, "BASE"), (6, "BASE"), (6, "EARLY_RETENTION"),
        (5, "EARLY_RETENTION"), (4, "EARLY_RETENTION"), (3, "EARLY_RETENTION"),
    )


def test_new_skip_migration_only_terminates_owned_due_checkpoint():
    sql=MIGRATION.read_text()
    skip=sql.split("CREATE OR REPLACE FUNCTION public.sxf_base_skip_missing_source",1)[1].split(
        "CREATE OR REPLACE FUNCTION public.sxf_base_claim_due_jobs_lane",1)[0]
    for marker in (
        "j.job_id=p_job_id", "j.lease_token=p_lease_token",
        "j.lease_expires_at>now()", "j.state='LEASED'",
        "j.checkpoint_at<=now()", "j.run_after<=now()",
        "j.ruleset_version='SXF_SIGNAL_MOTOR_V2_2026_10_22'",
        "j.kickoff_utc>now()", "state='SKIPPED_DATA'",
        "last_error_code='SOURCE_INCOMPLETE'", "RETURN FOUND",
        "REVOKE ALL ON FUNCTION", "TO service_role",
    ):
        assert marker in skip,marker
    assert "sibling.state" not in skip
    assert "sibling.fixture_uid" not in skip
    assert "FIXTURE_SKIPPED_UPSTREAM_GAP" not in skip
    assert "j.fixture_uid=" not in skip
    assert "DELETE FROM" not in skip.upper()
    assert "TRUNCATE" not in skip.upper()
    assert "SECURITY DEFINER" not in skip.upper()


def test_claim_never_excludes_an_entire_fixture_due_to_early_source_gap():
    sql=MIGRATION.read_text()
    claim=sql.split("CREATE OR REPLACE FUNCTION public.sxf_base_claim_due_jobs_lane",1)[1]
    assert "stopped.fixture_uid" not in claim
    assert "last_error_code='SOURCE_INCOMPLETE'" not in claim
    assert "j.ruleset_version='SXF_SIGNAL_MOTOR_V2_2026_10_22'" in claim
    assert "AT TIME ZONE 'Europe/Istanbul'" in claim
    assert "j.kickoff_utc>now()" in claim
    assert "FOR UPDATE SKIP LOCKED" in claim
    assert "lease_token=gen_random_uuid()" in claim
    assert "p_lane='LIVE'" in claim


def test_terminal_restore_never_rewrites_missing_checkpoint_or_real_signals():
    sql=RECOVERY.read_text()
    for phrase in (
        "VERIFIED_STOPPED_AND_LEASE_FREE",
        "RESTORE_REJECTED: live leases present",
        "RESTORE_REJECTED: fixture-wide skip RPC still installed",
        "j.ruleset_version='SXF_SIGNAL_MOTOR_V2_2026_10_22'",
        "j.state='SKIPPED_DATA'",
        "j.last_error_code='FIXTURE_SKIPPED_UPSTREAM_GAP'",
        "j.kickoff_utc>now()",
        "state='PENDING'",
        "EXISTS(", "COMMIT;",
    ):
        assert phrase in sql,phrase
    assert "last_error_code='SOURCE_INCOMPLETE'" not in sql
    assert "DELETE FROM" not in sql.upper()
    assert "TRUNCATE" not in sql.upper()
    assert "DISABLE TRIGGER" not in sql.upper()
    assert "UPDATE public.sxf_base_signal_events" not in sql.upper()
    assert "UPDATE public.sxf_base_checkpoint_attempts" not in sql.upper()


def test_feed_does_not_hide_valid_completed_other_family_signals():
    feed=(ROOT/"base_signal_engine/feed.py").read_text()
    assert "terminally_skipped" not in feed
    assert '"state", "eq.SKIPPED_DATA"' not in feed
    assert "HISTORY_INCOMPLETE" in feed
    assert 'selection_status == "ELIGIBLE"' in feed


def test_base_can_complete_when_some_markets_are_absent():
    source=(ROOT/"base_signal_engine/source_quality.py").read_text()
    assert '"disposition": "EVALUATE" if usable else "WAITING_DATA"' in source
    assert 'required = (job.hours,)' in source
    scheduler=(ROOT/"base_signal_engine/scheduler.py").read_text()
    assert '"HISTORY_INCOMPLETE_SIGNAL"' in scheduler
    assert '"FIRST_OBSERVED_NOT_VERIFIED"' in scheduler


def test_main_admin_security_files_survive_preview_reconciliation():
    # Release branch integration must not accidentally revert main-only
    # archive admin authentication and secret-safe setup.
    root=ROOT
    admin=(root/"sxf_capitale_archive_admin.py").read_text()
    auth=(root/"sxf_admin_password_auth.py").read_text()
    assert "is_secure_admin_session" in admin
    assert "SXF_ADMIN_PASSWORD_HASH" in auth
    assert (root/"scripts/configure_sxf_archive_access.py").is_file()
    assert (root/"tests/test_sxf_admin_password_auth.py").is_file()
    assert (root/"tests/test_sxf_archive_configuration.py").is_file()
