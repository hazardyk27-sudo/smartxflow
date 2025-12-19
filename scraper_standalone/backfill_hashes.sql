-- BACKFILL: NULL match_id_hash değerlerini doldur
-- Bu SQL'i Supabase SQL Editor'da çalıştır

-- 1. dropping_1x2_history
UPDATE dropping_1x2_history
SET match_id_hash = LEFT(MD5(
    LOWER(TRIM(COALESCE(league, ''))) || '|' ||
    LOWER(TRIM(REPLACE(REPLACE(COALESCE(home, ''), 'ı', 'i'), 'İ', 'I'))) || '|' ||
    LOWER(TRIM(REPLACE(REPLACE(COALESCE(away, ''), 'ı', 'i'), 'İ', 'I')))
), 12)
WHERE match_id_hash IS NULL;

-- 2. dropping_ou25_history
UPDATE dropping_ou25_history
SET match_id_hash = LEFT(MD5(
    LOWER(TRIM(COALESCE(league, ''))) || '|' ||
    LOWER(TRIM(REPLACE(REPLACE(COALESCE(home, ''), 'ı', 'i'), 'İ', 'I'))) || '|' ||
    LOWER(TRIM(REPLACE(REPLACE(COALESCE(away, ''), 'ı', 'i'), 'İ', 'I')))
), 12)
WHERE match_id_hash IS NULL;

-- 3. dropping_btts_history
UPDATE dropping_btts_history
SET match_id_hash = LEFT(MD5(
    LOWER(TRIM(COALESCE(league, ''))) || '|' ||
    LOWER(TRIM(REPLACE(REPLACE(COALESCE(home, ''), 'ı', 'i'), 'İ', 'I'))) || '|' ||
    LOWER(TRIM(REPLACE(REPLACE(COALESCE(away, ''), 'ı', 'i'), 'İ', 'I')))
), 12)
WHERE match_id_hash IS NULL;

-- 4. moneyway_1x2_history
UPDATE moneyway_1x2_history
SET match_id_hash = LEFT(MD5(
    LOWER(TRIM(COALESCE(league, ''))) || '|' ||
    LOWER(TRIM(REPLACE(REPLACE(COALESCE(home, ''), 'ı', 'i'), 'İ', 'I'))) || '|' ||
    LOWER(TRIM(REPLACE(REPLACE(COALESCE(away, ''), 'ı', 'i'), 'İ', 'I')))
), 12)
WHERE match_id_hash IS NULL;

-- 5. moneyway_ou25_history
UPDATE moneyway_ou25_history
SET match_id_hash = LEFT(MD5(
    LOWER(TRIM(COALESCE(league, ''))) || '|' ||
    LOWER(TRIM(REPLACE(REPLACE(COALESCE(home, ''), 'ı', 'i'), 'İ', 'I'))) || '|' ||
    LOWER(TRIM(REPLACE(REPLACE(COALESCE(away, ''), 'ı', 'i'), 'İ', 'I')))
), 12)
WHERE match_id_hash IS NULL;

-- 6. moneyway_btts_history
UPDATE moneyway_btts_history
SET match_id_hash = LEFT(MD5(
    LOWER(TRIM(COALESCE(league, ''))) || '|' ||
    LOWER(TRIM(REPLACE(REPLACE(COALESCE(home, ''), 'ı', 'i'), 'İ', 'I'))) || '|' ||
    LOWER(TRIM(REPLACE(REPLACE(COALESCE(away, ''), 'ı', 'i'), 'İ', 'I')))
), 12)
WHERE match_id_hash IS NULL;

-- Sonuç kontrolü
SELECT 'dropping_1x2_history' as tablo, COUNT(*) as null_count FROM dropping_1x2_history WHERE match_id_hash IS NULL
UNION ALL
SELECT 'dropping_ou25_history', COUNT(*) FROM dropping_ou25_history WHERE match_id_hash IS NULL
UNION ALL
SELECT 'dropping_btts_history', COUNT(*) FROM dropping_btts_history WHERE match_id_hash IS NULL
UNION ALL
SELECT 'moneyway_1x2_history', COUNT(*) FROM moneyway_1x2_history WHERE match_id_hash IS NULL
UNION ALL
SELECT 'moneyway_ou25_history', COUNT(*) FROM moneyway_ou25_history WHERE match_id_hash IS NULL
UNION ALL
SELECT 'moneyway_btts_history', COUNT(*) FROM moneyway_btts_history WHERE match_id_hash IS NULL;
