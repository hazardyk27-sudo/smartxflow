-- Migration: 2026-07-04
-- Polymarket trade ledger (confirmed/matched trades, incremental scraper)
-- Supabase dashboard SQL Editor'de calistir

-- 1. Maclar (event bazli, tekrar tekrar Gamma API'ye sormamak icin hafif cache)
CREATE TABLE IF NOT EXISTS public.polymarket_matches (
    event_id      TEXT PRIMARY KEY,
    slug          TEXT,
    home          TEXT,
    away          TEXT,
    kickoff_utc   TIMESTAMPTZ,
    sport         TEXT DEFAULT 'soccer',
    last_seen_at  TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Trade ledger — her satir tek bir eslesmis (confirmed) trade
CREATE TABLE IF NOT EXISTS public.polymarket_trades (
    id               BIGSERIAL PRIMARY KEY,
    transaction_hash TEXT NOT NULL,
    asset            TEXT,
    wallet           TEXT NOT NULL,
    pseudonym        TEXT,
    event_id         TEXT,
    condition_id     TEXT NOT NULL,
    market_type      TEXT NOT NULL,   -- 1x2 | ou25 | btts
    selection        TEXT,
    side             TEXT,
    outcome_raw      TEXT,
    amount_usdc      NUMERIC,
    price            NUMERIC,
    size             NUMERIC,
    traded_at        TIMESTAMPTZ NOT NULL,
    match_phase      TEXT,            -- prematch | live
    scraped_at       TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (transaction_hash, wallet, asset, side)
);

-- 3. Checkpoint/aggregate sorgulari icin indexler
CREATE INDEX IF NOT EXISTS idx_poly_trades_condition_traded ON public.polymarket_trades(condition_id, traded_at);
CREATE INDEX IF NOT EXISTS idx_poly_trades_event            ON public.polymarket_trades(event_id);
CREATE INDEX IF NOT EXISTS idx_poly_trades_traded_at         ON public.polymarket_trades(traded_at);
CREATE INDEX IF NOT EXISTS idx_poly_trades_phase             ON public.polymarket_trades(match_phase);
