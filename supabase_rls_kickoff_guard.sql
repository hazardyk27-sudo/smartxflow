-- =====================================================
-- SmartXFlow: Prematch Data Guard - RLS Policies
-- Maç başladıktan sonra veri eklenmesini engeller
-- =====================================================

-- 1) Arbworld date formatını ("03.Dec 14:00:00") UTC timestamp'e çeviren fonksiyon
CREATE OR REPLACE FUNCTION parse_arbworld_date(arbworld_date TEXT)
RETURNS TIMESTAMP WITH TIME ZONE AS $$
DECLARE
    day_num INT;
    month_abbr TEXT;
    time_part TEXT;
    month_num INT;
    current_year INT;
    result_ts TIMESTAMP WITH TIME ZONE;
BEGIN
    IF arbworld_date IS NULL OR arbworld_date = '' THEN
        RETURN NULL;
    END IF;
    
    -- Format: "03.Dec 14:00:00"
    day_num := CAST(SPLIT_PART(arbworld_date, '.', 1) AS INT);
    month_abbr := SPLIT_PART(SPLIT_PART(arbworld_date, '.', 2), ' ', 1);
    time_part := SPLIT_PART(arbworld_date, ' ', 2);
    
    -- Month mapping
    month_num := CASE month_abbr
        WHEN 'Jan' THEN 1 WHEN 'Feb' THEN 2 WHEN 'Mar' THEN 3
        WHEN 'Apr' THEN 4 WHEN 'May' THEN 5 WHEN 'Jun' THEN 6
        WHEN 'Jul' THEN 7 WHEN 'Aug' THEN 8 WHEN 'Sep' THEN 9
        WHEN 'Oct' THEN 10 WHEN 'Nov' THEN 11 WHEN 'Dec' THEN 12
        ELSE NULL
    END;
    
    IF month_num IS NULL THEN
        RETURN NULL;
    END IF;
    
    current_year := EXTRACT(YEAR FROM NOW());
    
    -- Build timestamp (Arbworld dates are UTC)
    result_ts := MAKE_TIMESTAMPTZ(
        current_year, 
        month_num, 
        day_num, 
        CAST(SPLIT_PART(time_part, ':', 1) AS INT),
        CAST(SPLIT_PART(time_part, ':', 2) AS INT),
        CAST(COALESCE(NULLIF(SPLIT_PART(time_part, ':', 3), ''), '0') AS DOUBLE PRECISION),
        'UTC'
    );
    
    -- Year rollover: if date is more than 6 months in future, use previous year
    IF result_ts > NOW() + INTERVAL '6 months' THEN
        result_ts := result_ts - INTERVAL '1 year';
    END IF;
    
    RETURN result_ts;
EXCEPTION
    WHEN OTHERS THEN
        RETURN NULL;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- 2) Maç başlayıp başlamadığını kontrol eden fonksiyon
-- Arbworld verileri UTC, şu anki zaman da UTC'de karşılaştırılır
CREATE OR REPLACE FUNCTION is_match_not_started(arbworld_date TEXT)
RETURNS BOOLEAN AS $$
DECLARE
    kickoff_utc TIMESTAMP WITH TIME ZONE;
BEGIN
    kickoff_utc := parse_arbworld_date(arbworld_date);
    
    IF kickoff_utc IS NULL THEN
        -- Parse edemediyse, güvenli tarafta kal ve izin ver
        RETURN TRUE;
    END IF;
    
    -- Maç henüz başlamamışsa TRUE döner
    RETURN NOW() < kickoff_utc;
END;
$$ LANGUAGE plpgsql STABLE;

-- 3) RLS'i etkinleştir (her history tablosu için)
ALTER TABLE moneyway_1x2_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE moneyway_ou25_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE moneyway_btts_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE dropping_1x2_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE dropping_ou25_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE dropping_btts_history ENABLE ROW LEVEL SECURITY;

-- 4) SELECT için tam erişim (okumaya izin ver)
CREATE POLICY "Allow all reads" ON moneyway_1x2_history FOR SELECT USING (true);
CREATE POLICY "Allow all reads" ON moneyway_ou25_history FOR SELECT USING (true);
CREATE POLICY "Allow all reads" ON moneyway_btts_history FOR SELECT USING (true);
CREATE POLICY "Allow all reads" ON dropping_1x2_history FOR SELECT USING (true);
CREATE POLICY "Allow all reads" ON dropping_ou25_history FOR SELECT USING (true);
CREATE POLICY "Allow all reads" ON dropping_btts_history FOR SELECT USING (true);

-- 5) INSERT için prematch guard (sadece maç başlamadan önce izin ver)
CREATE POLICY "Prematch insert only" ON moneyway_1x2_history 
    FOR INSERT WITH CHECK (is_match_not_started(date));

CREATE POLICY "Prematch insert only" ON moneyway_ou25_history 
    FOR INSERT WITH CHECK (is_match_not_started(date));

CREATE POLICY "Prematch insert only" ON moneyway_btts_history 
    FOR INSERT WITH CHECK (is_match_not_started(date));

CREATE POLICY "Prematch insert only" ON dropping_1x2_history 
    FOR INSERT WITH CHECK (is_match_not_started(date));

CREATE POLICY "Prematch insert only" ON dropping_ou25_history 
    FOR INSERT WITH CHECK (is_match_not_started(date));

CREATE POLICY "Prematch insert only" ON dropping_btts_history 
    FOR INSERT WITH CHECK (is_match_not_started(date));

-- =====================================================
-- TEST: Fonksiyonları test et
-- =====================================================
-- SELECT parse_arbworld_date('03.Dec 14:00:00');
-- SELECT is_match_not_started('03.Dec 14:00:00');
-- SELECT is_match_not_started('31.Dec 23:59:00');

-- =====================================================
-- ROLLBACK (gerekirse RLS'i kaldırmak için)
-- =====================================================
-- DROP POLICY IF EXISTS "Allow all reads" ON moneyway_1x2_history;
-- DROP POLICY IF EXISTS "Prematch insert only" ON moneyway_1x2_history;
-- ... (diğer tablolar için de aynı)
-- ALTER TABLE moneyway_1x2_history DISABLE ROW LEVEL SECURITY;
