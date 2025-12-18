-- =====================================================
-- UNIQUE CONSTRAINT'LER - TÜM ALARM TABLOLARI
-- Supabase SQL Editor'de çalıştırın
-- =====================================================

-- 1. SHARP ALARMS
ALTER TABLE sharp_alarms 
DROP CONSTRAINT IF EXISTS sharp_alarms_unique;
ALTER TABLE sharp_alarms 
ADD CONSTRAINT sharp_alarms_unique UNIQUE (home, away, market, selection);

-- 2. INSIDER ALARMS
ALTER TABLE insider_alarms 
DROP CONSTRAINT IF EXISTS insider_alarms_unique;
ALTER TABLE insider_alarms 
ADD CONSTRAINT insider_alarms_unique UNIQUE (home, away, market, selection);

-- 3. BIGMONEY ALARMS (match_id_hash kullanıyor)
ALTER TABLE bigmoney_alarms 
DROP CONSTRAINT IF EXISTS bigmoney_alarms_unique;
ALTER TABLE bigmoney_alarms 
ADD CONSTRAINT bigmoney_alarms_unique UNIQUE (match_id_hash, market, selection);

-- 4. VOLUMESHOCK ALARMS (match_id_hash kullanıyor)
ALTER TABLE volumeshock_alarms 
DROP CONSTRAINT IF EXISTS volumeshock_alarms_unique;
ALTER TABLE volumeshock_alarms 
ADD CONSTRAINT volumeshock_alarms_unique UNIQUE (match_id_hash, market, selection);

-- 5. DROPPING ALARMS
ALTER TABLE dropping_alarms 
DROP CONSTRAINT IF EXISTS dropping_alarms_unique;
ALTER TABLE dropping_alarms 
ADD CONSTRAINT dropping_alarms_unique UNIQUE (home, away, market, selection);

-- 6. PUBLICMOVE ALARMS
ALTER TABLE publicmove_alarms 
DROP CONSTRAINT IF EXISTS publicmove_alarms_unique;
ALTER TABLE publicmove_alarms 
ADD CONSTRAINT publicmove_alarms_unique UNIQUE (home, away, market, selection);

-- 7. VOLUMELEADER ALARMS
ALTER TABLE volume_leader_alarms 
DROP CONSTRAINT IF EXISTS volume_leader_alarms_unique;
ALTER TABLE volume_leader_alarms 
ADD CONSTRAINT volume_leader_alarms_unique UNIQUE (home, away, market, old_leader, new_leader);

-- 8. MIM ALARMS (match_id_hash kullanıyor)
ALTER TABLE mim_alarms 
DROP CONSTRAINT IF EXISTS mim_alarms_unique;
ALTER TABLE mim_alarms 
ADD CONSTRAINT mim_alarms_unique UNIQUE (match_id_hash, market);

-- =====================================================
-- KONTROL
-- =====================================================
SELECT 
    tc.table_name, 
    tc.constraint_name, 
    tc.constraint_type
FROM information_schema.table_constraints tc
WHERE tc.table_schema = 'public' 
AND tc.constraint_type = 'UNIQUE'
AND tc.table_name LIKE '%_alarms'
ORDER BY tc.table_name;
