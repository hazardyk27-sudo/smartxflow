-- SXF Signal Motor V3: prospective release, 2026-10-24.
-- Retains all V1/V2 rows/evaluations/attempts/events unchanged.
-- Existing in-flight V2 skip ACKs remain valid while V3 workers start.
-- Both checkpoint claim paths and late-T6 reconciliation are V3-fenced.
-- Before production: verify exact preview SHA and CI; release through main.
BEGIN;
SET LOCAL lock_timeout='8s';
SET LOCAL statement_timeout='90s';

DO $preflight$
BEGIN
  IF to_regclass('public.sxf_base_checkpoint_jobs') IS NULL OR
     to_regclass('public.sxf_base_signal_events') IS NULL OR
     to_regclass('public.sxf_base_reconcile_jobs') IS NULL THEN
    RAISE EXCEPTION 'V3_CUTOVER_REJECTED: required durable tables absent';
  END IF;
  IF EXISTS (SELECT 1 FROM public.sxf_base_checkpoint_jobs
              WHERE ruleset_version='SXF_SIGNAL_MOTOR_V3_2026_10_24') THEN
    RAISE EXCEPTION 'V3_CUTOVER_REJECTED: V3 jobs already exist';
  END IF;
END $preflight$;

-- sxf_base_claim_due_jobs
CREATE OR REPLACE FUNCTION public.sxf_base_claim_due_jobs(p_worker text, p_limit integer DEFAULT 25, p_lease_seconds integer DEFAULT 300)
 RETURNS TABLE(job_id uuid, job_key text, ruleset_version text, fixture_uid uuid, kickoff_utc timestamp with time zone, checkpoint_hours smallint, family text, checkpoint_at timestamp with time zone, lease_token uuid, attempt_count integer)
 LANGUAGE plpgsql
 SET search_path TO 'public', 'pg_temp'
AS $function$
BEGIN
    IF p_worker IS NULL OR length(trim(p_worker))<1 OR length(p_worker)>100
       OR p_limit NOT BETWEEN 1 AND 100 OR p_lease_seconds NOT BETWEEN 60 AND 1800 THEN
        RAISE EXCEPTION 'invalid claim parameters';
    END IF;
    RETURN QUERY WITH locked AS (
      SELECT j.job_id FROM public.sxf_base_checkpoint_jobs j
       WHERE j.ruleset_version='SXF_SIGNAL_MOTOR_V3_2026_10_24'
         AND ((j.state IN('PENDING','RETRY','WAITING_DATA') AND j.next_attempt_at<=now())
          OR (j.state='LEASED' AND j.lease_expires_at<now()))
       ORDER BY
         CASE WHEN j.checkpoint_at >= now()-INTERVAL '3 hours' THEN 0 ELSE 1 END,
         CASE WHEN j.family='BASE' AND j.checkpoint_hours IN (8,6) THEN 0 ELSE 1 END,
         j.checkpoint_at,j.job_id LIMIT p_limit
       FOR UPDATE SKIP LOCKED
    ), updated AS (
      UPDATE public.sxf_base_checkpoint_jobs j
      SET state='LEASED',lease_owner=p_worker,lease_token=gen_random_uuid(),
          lease_expires_at=now()+make_interval(secs=>p_lease_seconds),
          attempt_count=j.attempt_count+1
      FROM locked l WHERE j.job_id=l.job_id
      RETURNING j.*
    )
    SELECT u.job_id,u.job_key,u.ruleset_version,u.fixture_uid,u.kickoff_utc,
           u.checkpoint_hours,u.family,u.checkpoint_at,u.lease_token,u.attempt_count
    FROM updated u ORDER BY u.checkpoint_at,u.job_id;
END $function$;

-- sxf_base_claim_due_jobs_lane
CREATE OR REPLACE FUNCTION public.sxf_base_claim_due_jobs_lane(p_worker text, p_lane text, p_limit integer DEFAULT 1, p_lease_seconds integer DEFAULT 900)
 RETURNS TABLE(job_id uuid, job_key text, ruleset_version text, fixture_uid uuid, kickoff_utc timestamp with time zone, checkpoint_hours smallint, family text, checkpoint_at timestamp with time zone, lease_token uuid, attempt_count integer)
 LANGUAGE plpgsql
 SET search_path TO 'public', 'pg_temp'
AS $function$
BEGIN
    IF p_worker IS NULL OR length(trim(p_worker))<1 OR length(p_worker)>100
       OR p_lane IS NULL OR p_lane NOT IN ('LIVE','BACKLOG')
       OR p_limit IS NULL OR p_limit <> 1
       OR p_lease_seconds IS NULL OR p_lease_seconds NOT BETWEEN 60 AND 1800 THEN
        RAISE EXCEPTION 'invalid lane claim parameters';
    END IF;
    RETURN QUERY WITH locked AS (
        SELECT j.job_id
        FROM public.sxf_base_checkpoint_jobs j
        WHERE (
            (j.state IN ('PENDING','RETRY','WAITING_DATA') AND j.next_attempt_at<=now())
            OR (j.state='LEASED' AND j.lease_expires_at<now())
        )
        AND j.run_after<=now()
        AND j.ruleset_version='SXF_SIGNAL_MOTOR_V3_2026_10_24'
        -- Jobs are independent: an Early source gap cannot block Base or T12.
        AND (
            CASE WHEN p_lane='LIVE'
                THEN j.kickoff_utc>now()
                ELSE j.kickoff_utc<=now()
            END
        )
        -- Today first (Istanbul day), then tomorrow, then later match days.
        -- Do NOT prioritize ancient checkpoint debt over today's fixtures.
        ORDER BY
            -- Today first as explicitly requested, then protect checkpoint
            -- windows that can still yield an on-time signal before backlog.
            (j.kickoff_utc AT TIME ZONE 'Europe/Istanbul')::date ASC,
            CASE WHEN j.checkpoint_at + INTERVAL '20 minutes' >= now()
                      THEN 0 ELSE 1 END ASC,
            CASE WHEN j.checkpoint_at + INTERVAL '20 minutes' >= now()
                      THEN j.checkpoint_at ELSE NULL END ASC NULLS LAST,
            j.kickoff_utc ASC,
            j.checkpoint_at ASC,
            j.job_id ASC
        LIMIT p_limit
        FOR UPDATE SKIP LOCKED
    ), updated AS (
        UPDATE public.sxf_base_checkpoint_jobs j
        SET state='LEASED',lease_owner=p_worker,lease_token=gen_random_uuid(),
            lease_expires_at=now()+make_interval(secs=>p_lease_seconds),
            attempt_count=j.attempt_count+1
        FROM locked l WHERE j.job_id=l.job_id
        RETURNING j.*
    )
    SELECT u.job_id,u.job_key,u.ruleset_version,u.fixture_uid,u.kickoff_utc,
           u.checkpoint_hours,u.family,u.checkpoint_at,u.lease_token,u.attempt_count
    FROM updated u ORDER BY u.checkpoint_at,u.job_id;
END;
$function$;

-- sxf_base_claim_reconcile
CREATE OR REPLACE FUNCTION public.sxf_base_claim_reconcile(p_worker text, p_limit integer DEFAULT 1, p_lease_seconds integer DEFAULT 900)
 RETURNS TABLE(reconciliation_id bigint, origin_event_key text, fixture_uid uuid, kickoff_utc timestamp with time zone, market text, lease_token uuid, attempt_count integer)
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog', 'public'
AS $function$
BEGIN
    IF p_worker IS NULL OR length(btrim(p_worker)) NOT BETWEEN 1 AND 100
       OR p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 10
       OR p_lease_seconds IS NULL OR p_lease_seconds NOT BETWEEN 60 AND 1800 THEN
        RAISE EXCEPTION 'invalid reconcile claim';
    END IF;
    RETURN QUERY WITH locked AS (
      SELECT r.reconciliation_id FROM public.sxf_base_reconcile_jobs r
      WHERE EXISTS (
        SELECT 1 FROM public.sxf_base_signal_events e
        WHERE e.event_key=r.origin_event_key AND e.ruleset_version='SXF_SIGNAL_MOTOR_V3_2026_10_24'
      )
        AND ((r.state IN ('PENDING','RETRY','WAITING_DATA') AND r.next_attempt_at<=now())
           OR (r.state='LEASED' AND r.lease_expires_at<now()))
      ORDER BY r.reconciliation_id LIMIT p_limit FOR UPDATE SKIP LOCKED
    ), updated AS (
      UPDATE public.sxf_base_reconcile_jobs r
      SET state='LEASED',lease_owner=p_worker,lease_token=gen_random_uuid(),
          lease_expires_at=now()+make_interval(secs=>p_lease_seconds),
          attempt_count=r.attempt_count+1
      FROM locked l WHERE r.reconciliation_id=l.reconciliation_id
      RETURNING r.*
    ) SELECT u.reconciliation_id,u.origin_event_key,u.fixture_uid,u.kickoff_utc,
             u.market,u.lease_token,u.attempt_count FROM updated u
      ORDER BY u.reconciliation_id;
END $function$;

-- sxf_base_enqueue_jobs
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
            OR v_key IS NULL OR length(v_key)>320 OR v_ruleset NOT IN ('SXF_BASE_V1_2026_10_18', 'SXF_SIGNAL_MOTOR_V2_2026_10_22', 'SXF_SIGNAL_MOTOR_V3_2026_10_24')
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

-- sxf_base_skip_missing_source
CREATE OR REPLACE FUNCTION public.sxf_base_skip_missing_source(p_job_id uuid, p_lease_token uuid, p_reason text DEFAULT 'SOURCE_INCOMPLETE'::text)
 RETURNS boolean
 LANGUAGE plpgsql
 SET search_path TO 'public', 'pg_temp'
AS $function$
BEGIN
    IF p_job_id IS NULL OR p_lease_token IS NULL
       OR p_reason IS DISTINCT FROM 'SOURCE_INCOMPLETE' THEN
        RAISE EXCEPTION 'invalid source skip parameters';
    END IF;
    -- Only the missing family's due checkpoint is terminal. Do not alter
    -- sibling families or other checkpoints, even for the same fixture.
    UPDATE public.sxf_base_checkpoint_jobs j
       SET state='SKIPPED_DATA',
           last_error_code='SOURCE_INCOMPLETE',
           waiting_since=COALESCE(j.waiting_since,now()),
           lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL
     WHERE j.job_id=p_job_id
       AND j.lease_token=p_lease_token
       AND j.state='LEASED'
       AND j.ruleset_version IN ('SXF_SIGNAL_MOTOR_V2_2026_10_22', 'SXF_SIGNAL_MOTOR_V3_2026_10_24')
       AND j.lease_expires_at>now()
       AND j.checkpoint_at<=now()
       AND j.run_after<=now()
       AND j.kickoff_utc>now();
    RETURN FOUND;
END;
$function$;
COMMIT;
