-- Analysis V2 immutable signal ledger
-- Date: 2026-10-02
--
-- Design goals:
-- 1) Trigger-time facts never change and are never deleted.
-- 2) Later weakening/invalidation is appended as state history, not mutation.
-- 3) Settlement is appended and tied to exact match_id_hash/signal_uid.
-- 4) Every record is engine-versioned so backtests remain reproducible.

CREATE TABLE IF NOT EXISTS public.analysis_v2_signal_events (
    id BIGSERIAL PRIMARY KEY,
    signal_uid TEXT NOT NULL UNIQUE,
    engine_key TEXT NOT NULL,
    engine_version TEXT NOT NULL,

    match_id_hash VARCHAR(12) NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    league TEXT,
    kickoff_utc TIMESTAMPTZ,

    market_key TEXT NOT NULL,
    selection_code TEXT NOT NULL,
    selection_label TEXT,

    triggered_at TIMESTAMPTZ NOT NULL,

    opening_odds NUMERIC,
    odds_6h NUMERIC,
    odds_2h NUMERIC,
    odds_30m NUMERIC,
    trigger_odds NUMERIC,

    trigger_pct NUMERIC,
    trigger_amount NUMERIC,
    trigger_volume NUMERIC,

    money_delta_6h NUMERIC,
    money_delta_2h NUMERIC,
    money_delta_30m NUMERIC,

    price_move_open_pct NUMERIC,
    price_move_6h_pct NUMERIC,
    price_move_2h_pct NUMERIC,
    price_move_30m_pct NUMERIC,

    hours_before_kickoff NUMERIC,

    provider_market_key TEXT,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    engine_params JSONB NOT NULL DEFAULT '{}'::jsonb,
    raw_trigger JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT analysis_v2_signal_hash_format
        CHECK (match_id_hash ~ '^[0-9a-f]{12}$')
);

CREATE INDEX IF NOT EXISTS idx_analysis_v2_signal_match
    ON public.analysis_v2_signal_events(match_id_hash, triggered_at DESC);
CREATE INDEX IF NOT EXISTS idx_analysis_v2_signal_engine
    ON public.analysis_v2_signal_events(engine_key, engine_version, triggered_at DESC);
CREATE INDEX IF NOT EXISTS idx_analysis_v2_signal_market
    ON public.analysis_v2_signal_events(market_key, selection_code, triggered_at DESC);


CREATE TABLE IF NOT EXISTS public.analysis_v2_signal_state_events (
    id BIGSERIAL PRIMARY KEY,
    state_uid TEXT NOT NULL UNIQUE,
    signal_uid TEXT NOT NULL
        REFERENCES public.analysis_v2_signal_events(signal_uid)
        ON UPDATE RESTRICT ON DELETE RESTRICT,

    status TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,

    current_odds NUMERIC,
    current_pct NUMERIC,
    current_amount NUMERIC,
    current_volume NUMERIC,

    reason_code TEXT,
    reason_detail JSONB NOT NULL DEFAULT '{}'::jsonb,
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT analysis_v2_signal_state_status
        CHECK (status IN ('ACTIVE', 'WEAKENED', 'INVALIDATED', 'SETTLED'))
);

CREATE INDEX IF NOT EXISTS idx_analysis_v2_state_signal
    ON public.analysis_v2_signal_state_events(signal_uid, observed_at DESC);


CREATE TABLE IF NOT EXISTS public.analysis_v2_signal_settlement_events (
    id BIGSERIAL PRIMARY KEY,
    settlement_uid TEXT NOT NULL UNIQUE,
    signal_uid TEXT NOT NULL
        REFERENCES public.analysis_v2_signal_events(signal_uid)
        ON UPDATE RESTRICT ON DELETE RESTRICT,

    match_id_hash VARCHAR(12) NOT NULL,
    settled_at TIMESTAMPTZ NOT NULL,

    home_score INTEGER,
    away_score INTEGER,
    result_code TEXT,
    selection_result TEXT,

    settled_odds NUMERIC,
    flat_stake_units NUMERIC,

    source TEXT NOT NULL DEFAULT 'finished_scores',
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    correction_of TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT analysis_v2_settlement_hash_format
        CHECK (match_id_hash ~ '^[0-9a-f]{12}$'),
    CONSTRAINT analysis_v2_selection_result
        CHECK (selection_result IS NULL OR selection_result IN ('WIN', 'LOSS', 'PUSH', 'VOID', 'UNKNOWN'))
);

CREATE INDEX IF NOT EXISTS idx_analysis_v2_settlement_signal
    ON public.analysis_v2_signal_settlement_events(signal_uid, settled_at DESC);
CREATE INDEX IF NOT EXISTS idx_analysis_v2_settlement_match
    ON public.analysis_v2_signal_settlement_events(match_id_hash, settled_at DESC);


-- Hard database guard: trigger facts/history cannot be edited or deleted.
-- Corrections are represented by a new appended event.
CREATE OR REPLACE FUNCTION public.analysis_v2_reject_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'Analysis V2 ledger is append-only; append a new event instead of UPDATE/DELETE';
END;
$$;

DROP TRIGGER IF EXISTS trg_analysis_v2_signal_events_immutable
    ON public.analysis_v2_signal_events;
CREATE TRIGGER trg_analysis_v2_signal_events_immutable
BEFORE UPDATE OR DELETE ON public.analysis_v2_signal_events
FOR EACH ROW EXECUTE FUNCTION public.analysis_v2_reject_mutation();

DROP TRIGGER IF EXISTS trg_analysis_v2_signal_state_events_immutable
    ON public.analysis_v2_signal_state_events;
CREATE TRIGGER trg_analysis_v2_signal_state_events_immutable
BEFORE UPDATE OR DELETE ON public.analysis_v2_signal_state_events
FOR EACH ROW EXECUTE FUNCTION public.analysis_v2_reject_mutation();

DROP TRIGGER IF EXISTS trg_analysis_v2_signal_settlement_events_immutable
    ON public.analysis_v2_signal_settlement_events;
CREATE TRIGGER trg_analysis_v2_signal_settlement_events_immutable
BEFORE UPDATE OR DELETE ON public.analysis_v2_signal_settlement_events
FOR EACH ROW EXECUTE FUNCTION public.analysis_v2_reject_mutation();


-- Settlement must belong to the exact same match as the immutable trigger.
CREATE OR REPLACE FUNCTION public.analysis_v2_validate_settlement_match()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    expected_hash TEXT;
BEGIN
    SELECT match_id_hash INTO expected_hash
    FROM public.analysis_v2_signal_events
    WHERE signal_uid = NEW.signal_uid;

    IF expected_hash IS NULL THEN
        RAISE EXCEPTION 'Unknown Analysis V2 signal_uid: %', NEW.signal_uid;
    END IF;

    IF expected_hash <> NEW.match_id_hash THEN
        RAISE EXCEPTION
            'Settlement match_id_hash mismatch for signal %: expected %, got %',
            NEW.signal_uid, expected_hash, NEW.match_id_hash;
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_analysis_v2_settlement_exact_match
    ON public.analysis_v2_signal_settlement_events;
CREATE TRIGGER trg_analysis_v2_settlement_exact_match
BEFORE INSERT ON public.analysis_v2_signal_settlement_events
FOR EACH ROW EXECUTE FUNCTION public.analysis_v2_validate_settlement_match();


CREATE OR REPLACE VIEW public.analysis_v2_signal_current AS
SELECT
    e.*,
    s.status AS current_status,
    s.observed_at AS current_status_at,
    s.current_odds,
    s.current_pct,
    s.current_amount,
    s.current_volume,
    s.reason_code AS current_reason_code,
    s.reason_detail AS current_reason_detail,
    x.settled_at,
    x.home_score,
    x.away_score,
    x.result_code,
    x.selection_result,
    x.settled_odds,
    x.flat_stake_units
FROM public.analysis_v2_signal_events e
LEFT JOIN LATERAL (
    SELECT st.*
    FROM public.analysis_v2_signal_state_events st
    WHERE st.signal_uid = e.signal_uid
    ORDER BY st.observed_at DESC, st.id DESC
    LIMIT 1
) s ON TRUE
LEFT JOIN LATERAL (
    SELECT se.*
    FROM public.analysis_v2_signal_settlement_events se
    WHERE se.signal_uid = e.signal_uid
    ORDER BY se.settled_at DESC, se.id DESC
    LIMIT 1
) x ON TRUE;

COMMENT ON TABLE public.analysis_v2_signal_events IS
    'Immutable trigger-time facts for every Analysis V2 signal.';
COMMENT ON TABLE public.analysis_v2_signal_state_events IS
    'Append-only lifecycle observations: ACTIVE/WEAKENED/INVALIDATED/SETTLED.';
COMMENT ON TABLE public.analysis_v2_signal_settlement_events IS
    'Append-only exact-match settlement history; never fuzzy-matched by team name.';
