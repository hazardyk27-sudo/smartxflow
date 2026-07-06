-- Migration: 2026-07-06 (ek)
-- Task #264: "Handicapci" cuzdaninda Isabet Orani %0 gorunuyordu cunku kazanan
-- pozisyonlar REDEEM edilince /positions'tan tamamen kayboluyor ve hic bir yerde
-- kazanildigi kaydedilmiyordu (survivorship bias). Bu migration REDEEM
-- olaylarini kalici olarak saklayan bir tablo ekliyor + activity tablosuna
-- ham alim/satim (BUY/SELL) icin ayri bir `action` kolonu ekliyor (eskiden
-- `side` kolonu OU25/BTTS gibi piyasalarda sonuc etiketini tasiyip 1x2'de ham
-- yonu tasiyordu, ikisi karisiyordu).
-- Supabase dashboard SQL Editor'de calistir.

ALTER TABLE public.tracked_wallet_activity
    ADD COLUMN IF NOT EXISTS action TEXT;

-- Eski UNIQUE (wallet, transaction_hash, asset, side) kisitlamasi `side`'i
-- ham alim/satim yonu olarak kullaniyordu (1x2 icin). Artik `side` sadece
-- sonuc etiketi tasiyor (1x2'de hep NULL) ve ham yon `action` kolonunda, bu
-- yuzden kisitlamayi `action` da icerecek sekilde genisletiyoruz - aksi
-- halde ayni tx_hash+asset'e ait olasi BUY ve SELL kayitlari birbirinin
-- uzerine yazabilirdi.
-- NOT: Postgres'te UNIQUE kisitlamasinda NULL hicbir zaman NULL'a esit
-- sayilmaz, yani `side` kolonu NULL kalirsa (1x2 piyasalari icin oyle) ayni
-- islem tekrar tekrar INSERT edilebilir (upsert conflict eslesmez). Bu yuzden
-- uygulama katmani (polymarket_scraper.py) 1x2 icin `side`'i NULL yerine ""
-- (bos string) olarak yaziyor - bu kisitlama sadece bos-string'i non-null
-- sentinel olarak kullanan satirlarla dogru calisir.
ALTER TABLE public.tracked_wallet_activity
    DROP CONSTRAINT IF EXISTS tracked_wallet_activity_wallet_transaction_hash_asset_side_key;
ALTER TABLE public.tracked_wallet_activity
    ADD CONSTRAINT tracked_wallet_activity_wallet_txhash_asset_side_action_key
    UNIQUE (wallet, transaction_hash, asset, side, action);

-- Eger bu migration'dan once zaten side=NULL olan 1x2 satirlari varsa (eski
-- scraper kodu), onlari da "" sentinel'e cevir ki gelecekteki upsert'ler
-- dogru satirla eslessin ve duplicate birikmesin.
UPDATE public.tracked_wallet_activity SET side = '' WHERE side IS NULL;

-- Cuzdanin kazandigi ve REDEEM ettigi (nakde cevirdigi) piyasalarin kalici
-- kaydi. /positions anlik goruntusunden farkli olarak buradaki kayitlar asla
-- silinmez, boylece "kazandi ama redeem etti, artik pozisyonlarda gorunmuyor"
-- durumu Isabet Orani hesabinda kaybolmaz.
CREATE TABLE IF NOT EXISTS public.tracked_wallet_redeems (
    id               BIGSERIAL PRIMARY KEY,
    wallet           TEXT NOT NULL REFERENCES public.tracked_wallets(wallet) ON DELETE CASCADE,
    transaction_hash TEXT NOT NULL,
    condition_id     TEXT NOT NULL,
    asset            TEXT,
    title            TEXT,
    slug             TEXT,
    event_id         TEXT,
    amount_usdc      NUMERIC,
    traded_at        TIMESTAMPTZ NOT NULL,
    scraped_at       TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (wallet, transaction_hash, condition_id)
);

CREATE INDEX IF NOT EXISTS idx_tw_redeems_wallet ON public.tracked_wallet_redeems(wallet);
CREATE INDEX IF NOT EXISTS idx_tw_redeems_wallet_traded ON public.tracked_wallet_redeems(wallet, traded_at);
