-- SmartXFlow Supabase Temizlik SQL'i
-- Bu dosya kullanılmayan yapıları temizler
-- Supabase Dashboard > SQL Editor'da çalıştırın

-- ==============================================================================
-- 1. AKTİF KULLANILAN TABLOLAR (SİLMEYİN!)
-- ==============================================================================
-- matches                    - Maç bilgileri
-- odds_snapshots             - Oran snapshot'ları
-- moneyway_1x2_history       - 1X2 Moneyway tarihçe
-- moneyway_ou25_history      - O/U 2.5 Moneyway tarihçe
-- moneyway_btts_history      - BTTS Moneyway tarihçe
-- dropping_1x2_history       - 1X2 Dropping tarihçe
-- dropping_ou25_history      - O/U 2.5 Dropping tarihçe
-- dropping_btts_history      - BTTS Dropping tarihçe
-- alarm_settings             - Alarm ayarları (config)
-- sharp_alarms               - Sharp Money alarmları
-- insider_alarms             - Insider alarmları
-- bigmoney_alarms            - Big Money alarmları
-- volumeshock_alarms         - Volume Shock alarmları
-- dropping_alarms            - Dropping Odds alarmları
-- publicmove_alarms          - Public Move alarmları
-- volume_leader_alarms       - Volume Leader alarmları

-- ==============================================================================
-- 2. MEVCUT TABLOLARI LISTELE (önce bu sorguyu çalıştırın)
-- ==============================================================================
SELECT 
    table_name,
    CASE 
        WHEN table_name IN (
            'matches', 'odds_snapshots', 'alarm_settings',
            'moneyway_1x2_history', 'moneyway_ou25_history', 'moneyway_btts_history',
            'dropping_1x2_history', 'dropping_ou25_history', 'dropping_btts_history',
            'sharp_alarms', 'insider_alarms', 'bigmoney_alarms', 
            'volumeshock_alarms', 'dropping_alarms', 'publicmove_alarms', 'volume_leader_alarms'
        ) THEN 'ACTIVE - KEEP'
        ELSE 'UNUSED - CAN DELETE'
    END as status
FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_type = 'BASE TABLE'
ORDER BY status, table_name;

-- ==============================================================================
-- 3. MEVCUT VIEW'LARI LISTELE
-- ==============================================================================
SELECT 
    table_name as view_name,
    'VIEW - CHECK IF NEEDED' as status
FROM information_schema.views 
WHERE table_schema = 'public';

-- ==============================================================================
-- 4. MEVCUT FUNCTION'LARI LISTELE
-- ==============================================================================
SELECT 
    routine_name as function_name,
    routine_type,
    'FUNCTION - CHECK IF NEEDED' as status
FROM information_schema.routines 
WHERE routine_schema = 'public';

-- ==============================================================================
-- 5. MEVCUT TRIGGER'LARI LISTELE
-- ==============================================================================
SELECT 
    trigger_name,
    event_object_table as table_name,
    'TRIGGER - CHECK IF NEEDED' as status
FROM information_schema.triggers 
WHERE trigger_schema = 'public';

-- ==============================================================================
-- 6. MEVCUT POLICY'LERI LISTELE
-- ==============================================================================
SELECT 
    polname as policy_name,
    relname as table_name,
    CASE polcmd 
        WHEN 'r' THEN 'SELECT'
        WHEN 'a' THEN 'INSERT'
        WHEN 'w' THEN 'UPDATE'
        WHEN 'd' THEN 'DELETE'
        WHEN '*' THEN 'ALL'
    END as command
FROM pg_policy 
JOIN pg_class ON pg_policy.polrelid = pg_class.oid
JOIN pg_namespace ON pg_class.relnamespace = pg_namespace.oid
WHERE nspname = 'public'
ORDER BY table_name, policy_name;

-- ==============================================================================
-- 7. ESKİ / KULLANILMAYAN TABLOLARI SİL (DİKKATLİ OLUN!)
-- ==============================================================================
-- Önce yukarıdaki sorguları çalıştırın ve "UNUSED - CAN DELETE" olanları görün
-- Sonra aşağıdaki satırları uncomment edip çalıştırın

-- Olası eski tablolar (varsa silin):
-- DROP TABLE IF EXISTS alarms CASCADE;
-- DROP TABLE IF EXISTS alarm_logs CASCADE;
-- DROP TABLE IF EXISTS sharp_alarms_old CASCADE;
-- DROP TABLE IF EXISTS test_alarms CASCADE;
-- DROP TABLE IF EXISTS alarm_history CASCADE;
-- DROP TABLE IF EXISTS old_matches CASCADE;
-- DROP TABLE IF EXISTS matches_backup CASCADE;
-- DROP TABLE IF EXISTS odds_history CASCADE;
-- DROP TABLE IF EXISTS legacy_alarms CASCADE;

-- ==============================================================================
-- 8. ESKİ VIEW'LARI SİL
-- ==============================================================================
-- DROP VIEW IF EXISTS v_all_alarms CASCADE;
-- DROP VIEW IF EXISTS v_active_matches CASCADE;
-- DROP VIEW IF EXISTS v_match_summary CASCADE;

-- ==============================================================================
-- 9. ESKİ FUNCTION'LARI SİL
-- ==============================================================================
-- DROP FUNCTION IF EXISTS cleanup_old_data() CASCADE;
-- DROP FUNCTION IF EXISTS get_latest_odds() CASCADE;
-- DROP FUNCTION IF EXISTS calculate_sharp() CASCADE;

-- ==============================================================================
-- 10. ESKİ TRIGGER'LARI SİL
-- ==============================================================================
-- DROP TRIGGER IF EXISTS tr_alarm_log ON alarms;
-- DROP TRIGGER IF EXISTS tr_update_timestamp ON matches;

-- ==============================================================================
-- 11. GEREKSIZ POLICY'LERI SİL
-- ==============================================================================
-- Aktif tablolar için sadece "Allow all for X" policy'leri gerekli
-- Diğer policy'ler silinebilir

-- ==============================================================================
-- 12. FİNAL TEMİZLİK KONTROLÜ
-- ==============================================================================
-- Temizlikten sonra bu sorguyu çalıştırarak sadece aktif tabloların kaldığını doğrulayın:

-- SELECT table_name FROM information_schema.tables 
-- WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
-- ORDER BY table_name;

-- Beklenen sonuç (16 tablo):
-- alarm_settings
-- bigmoney_alarms
-- dropping_1x2_history
-- dropping_alarms
-- dropping_btts_history
-- dropping_ou25_history
-- insider_alarms
-- matches
-- moneyway_1x2_history
-- moneyway_btts_history
-- moneyway_ou25_history
-- odds_snapshots
-- publicmove_alarms
-- sharp_alarms
-- volume_leader_alarms
-- volumeshock_alarms
