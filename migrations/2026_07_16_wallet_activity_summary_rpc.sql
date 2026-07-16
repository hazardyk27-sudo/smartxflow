-- RPC: get_wallet_activity_summary
-- DB içinde GROUP BY yaparak her wallet için ~10 satır döndürür.
-- get_wallet_profile içindeki _fetch_activity, 10000 raw satır yerine
-- bu fonksiyonu çağırarak profil yükleme süresini 10-20x hızlandırır.
--
-- Kullanım (Supabase SQL Editor):
--   SELECT * FROM get_wallet_activity_summary('0x...');
--
-- PostgREST üzerinden:
--   POST /rest/v1/rpc/get_wallet_activity_summary
--   {"wallet_addr": "0x..."}

CREATE OR REPLACE FUNCTION get_wallet_activity_summary(wallet_addr TEXT)
RETURNS TABLE(
    asset          TEXT,
    condition_id   TEXT,
    title          TEXT,
    slug           TEXT,
    market_type    TEXT,
    outcome_raw    TEXT,
    selection      TEXT,
    side           TEXT,
    action         TEXT,
    amount_usdc    NUMERIC,
    price          NUMERIC,
    size           NUMERIC,
    traded_at      TEXT,
    result         TEXT,
    fill_count     BIGINT
)
LANGUAGE sql
STABLE
SECURITY DEFINER
AS $$
    SELECT
        asset,
        condition_id,
        MAX(title)          AS title,
        MAX(slug)           AS slug,
        MAX(market_type)    AS market_type,
        outcome_raw,
        MAX(selection)      AS selection,
        MAX(side)           AS side,
        action,
        SUM(amount_usdc)    AS amount_usdc,
        CASE
            WHEN SUM(amount_usdc) > 0
            THEN SUM(price * amount_usdc) / SUM(amount_usdc)
            ELSE AVG(price)
        END                 AS price,
        SUM(size)           AS size,
        MAX(traded_at)      AS traded_at,
        MAX(CASE WHEN result IN ('won', 'lost') THEN result END) AS result,
        COUNT(*)            AS fill_count
    FROM tracked_wallet_activity
    WHERE wallet = lower(wallet_addr)
    GROUP BY asset, condition_id, outcome_raw, action
    ORDER BY SUM(amount_usdc) DESC;
$$;
