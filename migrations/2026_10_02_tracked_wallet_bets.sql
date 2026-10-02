-- Migration: 2026-10-02
-- Durable canonical lifecycle rows for tracked Polymarket football bettors.
-- Raw tracked_wallet_activity remains the execution/audit ledger; this table
-- is the persistent bettor-level representation consumed by profile/history.

CREATE TABLE IF NOT EXISTS public.tracked_wallet_bets (
    id                    BIGSERIAL PRIMARY KEY,
    wallet                TEXT NOT NULL REFERENCES public.tracked_wallets(wallet) ON DELETE CASCADE,
    bet_key               TEXT NOT NULL,
    asset                 TEXT,
    condition_id          TEXT,
    event_id              TEXT,
    match_key             TEXT,
    match_name            TEXT,
    home                  TEXT,
    away                  TEXT,
    slug                  TEXT,
    kickoff_utc           TIMESTAMPTZ,
    title                 TEXT,
    market_type           TEXT,
    market_label          TEXT,
    selection             TEXT,
    side                  TEXT,
    outcome_raw           TEXT,
    selection_label       TEXT,
    side_label            TEXT,
    bet_label             TEXT,
    lifecycle_status      TEXT,
    result                TEXT,
    status_label          TEXT,
    stake_usdc            NUMERIC,
    sell_proceeds_usdc    NUMERIC,
    redeem_proceeds_usdc  NUMERIC,
    avg_entry_price       NUMERIC,
    avg_entry_decimal     NUMERIC,
    pnl_usdc              NUMERIC,
    pnl_kind              TEXT,
    fill_count            INTEGER DEFAULT 0,
    buy_fill_count        INTEGER DEFAULT 0,
    sell_fill_count       INTEGER DEFAULT 0,
    first_traded_at       TIMESTAMPTZ,
    last_traded_at        TIMESTAMPTZ,
    created_at            TIMESTAMPTZ DEFAULT NOW(),
    updated_at            TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (wallet, bet_key)
);

CREATE INDEX IF NOT EXISTS idx_tw_bets_wallet_last
    ON public.tracked_wallet_bets(wallet, last_traded_at DESC);

CREATE INDEX IF NOT EXISTS idx_tw_bets_wallet_status
    ON public.tracked_wallet_bets(wallet, lifecycle_status);

CREATE INDEX IF NOT EXISTS idx_tw_bets_wallet_asset
    ON public.tracked_wallet_bets(wallet, asset)
    WHERE asset IS NOT NULL;
