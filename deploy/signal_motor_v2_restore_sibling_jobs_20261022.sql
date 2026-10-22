-- Operator-gated remediation of V2 jobs incorrectly skipped by the
-- superseded fixture-wide skip routine. No data is deleted. The originally
-- missing checkpoint remains SKIPPED_DATA / SOURCE_INCOMPLETE, but the other
-- families and checkpoints of that fixture are once again claimable.
--
-- MUST run only after (1) production code & RPC migration for independent
-- checkpoints are staged, (2) worker + recovery timer both stopped/disabled,
-- and (3) lease drain verified. This cannot enforce systemd state; never
-- treat an empty instant lease sample as service stop confirmation.
--
-- The operator sets sxf.independent_restore_gate to
-- VERIFIED_STOPPED_AND_LEASE_FREE in the same SQL transaction session.
BEGIN;
SET LOCAL lock_timeout='8s';
SET LOCAL statement_timeout='120s';
LOCK TABLE public.sxf_base_checkpoint_jobs IN ACCESS EXCLUSIVE MODE;
DO $checks$
BEGIN
    IF current_setting('sxf.independent_restore_gate',true)
          IS DISTINCT FROM 'VERIFIED_STOPPED_AND_LEASE_FREE' THEN
        RAISE EXCEPTION 'RESTORE_REJECTED: worker and timer must be stopped';
    END IF;
    IF EXISTS(
      SELECT 1 FROM public.sxf_base_checkpoint_jobs
       WHERE state='LEASED' AND lease_expires_at>now()
    ) OR EXISTS(
      SELECT 1 FROM public.sxf_base_reconcile_jobs
       WHERE state='LEASED' AND lease_expires_at>now()
    ) OR EXISTS(
      SELECT 1 FROM public.sxf_base_discovery_cursors
       WHERE lease_expires_at>now()
    ) THEN
        RAISE EXCEPTION 'RESTORE_REJECTED: live leases present';
    END IF;
    IF NOT EXISTS(
      SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
       WHERE n.nspname='public' AND p.proname='sxf_base_skip_missing_source'
         AND position('FIXTURE_SKIPPED_UPSTREAM_GAP' IN pg_get_functiondef(p.oid))=0
    ) THEN
        RAISE EXCEPTION 'RESTORE_REJECTED: fixture-wide skip RPC still installed';
    END IF;
    IF EXISTS(
      SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
       WHERE n.nspname='public' AND p.proname='sxf_base_claim_due_jobs_lane'
         AND position('stopped.fixture_uid' IN pg_get_functiondef(p.oid))>0
    ) THEN
        RAISE EXCEPTION 'RESTORE_REJECTED: claim RPC still blocks skipped fixtures';
    END IF;
END;
$checks$;
-- Keep append-only evaluations/events/attempts and real source-gap jobs.
-- This reset only undoes upstream propagation to sibling checkpoint jobs.
UPDATE public.sxf_base_checkpoint_jobs j
   SET state='PENDING',
       last_error_code=NULL,
       waiting_since=NULL,
       next_attempt_at=LEAST(j.next_attempt_at,now()),
       lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL
 WHERE j.ruleset_version='SXF_SIGNAL_MOTOR_V2_2026_10_22'
   AND j.state='SKIPPED_DATA'
   AND j.last_error_code='FIXTURE_SKIPPED_UPSTREAM_GAP'
   AND j.kickoff_utc>now()
   AND NOT EXISTS(
     SELECT 1 FROM public.sxf_base_checkpoint_evaluations e
     WHERE e.job_id=j.job_id
   )
   AND NOT EXISTS(
     SELECT 1 FROM public.sxf_base_signal_events s
     WHERE s.job_id=j.job_id
   );
DO $post$
BEGIN
  IF EXISTS(
    SELECT 1 FROM public.sxf_base_checkpoint_jobs j
    WHERE j.ruleset_version='SXF_SIGNAL_MOTOR_V2_2026_10_22'
      AND j.state='PENDING' AND j.last_error_code='FIXTURE_SKIPPED_UPSTREAM_GAP'
  ) THEN
    RAISE EXCEPTION 'RESTORE_REJECTED: stale terminal reason still claimable';
  END IF;
END;
$post$;
COMMIT;
