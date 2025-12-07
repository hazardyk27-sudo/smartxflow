-- SmartXFlow Alarm Tables - UNIQUE Constraint Migration
-- Supabase Dashboard > SQL Editor'da çalıştırın
-- Bu script mevcut tablolara eksik UNIQUE constraint'leri ekler

-- 1. Sharp Alarms - UNIQUE constraint ekle (varsa atla)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'sharp_alarms_unique_key'
    ) THEN
        ALTER TABLE sharp_alarms 
        ADD CONSTRAINT sharp_alarms_unique_key UNIQUE (home, away, market, selection);
        RAISE NOTICE 'sharp_alarms: UNIQUE constraint eklendi';
    ELSE
        RAISE NOTICE 'sharp_alarms: UNIQUE constraint zaten mevcut';
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'sharp_alarms: % - Muhtemelen duplicate data var, önce temizleyin', SQLERRM;
END $$;

-- 2. Insider Alarms - UNIQUE constraint ekle
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'insider_alarms_unique_key'
    ) THEN
        ALTER TABLE insider_alarms 
        ADD CONSTRAINT insider_alarms_unique_key UNIQUE (home, away, market, selection);
        RAISE NOTICE 'insider_alarms: UNIQUE constraint eklendi';
    ELSE
        RAISE NOTICE 'insider_alarms: UNIQUE constraint zaten mevcut';
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'insider_alarms: % - Muhtemelen duplicate data var, önce temizleyin', SQLERRM;
END $$;

-- 3. BigMoney Alarms - UNIQUE constraint ekle (trigger_at dahil)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'bigmoney_alarms_unique_key'
    ) THEN
        ALTER TABLE bigmoney_alarms 
        ADD CONSTRAINT bigmoney_alarms_unique_key UNIQUE (home, away, market, selection, trigger_at);
        RAISE NOTICE 'bigmoney_alarms: UNIQUE constraint eklendi';
    ELSE
        RAISE NOTICE 'bigmoney_alarms: UNIQUE constraint zaten mevcut';
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'bigmoney_alarms: % - Muhtemelen duplicate data var, önce temizleyin', SQLERRM;
END $$;

-- 4. VolumeShock Alarms - UNIQUE constraint ekle
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'volumeshock_alarms_unique_key'
    ) THEN
        ALTER TABLE volumeshock_alarms 
        ADD CONSTRAINT volumeshock_alarms_unique_key UNIQUE (home, away, market, selection);
        RAISE NOTICE 'volumeshock_alarms: UNIQUE constraint eklendi';
    ELSE
        RAISE NOTICE 'volumeshock_alarms: UNIQUE constraint zaten mevcut';
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'volumeshock_alarms: % - Muhtemelen duplicate data var, önce temizleyin', SQLERRM;
END $$;

-- 5. Dropping Alarms - UNIQUE constraint ekle
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'dropping_alarms_unique_key'
    ) THEN
        ALTER TABLE dropping_alarms 
        ADD CONSTRAINT dropping_alarms_unique_key UNIQUE (home, away, market, selection);
        RAISE NOTICE 'dropping_alarms: UNIQUE constraint eklendi';
    ELSE
        RAISE NOTICE 'dropping_alarms: UNIQUE constraint zaten mevcut';
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'dropping_alarms: % - Muhtemelen duplicate data var, önce temizleyin', SQLERRM;
END $$;

-- 6. PublicMove Alarms - UNIQUE constraint ekle
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'publicmove_alarms_unique_key'
    ) THEN
        ALTER TABLE publicmove_alarms 
        ADD CONSTRAINT publicmove_alarms_unique_key UNIQUE (home, away, market, selection);
        RAISE NOTICE 'publicmove_alarms: UNIQUE constraint eklendi';
    ELSE
        RAISE NOTICE 'publicmove_alarms: UNIQUE constraint zaten mevcut';
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'publicmove_alarms: % - Muhtemelen duplicate data var, önce temizleyin', SQLERRM;
END $$;

-- 7. VolumeLeader Alarms - UNIQUE constraint ekle
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'volume_leader_alarms_unique_key'
    ) THEN
        ALTER TABLE volume_leader_alarms 
        ADD CONSTRAINT volume_leader_alarms_unique_key UNIQUE (home, away, market, old_leader, new_leader);
        RAISE NOTICE 'volume_leader_alarms: UNIQUE constraint eklendi';
    ELSE
        RAISE NOTICE 'volume_leader_alarms: UNIQUE constraint zaten mevcut';
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'volume_leader_alarms: % - Muhtemelen duplicate data var, önce temizleyin', SQLERRM;
END $$;

-- 8. Yeni canonical kolon isimleri ekle (eski kolonlar korunur - backward compatibility)
ALTER TABLE sharp_alarms ADD COLUMN IF NOT EXISTS odds_drop_pct NUMERIC;
ALTER TABLE sharp_alarms ADD COLUMN IF NOT EXISTS share_change NUMERIC;
ALTER TABLE sharp_alarms ADD COLUMN IF NOT EXISTS incoming_money NUMERIC;

ALTER TABLE insider_alarms ADD COLUMN IF NOT EXISTS odds_drop_pct NUMERIC;
ALTER TABLE insider_alarms ADD COLUMN IF NOT EXISTS incoming_money NUMERIC;
ALTER TABLE insider_alarms ADD COLUMN IF NOT EXISTS volume_shock NUMERIC;
ALTER TABLE insider_alarms ADD COLUMN IF NOT EXISTS snapshot_count INTEGER;

ALTER TABLE volumeshock_alarms ADD COLUMN IF NOT EXISTS volume_shock NUMERIC;
ALTER TABLE volumeshock_alarms ADD COLUMN IF NOT EXISTS volume_shock_multiplier NUMERIC;

ALTER TABLE dropping_alarms ADD COLUMN IF NOT EXISTS odds_drop_pct NUMERIC;

ALTER TABLE publicmove_alarms ADD COLUMN IF NOT EXISTS trap_score NUMERIC;
ALTER TABLE publicmove_alarms ADD COLUMN IF NOT EXISTS incoming_money NUMERIC;
ALTER TABLE publicmove_alarms ADD COLUMN IF NOT EXISTS odds_drop_pct NUMERIC;
ALTER TABLE publicmove_alarms ADD COLUMN IF NOT EXISTS previous_share NUMERIC;
ALTER TABLE publicmove_alarms ADD COLUMN IF NOT EXISTS current_share NUMERIC;
ALTER TABLE publicmove_alarms ADD COLUMN IF NOT EXISTS share_change NUMERIC;

-- 9. Mevcut verileri temizle (UNIQUE constraint için)
-- DIKKAT: Bu komutlar mevcut alarm verilerini siler!
-- Eğer duplicate data hatası alırsanız, aşağıdaki komutları çalıştırın:
-- TRUNCATE sharp_alarms, insider_alarms, bigmoney_alarms, volumeshock_alarms, dropping_alarms, publicmove_alarms, volume_leader_alarms;

SELECT 'Migration tamamlandi! Lutfen Admin EXE''yi yeniden baslatin.' as result;
