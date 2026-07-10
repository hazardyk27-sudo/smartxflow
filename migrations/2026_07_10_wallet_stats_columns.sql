-- Pre-computed stat columns for tracked_wallets.
-- Scraper fills these after each wallet sync; profile endpoint reads them
-- instantly instead of re-computing from raw rows on every request.
-- Run in Supabase SQL Editor.

ALTER TABLE tracked_wallets
  ADD COLUMN IF NOT EXISTS win_rate              NUMERIC,
  ADD COLUMN IF NOT EXISTS resolved_won          INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS resolved_lost         INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS resolved_total        INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS trade_count           INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS total_invested_usdc   NUMERIC DEFAULT 0,
  ADD COLUMN IF NOT EXISTS avg_bet_size_usdc     NUMERIC DEFAULT 0,
  ADD COLUMN IF NOT EXISTS avg_price             NUMERIC DEFAULT 0,
  ADD COLUMN IF NOT EXISTS avg_price_decimal     NUMERIC DEFAULT 0,
  ADD COLUMN IF NOT EXISTS open_position_count   INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS open_exposure_usdc    NUMERIC DEFAULT 0,
  ADD COLUMN IF NOT EXISTS last_synced_at        TIMESTAMPTZ;
