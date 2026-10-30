BEGIN;

-- Stop already queued T-12 checks without deleting their audit history.
UPDATE public.sxf_base_checkpoint_jobs
SET state='SUPERSEDED',
    completed_at=COALESCE(completed_at, clock_timestamp()),
    lease_owner=NULL,
    lease_token=NULL,
    lease_expires_at=NULL,
    waiting_since=NULL,
    last_error_code='ENGINE_RETIRED'
WHERE family='EARLY_T12'
  AND state IN ('PENDING','RETRY','WAITING_DATA','LEASED');

-- Preserve completed historical jobs while preventing new active T-12 jobs.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid='public.sxf_base_checkpoint_jobs'::regclass
          AND conname='sxf_base_checkpoint_jobs_retired_early_t12'
    ) THEN
        ALTER TABLE public.sxf_base_checkpoint_jobs
        ADD CONSTRAINT sxf_base_checkpoint_jobs_retired_early_t12
        CHECK (family <> 'EARLY_T12'
               OR state IN ('COMPLETED','SKIPPED_DATA','SUPERSEDED')) NOT VALID;
    END IF;
END;
$$;

COMMIT;
