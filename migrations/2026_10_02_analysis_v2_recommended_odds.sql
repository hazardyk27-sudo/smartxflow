-- Analysis V2 Part 9 — recommended entry odds compatibility
-- Date: 2026-10-02
--
-- Additive only. Do not apply to production without explicit approval.
-- Existing immutable rows are not backfilled or updated.

ALTER TABLE public.analysis_v2_signal_events
    ADD COLUMN IF NOT EXISTS recommended_odds NUMERIC;

CREATE OR REPLACE FUNCTION public.analysis_v2_validate_settlement()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    expected_match_id_hash TEXT;
    expected_entry_odds NUMERIC;
    expected_engine_version TEXT;
BEGIN
    SELECT
        match_id_hash,
        CASE
            WHEN recommended_odds IS NOT NULL THEN recommended_odds
            WHEN recommended_market = market_key
                 AND recommended_selection = selection_code
                THEN trigger_odds
            ELSE NULL
        END AS entry_odds,
        engine_version
    INTO
        expected_match_id_hash,
        expected_entry_odds,
        expected_engine_version
    FROM public.analysis_v2_signal_events
    WHERE signal_id = NEW.signal_id;

    IF expected_match_id_hash IS NULL THEN
        RAISE EXCEPTION
            'Unknown Analysis V2 signal_id: %',
            NEW.signal_id;
    END IF;

    IF expected_match_id_hash <> NEW.match_id_hash THEN
        RAISE EXCEPTION
            'Settlement match_id_hash mismatch for signal %: expected %, got %',
            NEW.signal_id,
            expected_match_id_hash,
            NEW.match_id_hash;
    END IF;

    IF expected_entry_odds IS DISTINCT FROM NEW.entry_odds THEN
        RAISE EXCEPTION
            'Settlement entry_odds must equal immutable recommended entry odds for signal %',
            NEW.signal_id;
    END IF;

    IF expected_engine_version <> NEW.engine_version THEN
        RAISE EXCEPTION
            'Settlement engine_version mismatch for signal %: expected %, got %',
            NEW.signal_id,
            expected_engine_version,
            NEW.engine_version;
    END IF;

    RETURN NEW;
END;
$$;
