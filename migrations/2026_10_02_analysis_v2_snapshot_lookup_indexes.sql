-- Analysis V2 Part 3 — moneyway snapshot lookup indexes
-- Date: 2026-10-02
-- Additive only. Do not apply to production without explicit approval.
--
-- Part 3 queries moneyway_snapshots by exact match + canonical market + time,
-- and performs a separate exact-selection lookup for the true opening point.

CREATE INDEX IF NOT EXISTS idx_mw_snap_v2_market_time
    ON public.moneyway_snapshots (
        match_id_hash,
        market,
        scraped_at_utc DESC
    );

CREATE INDEX IF NOT EXISTS idx_mw_snap_v2_selection_time
    ON public.moneyway_snapshots (
        match_id_hash,
        market,
        selection,
        scraped_at_utc DESC
    );
