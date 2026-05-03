-- SmartXFlow Sharp Alarms Migration V5.0 - ADDITIVE (NON-DESTRUCTIVE)
-- Bu script mevcut veriyi KORUR ve sadece yeni alanları ekler
-- Supabase Dashboard > SQL Editor'da çalıştırın

-- =====================================================
-- SHARP_ALARMS TABLOSU İÇİN YENİ ALAN EKLEMELERİ
-- =====================================================

-- Yeni alanları ekle (varsa hata vermez)
DO $$ 
BEGIN
    -- match_id
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'sharp_alarms' AND column_name = 'match_id') THEN
        ALTER TABLE sharp_alarms ADD COLUMN match_id TEXT;
    END IF;
    
    -- trigger_at (event_time korunur, trigger_at eklenir)
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'sharp_alarms' AND column_name = 'trigger_at') THEN
        ALTER TABLE sharp_alarms ADD COLUMN trigger_at TEXT;
    END IF;
    
    -- alarm_type
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'sharp_alarms' AND column_name = 'alarm_type') THEN
        ALTER TABLE sharp_alarms ADD COLUMN alarm_type TEXT DEFAULT 'sharp';
    END IF;
    
    -- Hacim Şoku alanları
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'sharp_alarms' AND column_name = 'amount_change') THEN
        ALTER TABLE sharp_alarms ADD COLUMN amount_change NUMERIC;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'sharp_alarms' AND column_name = 'avg_last_amounts') THEN
        ALTER TABLE sharp_alarms ADD COLUMN avg_last_amounts NUMERIC;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'sharp_alarms' AND column_name = 'shock_raw') THEN
        ALTER TABLE sharp_alarms ADD COLUMN shock_raw NUMERIC;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'sharp_alarms' AND column_name = 'shock_value') THEN
        ALTER TABLE sharp_alarms ADD COLUMN shock_value NUMERIC;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'sharp_alarms' AND column_name = 'volume_multiplier') THEN
        ALTER TABLE sharp_alarms ADD COLUMN volume_multiplier NUMERIC;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'sharp_alarms' AND column_name = 'max_volume_cap') THEN
        ALTER TABLE sharp_alarms ADD COLUMN max_volume_cap NUMERIC;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'sharp_alarms' AND column_name = 'volume_contrib') THEN
        ALTER TABLE sharp_alarms ADD COLUMN volume_contrib NUMERIC;
    END IF;
    
    -- Oran Düşüşü alanları
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'sharp_alarms' AND column_name = 'previous_odds') THEN
        ALTER TABLE sharp_alarms ADD COLUMN previous_odds NUMERIC;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'sharp_alarms' AND column_name = 'current_odds') THEN
        ALTER TABLE sharp_alarms ADD COLUMN current_odds NUMERIC;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'sharp_alarms' AND column_name = 'drop_pct') THEN
        ALTER TABLE sharp_alarms ADD COLUMN drop_pct NUMERIC;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'sharp_alarms' AND column_name = 'odds_multiplier_base') THEN
        ALTER TABLE sharp_alarms ADD COLUMN odds_multiplier_base NUMERIC;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'sharp_alarms' AND column_name = 'odds_multiplier_bucket') THEN
        ALTER TABLE sharp_alarms ADD COLUMN odds_multiplier_bucket NUMERIC;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'sharp_alarms' AND column_name = 'odds_multiplier') THEN
        ALTER TABLE sharp_alarms ADD COLUMN odds_multiplier NUMERIC;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'sharp_alarms' AND column_name = 'odds_value') THEN
        ALTER TABLE sharp_alarms ADD COLUMN odds_value NUMERIC;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'sharp_alarms' AND column_name = 'max_odds_cap') THEN
        ALTER TABLE sharp_alarms ADD COLUMN max_odds_cap NUMERIC;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'sharp_alarms' AND column_name = 'odds_contrib') THEN
        ALTER TABLE sharp_alarms ADD COLUMN odds_contrib NUMERIC;
    END IF;
    
    -- Pay Değişimi alanları
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'sharp_alarms' AND column_name = 'previous_share') THEN
        ALTER TABLE sharp_alarms ADD COLUMN previous_share NUMERIC;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'sharp_alarms' AND column_name = 'current_share') THEN
        ALTER TABLE sharp_alarms ADD COLUMN current_share NUMERIC;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'sharp_alarms' AND column_name = 'share_diff') THEN
        ALTER TABLE sharp_alarms ADD COLUMN share_diff NUMERIC;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'sharp_alarms' AND column_name = 'share_multiplier') THEN
        ALTER TABLE sharp_alarms ADD COLUMN share_multiplier NUMERIC;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'sharp_alarms' AND column_name = 'share_value') THEN
        ALTER TABLE sharp_alarms ADD COLUMN share_value NUMERIC;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'sharp_alarms' AND column_name = 'max_share_cap') THEN
        ALTER TABLE sharp_alarms ADD COLUMN max_share_cap NUMERIC;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'sharp_alarms' AND column_name = 'share_contrib') THEN
        ALTER TABLE sharp_alarms ADD COLUMN share_contrib NUMERIC;
    END IF;
    
    -- Final Skor alanları
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'sharp_alarms' AND column_name = 'sharp_score') THEN
        ALTER TABLE sharp_alarms ADD COLUMN sharp_score NUMERIC;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'sharp_alarms' AND column_name = 'min_sharp_score') THEN
        ALTER TABLE sharp_alarms ADD COLUMN min_sharp_score NUMERIC;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'sharp_alarms' AND column_name = 'triggered') THEN
        ALTER TABLE sharp_alarms ADD COLUMN triggered BOOLEAN DEFAULT TRUE;
    END IF;
END $$;

-- =====================================================
-- TAMAMLANDI
-- =====================================================
SELECT 'Sharp alarms tablosu başarıyla güncellendi! (V5.0 - Additive Migration)' as result;
