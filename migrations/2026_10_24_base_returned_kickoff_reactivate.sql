-- Restore exact current V3 kickoff identity when A->B->A without
-- deleting jobs or rewriting immutable evaluations / signal events.
-- Signal-bearing superseded jobs fail closed; drift events stay append-only.
BEGIN;

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
        SELECT job_id,state,job_key,fixture_uid,kickoff_utc,family,checkpoint_hours,ruleset_version
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
            -- Reintroduced exact kickoff identity (A->B->A); preserve events.
            IF v_existing.state='SUPERSEDED'
               AND v_ruleset='SXF_SIGNAL_MOTOR_V3_2026_10_24'
               AND v_kick>now() THEN
                IF EXISTS (
                    SELECT 1 FROM public.sxf_base_signal_events e
                    WHERE e.job_id=v_existing.job_id
                ) THEN
                    RAISE EXCEPTION 'returning kickoff has immutable signal events';
                END IF;
                UPDATE public.sxf_base_checkpoint_jobs j
                SET state=CASE WHEN EXISTS (
                        SELECT 1 FROM public.sxf_base_checkpoint_evaluations e
                        WHERE e.job_id=j.job_id
                    ) THEN 'COMPLETED' ELSE 'PENDING' END,
                    lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL,
                    last_error_code=NULL
                WHERE j.job_id=v_existing.job_id AND j.state='SUPERSEDED'
                  AND j.ruleset_version=v_ruleset AND j.fixture_uid=v_uid
                  AND j.kickoff_utc=v_kick
                  AND EXISTS (
                    SELECT 1 FROM public.fixtures f
                    WHERE f.fixture_uid=v_uid AND f.kickoff_utc=v_kick
                  );
                GET DIAGNOSTICS v_count=ROW_COUNT;
                IF v_count<>1 THEN
                    RAISE EXCEPTION 'returning kickoff reactivation uncertain';
                END IF;
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
            SELECT job_id,state,job_key,fixture_uid,kickoff_utc,family,checkpoint_hours,ruleset_version
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
END $function$


COMMIT;
