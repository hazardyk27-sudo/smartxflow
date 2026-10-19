-- SXF Base Signals Part 4C4C: read-only worker health telemetry.
-- SOURCE ONLY. No live database migrations without explicit approval.
BEGIN;
CREATE OR REPLACE FUNCTION public.sxf_base_health_snapshot()
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER
SET search_path=pg_catalog,public AS $$
DECLARE
    v_jobs jsonb;
    v_reconcile jsonb;
    v_discovery jsonb;
    v_identity jsonb;
BEGIN
    SELECT jsonb_build_object(
      'total',count(*),
      'pending_due',count(*) FILTER (WHERE state IN ('PENDING','RETRY','WAITING_DATA')
                                         AND next_attempt_at<=now()),
      'waiting_data',count(*) FILTER (WHERE state='WAITING_DATA'),
      'leased',count(*) FILTER (WHERE state='LEASED'),
      'expired_leases',count(*) FILTER (WHERE state='LEASED' AND lease_expires_at<now()),
      'completed',count(*) FILTER (WHERE state='COMPLETED'),
      'superseded',count(*) FILTER (WHERE state='SUPERSEDED'),
      'oldest_due_seconds',max(GREATEST(0,EXTRACT(EPOCH FROM now()-checkpoint_at)))
          FILTER (WHERE state IN ('PENDING','RETRY','WAITING_DATA')
                     AND next_attempt_at<=now()),
      't6_base_completed',count(*) FILTER (WHERE family='BASE'
                                                AND checkpoint_hours=6
                                                AND state='COMPLETED')
    ) INTO v_jobs FROM public.sxf_base_checkpoint_jobs;

    SELECT jsonb_build_object(
      'total',count(*),
      'pending_due',count(*) FILTER (WHERE state IN ('PENDING','RETRY','WAITING_DATA')
                                         AND next_attempt_at<=now()),
      'waiting_data',count(*) FILTER (WHERE state='WAITING_DATA'),
      'expired_leases',count(*) FILTER (WHERE state='LEASED' AND lease_expires_at<now()),
      'completed',count(*) FILTER (WHERE state='COMPLETED'),
      'last_checked_at',max(last_checked_at)
    ) INTO v_reconcile FROM public.sxf_base_reconcile_jobs;

    SELECT jsonb_build_object(
      'initialized',count(*)>0,
      'bootstrap_start',max(bootstrap_start),
      'completed_through',max(completed_through),
      'lag_seconds',CASE WHEN count(*)=0 THEN NULL
          ELSE GREATEST(0,EXTRACT(EPOCH FROM now()-max(completed_through))) END,
      'lease_expired',coalesce(bool_or(lease_expires_at<now()),false),
      'last_scanned_at',max(last_scanned_at),
      'last_window_fixtures',max(last_window_fixtures)
    ) INTO v_discovery FROM public.sxf_base_discovery_cursors
    WHERE cursor_name='BASE_FIXTURES';

    SELECT jsonb_build_object(
      'drift_events',count(*),
      'last_drift_observed_at',max(observed_at)
    ) INTO v_identity FROM public.sxf_base_fixture_drift_events;

    RETURN jsonb_build_object(
      'generated_at',now(),
      'checkpoint_queue',v_jobs,
      'reconciliation_queue',v_reconcile,
      'discovery_cursor',v_discovery,
      'fixture_identity',v_identity,
      'snapshot_ingestion_watermark',NULL
    );
END $$;
REVOKE ALL ON FUNCTION public.sxf_base_health_snapshot()
    FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.sxf_base_health_snapshot() TO service_role;
COMMIT;
