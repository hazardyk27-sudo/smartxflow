-- =============================================
-- KOLON ADLARINI STANDARTLAŞTIR - Supabase SQL Editor'de çalıştır
-- =============================================

-- Not: Bu script "scrapedat" kolonlarını "scraped_at" olarak değiştirir
-- Önce mevcut kolonları kontrol edin

-- 1. Moneyway History tablolarını güncelle
ALTER TABLE moneyway_1x2_history RENAME COLUMN scrapedat TO scraped_at;
ALTER TABLE moneyway_ou25_history RENAME COLUMN scrapedat TO scraped_at;
ALTER TABLE moneyway_btts_history RENAME COLUMN scrapedat TO scraped_at;

-- 2. Dropping History tablolarını güncelle
ALTER TABLE dropping_1x2_history RENAME COLUMN scrapedat TO scraped_at;
ALTER TABLE dropping_ou25_history RENAME COLUMN scrapedat TO scraped_at;
ALTER TABLE dropping_btts_history RENAME COLUMN scrapedat TO scraped_at;

-- 3. Ana market tablolarını güncelle (varsa)
-- ALTER TABLE moneyway_1x2 RENAME COLUMN scrapedat TO scraped_at;
-- ALTER TABLE moneyway_ou25 RENAME COLUMN scrapedat TO scraped_at;
-- ALTER TABLE moneyway_btts RENAME COLUMN scrapedat TO scraped_at;
-- ALTER TABLE dropping_1x2 RENAME COLUMN scrapedat TO scraped_at;
-- ALTER TABLE dropping_ou25 RENAME COLUMN scrapedat TO scraped_at;
-- ALTER TABLE dropping_btts RENAME COLUMN scrapedat TO scraped_at;

SELECT 'Kolon adları standartlaştırıldı!' as result;
