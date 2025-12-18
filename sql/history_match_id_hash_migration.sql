-- ============================================================
-- HISTORY TABLOLARINA match_id_hash KOLONU EKLEME
-- Supabase SQL Editor'de çalıştırın
-- ============================================================

-- 1. Moneyway History tablolarına match_id_hash ekle
ALTER TABLE moneyway_1x2_history ADD COLUMN IF NOT EXISTS match_id_hash VARCHAR(12);
ALTER TABLE moneyway_ou25_history ADD COLUMN IF NOT EXISTS match_id_hash VARCHAR(12);
ALTER TABLE moneyway_btts_history ADD COLUMN IF NOT EXISTS match_id_hash VARCHAR(12);

-- 2. Dropping History tablolarına match_id_hash ekle
ALTER TABLE dropping_1x2_history ADD COLUMN IF NOT EXISTS match_id_hash VARCHAR(12);
ALTER TABLE dropping_ou25_history ADD COLUMN IF NOT EXISTS match_id_hash VARCHAR(12);
ALTER TABLE dropping_btts_history ADD COLUMN IF NOT EXISTS match_id_hash VARCHAR(12);

-- 3. Index oluştur (performans için)
CREATE INDEX IF NOT EXISTS idx_mw_1x2_hist_hash ON moneyway_1x2_history(match_id_hash);
CREATE INDEX IF NOT EXISTS idx_mw_ou25_hist_hash ON moneyway_ou25_history(match_id_hash);
CREATE INDEX IF NOT EXISTS idx_mw_btts_hist_hash ON moneyway_btts_history(match_id_hash);
CREATE INDEX IF NOT EXISTS idx_do_1x2_hist_hash ON dropping_1x2_history(match_id_hash);
CREATE INDEX IF NOT EXISTS idx_do_ou25_hist_hash ON dropping_ou25_history(match_id_hash);
CREATE INDEX IF NOT EXISTS idx_do_btts_hist_hash ON dropping_btts_history(match_id_hash);

-- ============================================================
-- BACKFILL: Mevcut kayıtlar için match_id_hash hesapla
-- Bu işlem Python script ile yapılacak (hash hesaplama gerekli)
-- ============================================================
