-- Speed resolved-market result propagation for tracked wallet activity.
-- Runtime PATCH filter:
--   wallet = ? AND asset = ? AND result IS NULL
--
-- The existing uniqueness index begins (wallet, transaction_hash, asset, ...),
-- so Postgres cannot efficiently seek by wallet+asset. Keep this index partial
-- because resolved historical rows are never targeted by this update path.

CREATE INDEX IF NOT EXISTS tracked_wallet_activity_unresolved_wallet_asset_idx
    ON public.tracked_wallet_activity (wallet, asset)
    WHERE result IS NULL;
