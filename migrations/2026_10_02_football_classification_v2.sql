-- Migration: 2026-10-02
-- Football Classification Gate V2.
-- Nothing uncertain is deleted. VERIFIED_NON_FOOTBALL is excluded from the
-- football product, while uncertain source rows are quarantined for retry.

CREATE TABLE IF NOT EXISTS public.polymarket_sport_registry (
    identity_type       TEXT NOT NULL CHECK (identity_type IN ('event','condition')),
    identity_id         TEXT NOT NULL,
    event_id            TEXT,
    classification      TEXT NOT NULL CHECK (
        classification IN ('verified_football','verified_non_football','uncertain')
    ),
    classifier_version  TEXT NOT NULL DEFAULT 'gamma-soccer-v2',
    source              TEXT NOT NULL,
    evidence            JSONB NOT NULL DEFAULT '{}'::jsonb,
    first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_checked_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    next_retry_at       TIMESTAMPTZ,
    PRIMARY KEY (identity_type, identity_id)
);

CREATE INDEX IF NOT EXISTS idx_poly_sport_registry_event
    ON public.polymarket_sport_registry(event_id);

CREATE INDEX IF NOT EXISTS idx_poly_sport_registry_class
    ON public.polymarket_sport_registry(classification, next_retry_at);

CREATE TABLE IF NOT EXISTS public.tracked_wallet_sport_quarantine (
    wallet              TEXT NOT NULL REFERENCES public.tracked_wallets(wallet) ON DELETE CASCADE,
    item_kind           TEXT NOT NULL CHECK (item_kind IN ('activity','redeem','position')),
    item_key            TEXT NOT NULL,
    asset               TEXT,
    condition_id        TEXT,
    event_id            TEXT,
    title               TEXT,
    slug                TEXT,
    traded_at           TIMESTAMPTZ,
    classification      TEXT NOT NULL DEFAULT 'uncertain' CHECK (
        classification IN ('uncertain','verified_football','verified_non_football')
    ),
    reason              TEXT,
    raw_payload         JSONB NOT NULL,
    attempt_count       INTEGER NOT NULL DEFAULT 0,
    first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    next_retry_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at         TIMESTAMPTZ,
    PRIMARY KEY (wallet, item_kind, item_key)
);

CREATE INDEX IF NOT EXISTS idx_tw_sport_quarantine_retry
    ON public.tracked_wallet_sport_quarantine(classification, next_retry_at)
    WHERE classification = 'uncertain';

ALTER TABLE public.tracked_wallet_bets
    ADD COLUMN IF NOT EXISTS sport_classification TEXT,
    ADD COLUMN IF NOT EXISTS sport_verified_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS sport_classification_source TEXT;

CREATE INDEX IF NOT EXISTS idx_tw_bets_sport_classification
    ON public.tracked_wallet_bets(wallet, sport_classification, last_traded_at DESC);
