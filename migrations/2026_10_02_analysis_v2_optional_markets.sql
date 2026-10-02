-- Analysis V2 optional market contract
-- Date: 2026-10-02
--
-- Additive only: no existing table/column is modified or removed.
-- These tables store REAL provider values only. Double Chance values must never
-- be synthesized from 1X2 because synthetic prices have no real matched-money
-- amount/share behind them.

CREATE TABLE IF NOT EXISTS public.moneyway_double_chance (
    id BIGSERIAL PRIMARY KEY,
    league TEXT,
    date TEXT,
    home TEXT,
    away TEXT,
    odds1x TEXT,
    oddsx2 TEXT,
    odds12 TEXT,
    pct1x TEXT,
    pctx2 TEXT,
    pct12 TEXT,
    amt1x TEXT,
    amtx2 TEXT,
    amt12 TEXT,
    volume TEXT,
    CONSTRAINT moneyway_double_chance_match_uniq UNIQUE (league, home, away, date)
);

CREATE TABLE IF NOT EXISTS public.moneyway_double_chance_history (
    id BIGSERIAL PRIMARY KEY,
    match_id_hash VARCHAR(12),
    league TEXT,
    date TEXT,
    home TEXT,
    away TEXT,
    odds1x TEXT,
    oddsx2 TEXT,
    odds12 TEXT,
    pct1x TEXT,
    pctx2 TEXT,
    pct12 TEXT,
    amt1x TEXT,
    amtx2 TEXT,
    amt12 TEXT,
    volume TEXT,
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mw_dc_hist_hash_at
    ON public.moneyway_double_chance_history(match_id_hash, scraped_at DESC);
CREATE INDEX IF NOT EXISTS idx_mw_dc_hist_match_at
    ON public.moneyway_double_chance_history(home, away, scraped_at DESC);

CREATE TABLE IF NOT EXISTS public.moneyway_draw_no_bet (
    id BIGSERIAL PRIMARY KEY,
    league TEXT,
    date TEXT,
    home TEXT,
    away TEXT,
    odds1 TEXT,
    odds2 TEXT,
    pct1 TEXT,
    pct2 TEXT,
    amt1 TEXT,
    amt2 TEXT,
    volume TEXT,
    CONSTRAINT moneyway_draw_no_bet_match_uniq UNIQUE (league, home, away, date)
);

CREATE TABLE IF NOT EXISTS public.moneyway_draw_no_bet_history (
    id BIGSERIAL PRIMARY KEY,
    match_id_hash VARCHAR(12),
    league TEXT,
    date TEXT,
    home TEXT,
    away TEXT,
    odds1 TEXT,
    odds2 TEXT,
    pct1 TEXT,
    pct2 TEXT,
    amt1 TEXT,
    amt2 TEXT,
    volume TEXT,
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mw_dnb_hist_hash_at
    ON public.moneyway_draw_no_bet_history(match_id_hash, scraped_at DESC);
CREATE INDEX IF NOT EXISTS idx_mw_dnb_hist_match_at
    ON public.moneyway_draw_no_bet_history(home, away, scraped_at DESC);

COMMENT ON TABLE public.moneyway_double_chance IS
    'Analysis V2 real-provider Double Chance current state: 1X, X2, 12.';
COMMENT ON TABLE public.moneyway_double_chance_history IS
    'Analysis V2 immutable-ish provider snapshots for Double Chance. Never synthesize from 1X2.';
COMMENT ON TABLE public.moneyway_draw_no_bet IS
    'Analysis V2 real-provider Draw No Bet current state.';
COMMENT ON TABLE public.moneyway_draw_no_bet_history IS
    'Analysis V2 provider snapshot history for Draw No Bet.';
