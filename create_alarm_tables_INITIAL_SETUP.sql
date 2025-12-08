-- SmartXFlow Alarm Tabloları V5.0 - UI ALAN ADLARIYLA UYUMLU
-- Supabase Dashboard > SQL Editor'da çalıştırın
-- TÜM ALAN ADLARI UI İLE BİREBİR AYNI (Admin.exe bu alan adlarını kullanır)
-- NOT: Bu script tabloları DROP eder. Mevcut veriyi korumak için ADD COLUMN migration kullanın.

-- =====================================================
-- ADIM 1: ESKİ TABLOLARI SİL (TEMİZ BAŞLANGIÇ)
-- DİKKAT: Mevcut veri silinir! Sadece ilk kurulumda kullanın.
-- =====================================================
DROP TABLE IF EXISTS sharp_alarms CASCADE;
DROP TABLE IF EXISTS insider_alarms CASCADE;
DROP TABLE IF EXISTS bigmoney_alarms CASCADE;
DROP TABLE IF EXISTS volumeshock_alarms CASCADE;
DROP TABLE IF EXISTS dropping_alarms CASCADE;
DROP TABLE IF EXISTS publicmove_alarms CASCADE;
DROP TABLE IF EXISTS volume_leader_alarms CASCADE;

-- =====================================================
-- ADIM 2: YENİ TABLOLAR (ADMIN.EXE İLE BİREBİR AYNI)
-- =====================================================

-- 1. SHARP ALARMS - UI ALAN ADLARIYLA UYUMLU
CREATE TABLE sharp_alarms (
    id SERIAL PRIMARY KEY,
    match_id TEXT,
    home TEXT NOT NULL,
    away TEXT NOT NULL,
    market TEXT NOT NULL,
    selection TEXT NOT NULL,
    match_date TEXT,
    event_time TEXT,
    trigger_at TEXT,
    created_at TEXT,
    alarm_type TEXT DEFAULT 'sharp',
    
    -- Hacim Şoku (Volume Shock) - UI alan adları
    amount_change NUMERIC,
    avg_last_amounts NUMERIC,
    shock_raw NUMERIC,
    volume_multiplier NUMERIC,
    shock_value NUMERIC,
    max_volume_cap NUMERIC,
    volume_contrib NUMERIC,
    
    -- Oran Düşüşü (Odds Drop) - UI alan adları
    previous_odds NUMERIC,
    current_odds NUMERIC,
    drop_pct NUMERIC,
    odds_multiplier_base NUMERIC,
    odds_multiplier_bucket NUMERIC,
    odds_multiplier NUMERIC,
    odds_value NUMERIC,
    max_odds_cap NUMERIC,
    odds_contrib NUMERIC,
    
    -- Pay Değişimi (Share Change) - UI alan adları
    previous_share NUMERIC,
    current_share NUMERIC,
    share_diff NUMERIC,
    share_multiplier NUMERIC,
    share_value NUMERIC,
    max_share_cap NUMERIC,
    share_contrib NUMERIC,
    
    -- Final Skor
    sharp_score NUMERIC,
    min_sharp_score NUMERIC,
    triggered BOOLEAN DEFAULT TRUE,
    
    UNIQUE(home, away, market, selection)
);

-- 2. INSIDER ALARMS
CREATE TABLE insider_alarms (
    id SERIAL PRIMARY KEY,
    match_id TEXT,
    home TEXT NOT NULL,
    away TEXT NOT NULL,
    market TEXT NOT NULL,
    selection TEXT NOT NULL,
    match_date TEXT,
    event_time TEXT,
    trigger_at TEXT,
    created_at TEXT,
    hacim_sok NUMERIC,
    oran_dusus_pct NUMERIC,
    gelen_para NUMERIC,
    opening_odds NUMERIC,
    current_odds NUMERIC,
    last_odds NUMERIC,
    drop_time TEXT,
    drop_index INTEGER,
    window_start_odds NUMERIC,
    window_end_odds NUMERIC,
    window_odds_drop_pct NUMERIC,
    snapshot_details JSONB,
    insider_hacim_sok_esigi NUMERIC,
    insider_oran_dusus_esigi NUMERIC,
    insider_sure_dakika NUMERIC,
    insider_max_para NUMERIC,
    insider_max_odds_esigi NUMERIC,
    snapshot_count INTEGER,
    triggered BOOLEAN DEFAULT TRUE,
    UNIQUE(home, away, market, selection)
);

-- 3. BIGMONEY ALARMS
CREATE TABLE bigmoney_alarms (
    id SERIAL PRIMARY KEY,
    match_id TEXT,
    home TEXT NOT NULL,
    away TEXT NOT NULL,
    market TEXT NOT NULL,
    selection TEXT NOT NULL,
    match_date TEXT,
    event_time TEXT,
    trigger_at TEXT,
    created_at TEXT,
    incoming_money NUMERIC,
    selection_total NUMERIC,
    is_huge BOOLEAN DEFAULT FALSE,
    huge_total NUMERIC,
    alarm_type TEXT,
    big_money_limit NUMERIC,
    snapshot_count INTEGER,
    UNIQUE(home, away, market, selection, event_time)
);

-- 4. VOLUMESHOCK ALARMS
CREATE TABLE volumeshock_alarms (
    id SERIAL PRIMARY KEY,
    match_id TEXT,
    type TEXT DEFAULT 'volume_shock',
    home TEXT NOT NULL,
    away TEXT NOT NULL,
    market TEXT NOT NULL,
    selection TEXT NOT NULL,
    match_date TEXT,
    event_time TEXT,
    trigger_at TEXT,
    created_at TEXT,
    volume_shock_value NUMERIC,
    hours_to_kickoff NUMERIC,
    incoming_money NUMERIC,
    avg_previous NUMERIC,
    hacim_soku_min_saat NUMERIC,
    hacim_soku_min_esik NUMERIC,
    UNIQUE(home, away, market, selection)
);

-- 5. DROPPING ALARMS
CREATE TABLE dropping_alarms (
    id SERIAL PRIMARY KEY,
    match_id TEXT,
    home TEXT NOT NULL,
    away TEXT NOT NULL,
    home_team TEXT,
    away_team TEXT,
    league TEXT,
    market TEXT NOT NULL,
    selection TEXT NOT NULL,
    match_date TEXT,
    fixture_date TEXT,
    event_time TEXT,
    trigger_at TEXT,
    created_at TEXT,
    level TEXT,
    opening_odds NUMERIC,
    current_odds NUMERIC,
    drop_pct NUMERIC,
    volume NUMERIC,
    UNIQUE(home, away, market, selection)
);

-- 6. PUBLICMOVE ALARMS
CREATE TABLE publicmove_alarms (
    id SERIAL PRIMARY KEY,
    match_id TEXT,
    home TEXT NOT NULL,
    away TEXT NOT NULL,
    market TEXT NOT NULL,
    selection TEXT NOT NULL,
    match_date TEXT,
    event_time TEXT,
    trigger_at TEXT,
    created_at TEXT,
    trap_score NUMERIC,
    incoming_money NUMERIC,
    odds_drop_pct NUMERIC,
    previous_share NUMERIC,
    current_share NUMERIC,
    share_change NUMERIC,
    UNIQUE(home, away, market, selection)
);

-- 7. VOLUME LEADER ALARMS
CREATE TABLE volume_leader_alarms (
    id SERIAL PRIMARY KEY,
    match_id TEXT,
    home TEXT NOT NULL,
    away TEXT NOT NULL,
    market TEXT NOT NULL,
    selection TEXT,
    match_date TEXT,
    event_time TEXT,
    trigger_at TEXT,
    created_at TEXT,
    old_leader TEXT,
    old_leader_share NUMERIC,
    new_leader TEXT,
    new_leader_share NUMERIC,
    total_volume NUMERIC,
    UNIQUE(home, away, market, old_leader, new_leader)
);

-- =====================================================
-- ADIM 3: ROW LEVEL SECURITY (RLS)
-- =====================================================
ALTER TABLE sharp_alarms ENABLE ROW LEVEL SECURITY;
ALTER TABLE insider_alarms ENABLE ROW LEVEL SECURITY;
ALTER TABLE bigmoney_alarms ENABLE ROW LEVEL SECURITY;
ALTER TABLE volumeshock_alarms ENABLE ROW LEVEL SECURITY;
ALTER TABLE dropping_alarms ENABLE ROW LEVEL SECURITY;
ALTER TABLE publicmove_alarms ENABLE ROW LEVEL SECURITY;
ALTER TABLE volume_leader_alarms ENABLE ROW LEVEL SECURITY;

-- =====================================================
-- ADIM 4: POLICY'LER (OKUMA/YAZMA İZNİ)
-- =====================================================
CREATE POLICY "Allow all for sharp_alarms" ON sharp_alarms FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for insider_alarms" ON insider_alarms FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for bigmoney_alarms" ON bigmoney_alarms FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for volumeshock_alarms" ON volumeshock_alarms FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for dropping_alarms" ON dropping_alarms FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for publicmove_alarms" ON publicmove_alarms FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for volume_leader_alarms" ON volume_leader_alarms FOR ALL USING (true) WITH CHECK (true);

-- =====================================================
-- ADIM 5: İNDEKSLER (PERFORMANS)
-- =====================================================
CREATE INDEX idx_sharp_match ON sharp_alarms(home, away);
CREATE INDEX idx_sharp_created ON sharp_alarms(created_at);

CREATE INDEX idx_insider_match ON insider_alarms(home, away);
CREATE INDEX idx_insider_created ON insider_alarms(created_at);

CREATE INDEX idx_bigmoney_match ON bigmoney_alarms(home, away);
CREATE INDEX idx_bigmoney_created ON bigmoney_alarms(created_at);

CREATE INDEX idx_volumeshock_match ON volumeshock_alarms(home, away);
CREATE INDEX idx_volumeshock_created ON volumeshock_alarms(created_at);

CREATE INDEX idx_dropping_match ON dropping_alarms(home, away);
CREATE INDEX idx_dropping_created ON dropping_alarms(created_at);

CREATE INDEX idx_publicmove_match ON publicmove_alarms(home, away);
CREATE INDEX idx_publicmove_created ON publicmove_alarms(created_at);

CREATE INDEX idx_volumeleader_match ON volume_leader_alarms(home, away);
CREATE INDEX idx_volumeleader_created ON volume_leader_alarms(created_at);

-- =====================================================
-- TAMAMLANDI
-- =====================================================
SELECT 'Tüm alarm tabloları başarıyla oluşturuldu! (V5.0 - UI Alan Adlarıyla Uyumlu)' as result;
