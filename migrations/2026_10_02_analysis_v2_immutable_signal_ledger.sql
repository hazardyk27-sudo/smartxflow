-- SmartXFlow Analysis V2 — immutable signal history
-- Date: 2026-10-02
--
-- IMPORTANT:
-- * This migration belongs to GitHub preview only until explicit production approval.
-- * Trigger facts are immutable.
-- * State changes are append-only.
-- * One logical signal can have only one settlement.
-- * Settlement uses exact match_id_hash only; fuzzy team-name settlement is forbidden.

CREATE TABLE IF NOT EXISTS public.analysis_v2_signal_events (
    id BIGSERIAL PRIMARY KEY,
    signal_id TEXT NOT NULL UNIQUE,
    engine_key TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    match_id_hash VARCHAR(12) NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    league TEXT,
    kickoff_utc TIMESTAMPTZ,
    market_key TEXT NOT NULL,
    selection_code TEXT NOT NULL,
    recommended_market TEXT NOT NULL,
    recommended_selection TEXT NOT NULL,
    recommended_odds NUMERIC,
    trigger_at TIMESTAMPTZ NOT NULL,
    opening_odds NUMERIC,
    trigger_odds NUMERIC,
    trigger_pct NUMERIC,
    trigger_amount NUMERIC,
    trigger_volume NUMERIC,
    odds_6h NUMERIC,
    odds_2h NUMERIC,
    odds_30m NUMERIC,
    pct_6h NUMERIC,
    pct_2h NUMERIC,
    pct_30m NUMERIC,
    amount_6h NUMERIC,
    amount_2h NUMERIC,
    amount_30m NUMERIC,
    money_added_6h NUMERIC,
    money_added_2h NUMERIC,
    money_added_30m NUMERIC,
    hours_before_kickoff NUMERIC,
    engine_reason JSONB NOT NULL DEFAULT '{}'::jsonb,
    features JSONB NOT NULL DEFAULT '{}'::jsonb,
    config_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    raw_trigger JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT analysis_v2_signal_hash_format
        CHECK (match_id_hash ~ '^[0-9a-f]{12}$'),
    CONSTRAINT analysis_v2_signal_identity_unique
        UNIQUE (
            engine_key,
            engine_version,
            match_id_hash,
            market_key,
            selection_code
        )
);

CREATE INDEX IF NOT EXISTS idx_analysis_v2_signal_match
    ON public.analysis_v2_signal_events(match_id_hash, trigger_at DESC);
CREATE INDEX IF NOT EXISTS idx_analysis_v2_signal_engine
    ON public.analysis_v2_signal_events(
        engine_key,
        engine_version,
        trigger_at DESC
    );
CREATE INDEX IF NOT EXISTS idx_analysis_v2_signal_market
    ON public.analysis_v2_signal_events(
        market_key,
        selection_code,
        trigger_at DESC
    );

CREATE TABLE IF NOT EXISTS public.analysis_v2_signal_state_events (
    id BIGSERIAL PRIMARY KEY,
    state_id TEXT NOT NULL UNIQUE,
    signal_id TEXT NOT NULL
        REFERENCES public.analysis_v2_signal_events(signal_id)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT,
    state TEXT NOT NULL,
    state_at TIMESTAMPTZ NOT NULL,
    current_odds NUMERIC,
    current_pct NUMERIC,
    current_amount NUMERIC,
    current_volume NUMERIC,
    reason_code TEXT,
    reason JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT analysis_v2_signal_state_value
        CHECK (
            state IN (
                'TRIGGERED',
                'ACTIVE',
                'CONFIRMED',
                'WEAKENED',
                'INVALIDATED',
                'SETTLED'
            )
        )
);

CREATE INDEX IF NOT EXISTS idx_analysis_v2_state_signal
    ON public.analysis_v2_signal_state_events(signal_id, state_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS public.analysis_v2_signal_settlements (
    id BIGSERIAL PRIMARY KEY,
    settlement_id TEXT NOT NULL UNIQUE,
    signal_id TEXT NOT NULL UNIQUE
        REFERENCES public.analysis_v2_signal_events(signal_id)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT,
    match_id_hash VARCHAR(12) NOT NULL,
    final_home_score INTEGER,
    final_away_score INTEGER,
    outcome TEXT NOT NULL,
    entry_odds NUMERIC,
    pnl_units NUMERIC,
    settled_at TIMESTAMPTZ NOT NULL,
    settlement_source TEXT NOT NULL DEFAULT 'finished_scores',
    engine_version TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT analysis_v2_settlement_hash_format
        CHECK (match_id_hash ~ '^[0-9a-f]{12}$'),
    CONSTRAINT analysis_v2_settlement_outcome
        CHECK (outcome IN ('WIN', 'LOSS', 'PUSH', 'VOID', 'UNKNOWN'))
);

CREATE INDEX IF NOT EXISTS idx_analysis_v2_settlement_match
    ON public.analysis_v2_signal_settlements(match_id_hash, settled_at DESC);

CREATE OR REPLACE FUNCTION public.analysis_v2_reject_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'Analysis V2 ledger is append-only; UPDATE/DELETE is forbidden';
END;
$$;

DROP TRIGGER IF EXISTS trg_analysis_v2_signal_events_immutable
    ON public.analysis_v2_signal_events;
CREATE TRIGGER trg_analysis_v2_signal_events_immutable
BEFORE UPDATE OR DELETE ON public.analysis_v2_signal_events
FOR EACH ROW
EXECUTE FUNCTION public.analysis_v2_reject_mutation();

DROP TRIGGER IF EXISTS trg_analysis_v2_signal_state_events_immutable
    ON public.analysis_v2_signal_state_events;
CREATE TRIGGER trg_analysis_v2_signal_state_events_immutable
BEFORE UPDATE OR DELETE ON public.analysis_v2_signal_state_events
FOR EACH ROW
EXECUTE FUNCTION public.analysis_v2_reject_mutation();

DROP TRIGGER IF EXISTS trg_analysis_v2_signal_settlements_immutable
    ON public.analysis_v2_signal_settlements;
CREATE TRIGGER trg_analysis_v2_signal_settlements_immutable
BEFORE UPDATE OR DELETE ON public.analysis_v2_signal_settlements
FOR EACH ROW
EXECUTE FUNCTION public.analysis_v2_reject_mutation();

CREATE OR REPLACE FUNCTION public.analysis_v2_validate_settlement()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    expected_match_id_hash TEXT;
    expected_entry_odds NUMERIC;
    expected_pnl_units NUMERIC;
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

    expected_pnl_units := CASE
        WHEN NEW.outcome = 'WIN' AND expected_entry_odds IS NOT NULL
            THEN expected_entry_odds - 1
        WHEN NEW.outcome = 'LOSS'
            THEN -1
        WHEN NEW.outcome IN ('PUSH', 'VOID')
            THEN 0
        ELSE NULL
    END;

    IF expected_pnl_units IS DISTINCT FROM NEW.pnl_units THEN
        RAISE EXCEPTION
            'Settlement pnl_units must match canonical flat-stake PnL for signal %',
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

DROP TRIGGER IF EXISTS trg_analysis_v2_settlement_validate
    ON public.analysis_v2_signal_settlements;
CREATE TRIGGER trg_analysis_v2_settlement_validate
BEFORE INSERT ON public.analysis_v2_signal_settlements
FOR EACH ROW
EXECUTE FUNCTION public.analysis_v2_validate_settlement();

CREATE OR REPLACE VIEW public.analysis_v2_signal_current AS
SELECT
    e.*,
    s.state AS current_state,
    s.state_at AS current_state_at,
    s.current_odds,
    s.current_pct,
    s.current_amount,
    s.current_volume,
    s.reason_code AS current_reason_code,
    s.reason AS current_reason,
    x.settlement_id,
    x.final_home_score,
    x.final_away_score,
    x.outcome,
    x.entry_odds,
    x.pnl_units,
    x.settled_at,
    x.settlement_source
FROM public.analysis_v2_signal_events e
LEFT JOIN LATERAL (
    SELECT st.*
    FROM public.analysis_v2_signal_state_events st
    WHERE st.signal_id = e.signal_id
    ORDER BY st.state_at DESC, st.id DESC
    LIMIT 1
) s ON TRUE
LEFT JOIN public.analysis_v2_signal_settlements x
    ON x.signal_id = e.signal_id;

COMMENT ON TABLE public.analysis_v2_signal_events IS
    'Immutable trigger-time snapshots for Analysis V2.';
COMMENT ON TABLE public.analysis_v2_signal_state_events IS
    'Append-only Analysis V2 lifecycle history.';
COMMENT ON TABLE public.analysis_v2_signal_settlements IS
    'One exact-match settlement per Analysis V2 signal.';
