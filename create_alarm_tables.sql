-- SmartXFlow Alarm Tabloları V3.0 - TEMİZ BAŞLANGIÇ
-- Supabase Dashboard > SQL Editor'da çalıştırın
-- TÜM ALAN ADLARI FIELD_NAMING_STANDARD.md'YE GÖRE

-- =====================================================
-- ADIM 1: ESKİ TABLOLARI SİL (TEMİZ BAŞLANGIÇ)
-- =====================================================
DROP TABLE IF EXISTS sharp_alarms CASCADE;
DROP TABLE IF EXISTS insider_alarms CASCADE;
DROP TABLE IF EXISTS bigmoney_alarms CASCADE;
DROP TABLE IF EXISTS volumeshock_alarms CASCADE;
DROP TABLE IF EXISTS dropping_alarms CASCADE;
DROP TABLE IF EXISTS publicmove_alarms CASCADE;
DROP TABLE IF EXISTS volume_leader_alarms CASCADE;

-- =====================================================
-- ADIM 2: YENİ TABLOLAR (CANONICAL İSİMLER)
-- =====================================================

-- 1. SHARP ALARMS
CREATE TABLE sharp_alarms (
    id SERIAL PRIMARY KEY,
    match_id TEXT,
    home TEXT NOT NULL,
    away TEXT NOT NULL,
    market TEXT NOT NULL,
    selection TEXT NOT NULL,
    sharp_score NUMERIC,
    volume_contrib NUMERIC,
    odds_contrib NUMERIC,
    share_contrib NUMERIC,
    incoming_money NUMERIC,
    previous_amount NUMERIC,
    current_amount NUMERIC,
    opening_odds NUMERIC,
    previous_odds NUMERIC,
    current_odds NUMERIC,
    odds_drop_pct NUMERIC,
    previous_share NUMERIC,
    current_share NUMERIC,
    share_change NUMERIC,
    volume_shock NUMERIC,
    volume_shock_multiplier NUMERIC,
    avg_previous NUMERIC,
    match_date TEXT,
    trigger_at TEXT,
    created_at TEXT DEFAULT NOW()::TEXT,
    alarm_type TEXT DEFAULT 'sharp',
    UNIQUE(home, away, market, selection, trigger_at)
);

-- 2. INSIDER ALARMS
CREATE TABLE insider_alarms (
    id SERIAL PRIMARY KEY,
    match_id TEXT,
    home TEXT NOT NULL,
    away TEXT NOT NULL,
    market TEXT NOT NULL,
    selection TEXT NOT NULL,
    odds_drop_pct NUMERIC,
    incoming_money NUMERIC,
    volume_shock NUMERIC,
    avg_volume_shock NUMERIC,
    opening_odds NUMERIC,
    current_odds NUMERIC,
    surrounding_snapshots JSONB,
    snapshot_count INTEGER,
    drop_moment TEXT,
    match_date TEXT,
    trigger_at TEXT,
    created_at TEXT DEFAULT NOW()::TEXT,
    alarm_type TEXT DEFAULT 'insider',
    UNIQUE(home, away, market, selection, trigger_at)
);

-- 3. BIGMONEY ALARMS
CREATE TABLE bigmoney_alarms (
    id SERIAL PRIMARY KEY,
    match_id TEXT,
    home TEXT NOT NULL,
    away TEXT NOT NULL,
    market TEXT NOT NULL,
    selection TEXT NOT NULL,
    incoming_money NUMERIC,
    selection_total NUMERIC,
    is_huge BOOLEAN DEFAULT FALSE,
    huge_total NUMERIC,
    match_date TEXT,
    trigger_at TEXT,
    created_at TEXT DEFAULT NOW()::TEXT,
    alarm_type TEXT DEFAULT 'bigmoney',
    UNIQUE(home, away, market, selection, trigger_at)
);

-- 4. VOLUMESHOCK ALARMS
CREATE TABLE volumeshock_alarms (
    id SERIAL PRIMARY KEY,
    match_id TEXT,
    home TEXT NOT NULL,
    away TEXT NOT NULL,
    market TEXT NOT NULL,
    selection TEXT NOT NULL,
    volume_shock NUMERIC,
    volume_shock_multiplier NUMERIC,
    incoming_money NUMERIC,
    avg_previous NUMERIC,
    hours_to_kickoff NUMERIC,
    match_date TEXT,
    trigger_at TEXT,
    created_at TEXT DEFAULT NOW()::TEXT,
    alarm_type TEXT DEFAULT 'volumeshock',
    UNIQUE(home, away, market, selection, trigger_at)
);

-- 5. DROPPING ALARMS
CREATE TABLE dropping_alarms (
    id SERIAL PRIMARY KEY,
    match_id TEXT,
    home TEXT NOT NULL,
    away TEXT NOT NULL,
    market TEXT NOT NULL,
    selection TEXT NOT NULL,
    opening_odds NUMERIC,
    current_odds NUMERIC,
    odds_drop_pct NUMERIC,
    level TEXT,
    match_date TEXT,
    trigger_at TEXT,
    created_at TEXT DEFAULT NOW()::TEXT,
    alarm_type TEXT DEFAULT 'dropping',
    UNIQUE(home, away, market, selection, trigger_at)
);

-- 6. PUBLICMOVE ALARMS
CREATE TABLE publicmove_alarms (
    id SERIAL PRIMARY KEY,
    match_id TEXT,
    home TEXT NOT NULL,
    away TEXT NOT NULL,
    market TEXT NOT NULL,
    selection TEXT NOT NULL,
    trap_score NUMERIC,
    incoming_money NUMERIC,
    odds_drop_pct NUMERIC,
    previous_share NUMERIC,
    current_share NUMERIC,
    share_change NUMERIC,
    match_date TEXT,
    trigger_at TEXT,
    created_at TEXT DEFAULT NOW()::TEXT,
    alarm_type TEXT DEFAULT 'publicmove',
    UNIQUE(home, away, market, selection, trigger_at)
);

-- 7. VOLUME LEADER ALARMS
CREATE TABLE volume_leader_alarms (
    id SERIAL PRIMARY KEY,
    match_id TEXT,
    home TEXT NOT NULL,
    away TEXT NOT NULL,
    market TEXT NOT NULL,
    old_leader TEXT,
    old_leader_share NUMERIC,
    new_leader TEXT,
    new_leader_share NUMERIC,
    total_volume NUMERIC,
    match_date TEXT,
    trigger_at TEXT,
    created_at TEXT DEFAULT NOW()::TEXT,
    alarm_type TEXT DEFAULT 'volumeleader',
    UNIQUE(home, away, market, old_leader, new_leader, trigger_at)
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
CREATE INDEX idx_sharp_trigger ON sharp_alarms(trigger_at);

CREATE INDEX idx_insider_match ON insider_alarms(home, away);
CREATE INDEX idx_insider_created ON insider_alarms(created_at);
CREATE INDEX idx_insider_trigger ON insider_alarms(trigger_at);

CREATE INDEX idx_bigmoney_match ON bigmoney_alarms(home, away);
CREATE INDEX idx_bigmoney_created ON bigmoney_alarms(created_at);
CREATE INDEX idx_bigmoney_trigger ON bigmoney_alarms(trigger_at);

CREATE INDEX idx_volumeshock_match ON volumeshock_alarms(home, away);
CREATE INDEX idx_volumeshock_created ON volumeshock_alarms(created_at);
CREATE INDEX idx_volumeshock_trigger ON volumeshock_alarms(trigger_at);

CREATE INDEX idx_dropping_match ON dropping_alarms(home, away);
CREATE INDEX idx_dropping_created ON dropping_alarms(created_at);
CREATE INDEX idx_dropping_trigger ON dropping_alarms(trigger_at);

CREATE INDEX idx_publicmove_match ON publicmove_alarms(home, away);
CREATE INDEX idx_publicmove_created ON publicmove_alarms(created_at);
CREATE INDEX idx_publicmove_trigger ON publicmove_alarms(trigger_at);

CREATE INDEX idx_volumeleader_match ON volume_leader_alarms(home, away);
CREATE INDEX idx_volumeleader_created ON volume_leader_alarms(created_at);
CREATE INDEX idx_volumeleader_trigger ON volume_leader_alarms(trigger_at);

-- =====================================================
-- TAMAMLANDI
-- =====================================================
SELECT 'Tüm alarm tabloları başarıyla oluşturuldu! (V3.0 - Canonical İsimler)' as result;
