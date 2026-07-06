-- Migration: 2026-07-06
-- Takip edilen bahisçiler (tracked wallets) - kullanıcı tanımlı cüzdan takip listesi,
-- cüzdan bazlı tam işlem gecmisi (Polymarket /activity, market-bazli /trades'in
-- eksik saydigi partial-fill'leri de icerir) ve acik pozisyon anlik goruntusu.
-- Supabase dashboard SQL Editor'de calistir.

-- 1. Takip listesi - kullanicinin ekledigi cuzdanlar + verdigi takma ad
CREATE TABLE IF NOT EXISTS public.tracked_wallets (
    wallet        TEXT PRIMARY KEY,
    nickname      TEXT NOT NULL,
    notes         TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Cuzdan bazli tam islem gecmisi - Polymarket /activity (user=) endpoint'inden,
-- sadece futbol maclarina ait TRADE tipi kayitlar. Market-bazli /trades feed'inin
-- toplu (batch) islemlerde diger kullanicilarin payini gizlemesi sorununu asar.
CREATE TABLE IF NOT EXISTS public.tracked_wallet_activity (
    id               BIGSERIAL PRIMARY KEY,
    wallet           TEXT NOT NULL REFERENCES public.tracked_wallets(wallet) ON DELETE CASCADE,
    transaction_hash TEXT NOT NULL,
    asset            TEXT,
    condition_id     TEXT,
    event_id         TEXT,
    title            TEXT,
    slug             TEXT,
    market_type      TEXT,
    selection        TEXT,
    side             TEXT,
    outcome_raw      TEXT,
    amount_usdc      NUMERIC,
    price            NUMERIC,
    size             NUMERIC,
    traded_at        TIMESTAMPTZ NOT NULL,
    scraped_at       TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (wallet, transaction_hash, asset, side)
);

CREATE INDEX IF NOT EXISTS idx_tw_activity_wallet_traded ON public.tracked_wallet_activity(wallet, traded_at);

-- 3. Acik/kapali pozisyon anlik goruntusu - Polymarket /positions (user=) endpoint'inden.
-- Her tarama dongusunde cuzdanin GUNCEL pozisyon listesiyle degistirilir (tam senkron).
CREATE TABLE IF NOT EXISTS public.tracked_wallet_positions (
    id            BIGSERIAL PRIMARY KEY,
    wallet        TEXT NOT NULL REFERENCES public.tracked_wallets(wallet) ON DELETE CASCADE,
    condition_id  TEXT NOT NULL,
    asset         TEXT NOT NULL,
    title         TEXT,
    slug          TEXT,
    event_id      TEXT,
    outcome       TEXT,
    size          NUMERIC,
    avg_price     NUMERIC,
    cur_price     NUMERIC,
    initial_value NUMERIC,
    current_value NUMERIC,
    cash_pnl      NUMERIC,
    percent_pnl   NUMERIC,
    redeemable    BOOLEAN,
    end_date      TEXT,
    updated_at    TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (wallet, condition_id, asset)
);

CREATE INDEX IF NOT EXISTS idx_tw_positions_wallet ON public.tracked_wallet_positions(wallet);
