-- MIM alarms tablosuna eksik kolonları ekle
-- Supabase SQL Editor'da çalıştır

-- 1. impact kolonu (eğer yoksa)
ALTER TABLE mim_alarms ADD COLUMN IF NOT EXISTS impact DECIMAL(8,4);

-- 2. prev_volume kolonu
ALTER TABLE mim_alarms ADD COLUMN IF NOT EXISTS prev_volume DECIMAL(14,2);

-- 3. current_volume kolonu
ALTER TABLE mim_alarms ADD COLUMN IF NOT EXISTS current_volume DECIMAL(14,2);

-- 4. incoming_volume kolonu
ALTER TABLE mim_alarms ADD COLUMN IF NOT EXISTS incoming_volume DECIMAL(14,2);

-- 5. total_market_volume kolonu
ALTER TABLE mim_alarms ADD COLUMN IF NOT EXISTS total_market_volume DECIMAL(14,2);

-- Mevcut money_impact değerlerini impact'e kopyala (varsa)
UPDATE mim_alarms SET impact = money_impact WHERE impact IS NULL AND money_impact IS NOT NULL;

-- Kontrol: kolon yapısını göster
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'mim_alarms' 
ORDER BY ordinal_position;
