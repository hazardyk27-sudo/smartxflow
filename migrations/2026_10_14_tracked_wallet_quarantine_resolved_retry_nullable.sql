-- Resolved sport-quarantine rows must not be scheduled for another retry.
-- The runtime already writes next_retry_at = NULL when classification becomes
-- verified_football or verified_non_football, but the original V2 schema made
-- the column NOT NULL.  That mismatch caused the whole PATCH to fail and left
-- resolved items stuck as uncertain.
--
-- Keep the real invariant: uncertain rows always need a retry timestamp;
-- resolved rows may clear it.

ALTER TABLE public.tracked_wallet_sport_quarantine
    ALTER COLUMN next_retry_at DROP NOT NULL;

ALTER TABLE public.tracked_wallet_sport_quarantine
    DROP CONSTRAINT IF EXISTS tracked_wallet_sport_quarantine_uncertain_retry_at_chk;

ALTER TABLE public.tracked_wallet_sport_quarantine
    ADD CONSTRAINT tracked_wallet_sport_quarantine_uncertain_retry_at_chk
    CHECK (
        classification <> 'uncertain'
        OR next_retry_at IS NOT NULL
    ) NOT VALID;

ALTER TABLE public.tracked_wallet_sport_quarantine
    VALIDATE CONSTRAINT tracked_wallet_sport_quarantine_uncertain_retry_at_chk;
