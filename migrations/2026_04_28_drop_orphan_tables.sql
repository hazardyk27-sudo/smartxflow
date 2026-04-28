-- ============================================================================
-- Migration: Atil tablolari kaldir (Task #156 - Tablo Temizligi ve Duzeni)
-- Tarih: 2026-04-28
--
-- Bu migration su 8 tabloyu DROP eder. Migration calismadan once veriler
-- REST API uzerinden zaten temizlendi (~143K satir). Tablo yapilari
-- silinmek uzere bekliyor.
--
-- Calistirma: Supabase Dashboard > SQL Editor > paste & run
-- Geri alma: Yedekten geri yukleme gerekir (DROP CASCADE geri alinmaz!)
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- 1) Eski PascalCase moneyway history tablolari (3 adet)
--    Yeni snake_case karsiliklari: moneyway_1x2_history, moneyway_btts_history,
--    moneyway_ou25_history. Hicbir kod artik _hist tablolarina yazmiyor/okumuyor.
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS moneyway_1x2_hist CASCADE;
DROP TABLE IF EXISTS moneyway_btts_hist CASCADE;
DROP TABLE IF EXISTS moneyway_ou25_hist CASCADE;

-- ----------------------------------------------------------------------------
-- 2) Eski PascalCase dropping history tablolari (3 adet)
--    Yeni snake_case karsiliklari: dropping_1x2_history, dropping_btts_history,
--    dropping_ou25_history. Yine _hist'lere referans yok.
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS dropping_1x2_hist CASCADE;
DROP TABLE IF EXISTS dropping_btts_hist CASCADE;
DROP TABLE IF EXISTS dropping_ou25_hist CASCADE;

-- ----------------------------------------------------------------------------
-- 3) alarm_config: Sadece sql/create_missing_tables.sql'de tanim, kodda 0 ref.
--    Hicbir alarm motoru bu tabloyu okumuyor/yazmiyor.
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS alarm_config CASCADE;

-- ----------------------------------------------------------------------------
-- 4) match_favorites: Eski device_id-bazli favori sistemi.
--    Yeni sistem: license_favorites (license_key + match_key).
--    Kodda 0 referans, 71 satirlik veri device_id'liydi -> mapping yok,
--    migrate edilemezdi. Veri zaten silindi.
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS match_favorites CASCADE;

COMMIT;

-- Dogrulama:
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN (
    'moneyway_1x2_hist','moneyway_btts_hist','moneyway_ou25_hist',
    'dropping_1x2_hist','dropping_btts_hist','dropping_ou25_hist',
    'alarm_config','match_favorites'
  );
-- Beklenen: 0 satir
