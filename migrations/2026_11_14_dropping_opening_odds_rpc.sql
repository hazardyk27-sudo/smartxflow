-- Apply after 2026_11_14_dropping_opening_odds_index.sql is complete.
CREATE OR REPLACE FUNCTION public.get_dropping_opening_odds(p_keys jsonb)
RETURNS TABLE (
    match_id_hash text,
    market text,
    selection text,
    opening_odds numeric
)
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = ''
AS $function$
    WITH requested AS (
        SELECT DISTINCT
            item.value ->> 'match_id_hash' AS match_id_hash,
            item.value ->> 'market' AS market,
            item.value ->> 'selection' AS selection
        FROM pg_catalog.jsonb_array_elements(COALESCE(p_keys, '[]'::jsonb)) AS item(value)
        WHERE NULLIF(item.value ->> 'match_id_hash', '') IS NOT NULL
          AND NULLIF(item.value ->> 'market', '') IS NOT NULL
          AND NULLIF(item.value ->> 'selection', '') IS NOT NULL
    )
    SELECT
        requested.match_id_hash,
        requested.market,
        requested.selection,
        opening.odds AS opening_odds
    FROM requested
    CROSS JOIN LATERAL (
        SELECT snapshot.odds
        FROM public.moneyway_snapshots AS snapshot
        WHERE snapshot.match_id_hash = requested.match_id_hash
          AND snapshot.market = requested.market
          AND snapshot.selection = requested.selection
          AND snapshot.odds > 0
        ORDER BY snapshot.scraped_at_utc ASC, snapshot.id ASC
        LIMIT 1
    ) AS opening;
$function$;

REVOKE ALL ON FUNCTION public.get_dropping_opening_odds(jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.get_dropping_opening_odds(jsonb) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_dropping_opening_odds(jsonb) TO service_role;

NOTIFY pgrst, 'reload schema';
