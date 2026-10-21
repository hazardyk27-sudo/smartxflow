-- PREVIEW ONLY: one-time operator-controlled fresh start; never auto-run on push.
-- User-requested: remove NEVER-ATTEMPTED PENDING jobs; retire all historical
-- WAITING_DATA/RETRY/expired LEASED jobs WITHOUT deleting immutable attempt
-- journals or any completed signal/event/evaluation row.
-- Preconditions OUTSIDE SQL: authorized operator stopped and disabled both
-- smartxflow-base-worker.service and smartxflow-base-guarded-recovery.timer,
-- verified systemd inactive and no other writers, and obtained cutover approval.
-- Do not treat an instantaneous zero lease count as proof that services stopped.
-- Before running, set session GUC sxf.signal_fresh_start_gate to EXACTLY
-- VERIFIED_WORKER_AND_TIMER_STOPPED, ONLY after verifying prerequisites.
-- Always execute in one transaction with limited role and verified backups.
BEGIN;
SET LOCAL lock_timeout='8s';
SET LOCAL statement_timeout='120s';
LOCK TABLE public.sxf_base_checkpoint_jobs,public.sxf_base_checkpoint_attempts,
           public.sxf_base_reconcile_jobs,public.sxf_base_discovery_cursors
 IN ACCESS EXCLUSIVE MODE;
DO $sxf_fresh_start_checks$
BEGIN
    IF current_setting('sxf.signal_fresh_start_gate',true)
       IS DISTINCT FROM 'VERIFIED_WORKER_AND_TIMER_STOPPED' THEN
        RAISE EXCEPTION 'FRESH_START_REJECTED: worker and timer human verification required';
    END IF;
    IF EXISTS(SELECT 1 FROM public.sxf_base_checkpoint_jobs
              WHERE state='LEASED' AND lease_expires_at>now())
       OR EXISTS(SELECT 1 FROM public.sxf_base_reconcile_jobs
                 WHERE state='LEASED' AND lease_expires_at>now())
       OR EXISTS(SELECT 1 FROM public.sxf_base_discovery_cursors
                 WHERE lease_expires_at>now()) THEN
        RAISE EXCEPTION 'FRESH_START_REJECTED: outstanding leases';
    END IF;
    IF (SELECT count(*) FROM public.sxf_base_discovery_cursors
        WHERE cursor_name='BASE_FIXTURES')<>1 THEN
        RAISE EXCEPTION 'FRESH_START_REJECTED: unexpected cursor identity';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.sxf_base_checkpoint_jobs j
        WHERE j.ruleset_version='SXF_BASE_V1_2026_10_18'
          AND j.state IN('PENDING','RETRY','WAITING_DATA','LEASED')
          AND (
            EXISTS (SELECT 1 FROM public.sxf_base_signal_events e WHERE e.job_id=j.job_id)
            OR EXISTS (SELECT 1 FROM public.sxf_base_checkpoint_evaluations e WHERE e.job_id=j.job_id)
          )
    ) THEN
        RAISE EXCEPTION 'FRESH_START_REJECTED: nonterminal job has completed evidence';
    END IF;
    IF EXISTS(SELECT 1 FROM public.sxf_base_checkpoint_jobs
              WHERE ruleset_version='SXF_SIGNAL_MOTOR_V2_2026_10_22') THEN
        RAISE EXCEPTION 'FRESH_START_REJECTED: V2 already started';
    END IF;
END;
$sxf_fresh_start_checks$;

-- Keep actual Supabase enqueue function unchanged except its accepted release
-- identity. The old release is allowed for audits but cannot be claimed by
-- the new LIVE worker (separate V2-only claim migration).
CREATE OR REPLACE FUNCTION public.sxf_base_enqueue_jobs(p_jobs jsonb)
 RETURNS integer
 LANGUAGE plpgsql
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    item jsonb;
    v_uid uuid;
    v_kick timestamptz;
    v_hours smallint;
    v_family text;
    v_cp timestamptz;
    v_key text;
    v_ruleset text;
    v_added integer := 0;
    v_count integer;
    v_existing record;
BEGIN
    IF p_jobs IS NULL OR jsonb_typeof(p_jobs)<>'array' OR jsonb_array_length(p_jobs)>1000 THEN
        RAISE EXCEPTION 'invalid enqueue batch';
    END IF;
    FOR item IN SELECT value FROM jsonb_array_elements(p_jobs) LOOP
        v_uid := (item->>'fixture_uid')::uuid;
        v_kick := (item->>'kickoff_utc')::timestamptz;
        v_hours := (item->>'checkpoint_hours')::smallint;
        v_family := item->>'family';
        v_key := item->>'job_key';
        v_ruleset := item->>'ruleset_version';
        v_cp := v_kick - v_hours * INTERVAL '1 hour';
        IF v_uid IS NULL OR v_kick IS NULL OR v_hours IS NULL OR v_family IS NULL
            OR v_key IS NULL OR length(v_key)>320 OR v_ruleset NOT IN ('SXF_BASE_V1_2026_10_18', 'SXF_SIGNAL_MOTOR_V2_2026_10_22')
            OR NOT ((v_family='EARLY_CORE' AND v_hours IN(72,60,40,24))
                 OR (v_family='EARLY_T12' AND v_hours=12)
                 OR (v_family='BASE' AND v_hours IN(8,6))
                 OR (v_family='EARLY_RETENTION' AND v_hours IN(6,5,4,3))) THEN
            RAISE EXCEPTION 'invalid enqueue job';
        END IF;
        -- No phantom/ambiguous fixture identities, no legacy hash-only linking.
        SELECT count(*) INTO v_count FROM public.fixtures f
          WHERE f.fixture_uid=v_uid AND f.kickoff_utc=v_kick;
        IF v_count<>1 THEN
            RAISE EXCEPTION 'fixture identity missing or kickoff drift';
        END IF;
        SELECT job_key,fixture_uid,kickoff_utc,family,checkpoint_hours,ruleset_version
          INTO v_existing FROM public.sxf_base_checkpoint_jobs
          WHERE job_key=v_key OR (ruleset_version=v_ruleset AND fixture_uid=v_uid
                AND kickoff_utc=v_kick AND family=v_family AND checkpoint_hours=v_hours)
          LIMIT 1;
        IF FOUND THEN
            IF v_existing.job_key<>v_key OR v_existing.fixture_uid<>v_uid
                OR v_existing.kickoff_utc<>v_kick OR v_existing.family<>v_family
                OR v_existing.checkpoint_hours<>v_hours OR v_existing.ruleset_version<>v_ruleset THEN
                RAISE EXCEPTION 'enqueue key collision';
            END IF;
            CONTINUE;
        END IF;
        INSERT INTO public.sxf_base_checkpoint_jobs(
            job_key,ruleset_version,fixture_uid,kickoff_utc,checkpoint_hours,family,
            checkpoint_at,run_after,next_attempt_at)
        VALUES(v_key,v_ruleset,v_uid,v_kick,v_hours,v_family,v_cp,v_cp+INTERVAL '10 minutes',v_cp+INTERVAL '10 minutes')
        ON CONFLICT DO NOTHING;
        GET DIAGNOSTICS v_count = ROW_COUNT;
        IF v_count = 0 THEN
            -- Another enqueuer may have won the unique-index race after our check.
            SELECT job_key,fixture_uid,kickoff_utc,family,checkpoint_hours,ruleset_version
              INTO v_existing FROM public.sxf_base_checkpoint_jobs
              WHERE job_key=v_key OR (ruleset_version=v_ruleset AND fixture_uid=v_uid
                AND kickoff_utc=v_kick AND family=v_family AND checkpoint_hours=v_hours)
              LIMIT 1;
            IF NOT FOUND OR v_existing.job_key<>v_key OR v_existing.fixture_uid<>v_uid
                OR v_existing.kickoff_utc<>v_kick OR v_existing.family<>v_family
                OR v_existing.checkpoint_hours<>v_hours OR v_existing.ruleset_version<>v_ruleset THEN
                RAISE EXCEPTION 'concurrent enqueue collision';
            END IF;
        END IF;
        v_added := v_added + v_count;
    END LOOP;
    RETURN v_added;
END $function$;

-- Permanently retire retryable V1 jobs with immutable past attempt evidence.
-- Existing 32k+ audit attempts and all completed events remain unchanged.
UPDATE public.sxf_base_checkpoint_jobs
   SET state='SUPERSEDED',last_error_code='FRESH_START_V2_RETIRED',
       lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL
 WHERE ruleset_version='SXF_BASE_V1_2026_10_18'
   AND state IN('RETRY','WAITING_DATA','LEASED');

-- Truly delete only unused, never-attempted PENDING jobs. Do not bypass the
-- sxf_base_checkpoint_attempts_immutable trigger or FK RESTRICT constraints.
DELETE FROM public.sxf_base_checkpoint_jobs j
 WHERE j.ruleset_version='SXF_BASE_V1_2026_10_18'
   AND j.state='PENDING' AND j.attempt_count=0
   AND NOT EXISTS(SELECT 1 FROM public.sxf_base_checkpoint_attempts a WHERE a.job_id=j.job_id)
   AND NOT EXISTS(SELECT 1 FROM public.sxf_base_checkpoint_evaluations e WHERE e.job_id=j.job_id)
   AND NOT EXISTS(SELECT 1 FROM public.sxf_base_signal_events e WHERE e.job_id=j.job_id);
-- Defensive cleanup for any previously-attempted PENDING records.
UPDATE public.sxf_base_checkpoint_jobs
   SET state='SUPERSEDED',last_error_code='FRESH_START_V2_RETIRED',
       lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL
 WHERE ruleset_version='SXF_BASE_V1_2026_10_18'
   AND state='PENDING';

-- The old completed signal ledger is intact; only pending future historical
-- correction work is dropped, per the user's clean-slate instruction.
DELETE FROM public.sxf_base_reconcile_jobs
 WHERE state IN('PENDING','RETRY','WAITING_DATA','LEASED');

-- Restart cursor from 00:00 Istanbul on the cutover day (not the 19 Oct
-- bootstrap). On launch, V2 hourly discovery enumerates fixtures from today
-- onward, with LIVE claims sorted by actual Istanbul match day and kickoff.
UPDATE public.sxf_base_discovery_cursors
   SET bootstrap_start=(date_trunc('day',now() AT TIME ZONE 'Europe/Istanbul')
                        AT TIME ZONE 'Europe/Istanbul'),
       completed_through=(date_trunc('day',now() AT TIME ZONE 'Europe/Istanbul')
                        AT TIME ZONE 'Europe/Istanbul'),
       last_scanned_at=NULL,last_window_fixtures=0,
       lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL,
       last_error_code=NULL,updated_at=now()
 WHERE cursor_name='BASE_FIXTURES';

DO $sxf_fresh_start_post$
BEGIN
    IF EXISTS(SELECT 1 FROM public.sxf_base_checkpoint_jobs
              WHERE ruleset_version='SXF_BASE_V1_2026_10_18'
                AND state IN('PENDING','RETRY','WAITING_DATA','LEASED'))
       OR EXISTS(SELECT 1 FROM public.sxf_base_reconcile_jobs
                 WHERE state IN('PENDING','RETRY','WAITING_DATA','LEASED')) THEN
        RAISE EXCEPTION 'FRESH_START_REJECTED: old queues still claimable';
    END IF;
END;
$sxf_fresh_start_post$;
COMMIT;
