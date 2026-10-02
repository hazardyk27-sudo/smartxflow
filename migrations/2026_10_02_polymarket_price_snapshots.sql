-- Migration: 2026-10-02
-- Market-price history for tracked Polymarket bettor outcomes.
-- Snapshots are market-level (asset/token), so multiple tracked wallets betting
-- the same outcome share one price series.

CREATE TABLE IF NOT EXISTS public.polymarket_price_snapshots (
    asset              TEXT NOT NULL,
    bucket_at          TIMESTAMPTZ NOT NULL,
    observed_at        TIMESTAMPTZ NOT NULL,
    condition_id       TEXT,
    event_id           TEXT,
    kickoff_utc        TIMESTAMPTZ,
    market_price       NUMERIC NOT NULL CHECK (market_price >= 0 AND market_price <= 1),
    decimal_odds       NUMERIC,
    source             TEXT NOT NULL DEFAULT 'clob_midpoint',
    cadence_minutes    INTEGER NOT NULL,
    is_pre_kickoff     BOOLEAN NOT NULL DEFAULT TRUE,
    hours_to_kickoff   NUMERIC,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (asset, bucket_at)
);

CREATE INDEX IF NOT EXISTS idx_poly_price_snapshots_asset_observed
    ON public.polymarket_price_snapshots(asset, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_poly_price_snapshots_event_observed
    ON public.polymarket_price_snapshots(event_id, observed_at DESC)
    WHERE event_id IS NOT NULL;

ALTER TABLE public.tracked_wallet_bets
    ADD COLUMN IF NOT EXISTS latest_market_price NUMERIC,
    ADD COLUMN IF NOT EXISTS latest_market_decimal NUMERIC,
    ADD COLUMN IF NOT EXISTS latest_market_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS closing_price NUMERIC,
    ADD COLUMN IF NOT EXISTS closing_decimal NUMERIC,
    ADD COLUMN IF NOT EXISTS closing_observed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS clv_probability_pp NUMERIC,
    ADD COLUMN IF NOT EXISTS clv_pct NUMERIC;

CREATE INDEX IF NOT EXISTS idx_tw_bets_closing_pending
    ON public.tracked_wallet_bets(kickoff_utc, asset)
    WHERE closing_price IS NULL AND asset IS NOT NULL;
