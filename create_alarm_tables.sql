-- SmartXFlow Alarm Tabloları - Supabase Dashboard > SQL Editor'da çalıştırın
-- V2.1 - Non-destructive migration (IF NOT EXISTS kullanılıyor)

-- 1. Sharp Alarms - TÜM FIELD'LAR
CREATE TABLE IF NOT EXISTS sharp_alarms (
    id SERIAL PRIMARY KEY,
    home TEXT NOT NULL,
    away TEXT NOT NULL,
    market TEXT NOT NULL,
    selection TEXT NOT NULL,
    sharp_score NUMERIC,
    smart_score NUMERIC,
    volume_contrib NUMERIC,
    odds_contrib NUMERIC,
    share_contrib NUMERIC,
    volume NUMERIC,
    volume_shock_multiplier NUMERIC,
    opening_odds NUMERIC,
    previous_odds NUMERIC,
    current_odds NUMERIC,
    drop_percentage NUMERIC,
    previous_share NUMERIC,
    current_share NUMERIC,
    share_change_percent NUMERIC,
    weights JSONB,
    match_date TEXT,
    event_time TEXT,
    trigger_at TEXT,
    created_at TEXT,
    alarm_type TEXT DEFAULT 'sharp',
    UNIQUE(home, away, market, selection)
);

-- Eksik kolonları ekle (mevcut tabloya)
ALTER TABLE sharp_alarms ADD COLUMN IF NOT EXISTS smart_score NUMERIC;
ALTER TABLE sharp_alarms ADD COLUMN IF NOT EXISTS volume_shock_multiplier NUMERIC;
ALTER TABLE sharp_alarms ADD COLUMN IF NOT EXISTS opening_odds NUMERIC;
ALTER TABLE sharp_alarms ADD COLUMN IF NOT EXISTS drop_percentage NUMERIC;
ALTER TABLE sharp_alarms ADD COLUMN IF NOT EXISTS share_change_percent NUMERIC;
ALTER TABLE sharp_alarms ADD COLUMN IF NOT EXISTS weights JSONB;

-- TEXT kolonları JSONB'ye dönüştür (mevcut tablolar için)
DO $$ 
BEGIN
    -- weights TEXT ise JSONB'ye dönüştür
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'sharp_alarms' AND column_name = 'weights' AND data_type = 'text') THEN
        ALTER TABLE sharp_alarms ALTER COLUMN weights TYPE JSONB USING weights::jsonb;
    END IF;
END $$;

-- 2. Insider Alarms - TÜM FIELD'LAR
CREATE TABLE IF NOT EXISTS insider_alarms (
    id SERIAL PRIMARY KEY,
    home TEXT NOT NULL,
    away TEXT NOT NULL,
    market TEXT NOT NULL,
    selection TEXT NOT NULL,
    oran_dusus_pct NUMERIC,
    odds_change_percent NUMERIC,
    gelen_para NUMERIC,
    hacim_sok NUMERIC,
    avg_volume_shock NUMERIC,
    max_surrounding_hacim_sok NUMERIC,
    max_surrounding_incoming NUMERIC,
    opening_odds NUMERIC,
    open_odds NUMERIC,
    current_odds NUMERIC,
    surrounding_snapshots JSONB,
    surrounding_count INTEGER,
    snapshot_count INTEGER,
    drop_moment_index INTEGER,
    drop_moment TEXT,
    match_date TEXT,
    event_time TEXT,
    trigger_at TEXT,
    created_at TEXT,
    alarm_type TEXT DEFAULT 'insider',
    UNIQUE(home, away, market, selection)
);

-- Eksik kolonları ekle
ALTER TABLE insider_alarms ADD COLUMN IF NOT EXISTS odds_change_percent NUMERIC;
ALTER TABLE insider_alarms ADD COLUMN IF NOT EXISTS avg_volume_shock NUMERIC;
ALTER TABLE insider_alarms ADD COLUMN IF NOT EXISTS max_surrounding_hacim_sok NUMERIC;
ALTER TABLE insider_alarms ADD COLUMN IF NOT EXISTS max_surrounding_incoming NUMERIC;
ALTER TABLE insider_alarms ADD COLUMN IF NOT EXISTS open_odds NUMERIC;
ALTER TABLE insider_alarms ADD COLUMN IF NOT EXISTS surrounding_snapshots JSONB;
ALTER TABLE insider_alarms ADD COLUMN IF NOT EXISTS surrounding_count INTEGER;
ALTER TABLE insider_alarms ADD COLUMN IF NOT EXISTS snapshot_count INTEGER;
ALTER TABLE insider_alarms ADD COLUMN IF NOT EXISTS drop_moment_index INTEGER;
ALTER TABLE insider_alarms ADD COLUMN IF NOT EXISTS drop_moment TEXT;

-- TEXT kolonları JSONB'ye dönüştür (insider_alarms için)
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'insider_alarms' AND column_name = 'surrounding_snapshots' AND data_type = 'text') THEN
        ALTER TABLE insider_alarms ALTER COLUMN surrounding_snapshots TYPE JSONB USING COALESCE(surrounding_snapshots::jsonb, '[]'::jsonb);
    END IF;
END $$;

-- 3. BigMoney Alarms
CREATE TABLE IF NOT EXISTS bigmoney_alarms (
    id SERIAL PRIMARY KEY,
    home TEXT NOT NULL,
    away TEXT NOT NULL,
    market TEXT NOT NULL,
    selection TEXT NOT NULL,
    incoming_money NUMERIC,
    selection_total NUMERIC,
    is_huge BOOLEAN DEFAULT FALSE,
    huge_total NUMERIC,
    match_date TEXT,
    event_time TEXT,
    trigger_at TEXT,
    created_at TEXT,
    alarm_type TEXT DEFAULT 'bigmoney',
    UNIQUE(home, away, market, selection)
);

-- 4. VolumeShock Alarms - TÜM FIELD'LAR
CREATE TABLE IF NOT EXISTS volumeshock_alarms (
    id SERIAL PRIMARY KEY,
    home TEXT NOT NULL,
    away TEXT NOT NULL,
    market TEXT NOT NULL,
    selection TEXT NOT NULL,
    volume_shock_value NUMERIC,
    multiplier NUMERIC,
    incoming_money NUMERIC,
    new_money NUMERIC,
    avg_previous NUMERIC,
    avg_last_10 NUMERIC,
    hours_to_kickoff NUMERIC,
    match_date TEXT,
    event_time TEXT,
    trigger_at TEXT,
    created_at TEXT,
    alarm_type TEXT DEFAULT 'volumeshock',
    UNIQUE(home, away, market, selection)
);

-- Eksik kolonları ekle
ALTER TABLE volumeshock_alarms ADD COLUMN IF NOT EXISTS multiplier NUMERIC;
ALTER TABLE volumeshock_alarms ADD COLUMN IF NOT EXISTS new_money NUMERIC;
ALTER TABLE volumeshock_alarms ADD COLUMN IF NOT EXISTS avg_last_10 NUMERIC;
ALTER TABLE volumeshock_alarms ADD COLUMN IF NOT EXISTS hours_to_kickoff NUMERIC;

-- 5. Dropping Alarms - TÜM FIELD'LAR
CREATE TABLE IF NOT EXISTS dropping_alarms (
    id SERIAL PRIMARY KEY,
    home TEXT NOT NULL,
    away TEXT NOT NULL,
    market TEXT NOT NULL,
    selection TEXT NOT NULL,
    opening_odds NUMERIC,
    open_odds NUMERIC,
    current_odds NUMERIC,
    drop_pct NUMERIC,
    drop_percentage NUMERIC,
    level TEXT,
    match_date TEXT,
    event_time TEXT,
    trigger_at TEXT,
    created_at TEXT,
    alarm_type TEXT DEFAULT 'dropping',
    UNIQUE(home, away, market, selection)
);

-- Eksik kolonları ekle
ALTER TABLE dropping_alarms ADD COLUMN IF NOT EXISTS open_odds NUMERIC;
ALTER TABLE dropping_alarms ADD COLUMN IF NOT EXISTS drop_percentage NUMERIC;
ALTER TABLE dropping_alarms ADD COLUMN IF NOT EXISTS level TEXT;

-- 6. PublicMove Alarms - TÜM FIELD'LAR
CREATE TABLE IF NOT EXISTS publicmove_alarms (
    id SERIAL PRIMARY KEY,
    home TEXT NOT NULL,
    away TEXT NOT NULL,
    market TEXT NOT NULL,
    selection TEXT NOT NULL,
    trap_score NUMERIC,
    volume NUMERIC,
    odds_drop NUMERIC,
    share_before NUMERIC,
    share_after NUMERIC,
    share_change NUMERIC,
    delta NUMERIC,
    match_date TEXT,
    event_time TEXT,
    trigger_at TEXT,
    created_at TEXT,
    alarm_type TEXT DEFAULT 'publicmove',
    UNIQUE(home, away, market, selection)
);

-- Eksik kolonları ekle
ALTER TABLE publicmove_alarms ADD COLUMN IF NOT EXISTS share_before NUMERIC;
ALTER TABLE publicmove_alarms ADD COLUMN IF NOT EXISTS share_after NUMERIC;
ALTER TABLE publicmove_alarms ADD COLUMN IF NOT EXISTS delta NUMERIC;

-- 7. Volume Leader Alarms
CREATE TABLE IF NOT EXISTS volume_leader_alarms (
    id SERIAL PRIMARY KEY,
    home TEXT NOT NULL,
    away TEXT NOT NULL,
    market TEXT NOT NULL,
    old_leader TEXT,
    old_leader_share NUMERIC,
    new_leader TEXT,
    new_leader_share NUMERIC,
    total_volume NUMERIC,
    match_date TEXT,
    event_time TEXT,
    trigger_at TEXT,
    created_at TEXT,
    alarm_type TEXT DEFAULT 'volumeleader',
    UNIQUE(home, away, market, old_leader, new_leader)
);

-- Row Level Security (RLS) - Herkese okuma/yazma izni
ALTER TABLE sharp_alarms ENABLE ROW LEVEL SECURITY;
ALTER TABLE insider_alarms ENABLE ROW LEVEL SECURITY;
ALTER TABLE bigmoney_alarms ENABLE ROW LEVEL SECURITY;
ALTER TABLE volumeshock_alarms ENABLE ROW LEVEL SECURITY;
ALTER TABLE dropping_alarms ENABLE ROW LEVEL SECURITY;
ALTER TABLE publicmove_alarms ENABLE ROW LEVEL SECURITY;
ALTER TABLE volume_leader_alarms ENABLE ROW LEVEL SECURITY;

-- Policy'ler (DROP IF EXISTS ile güvenli)
DROP POLICY IF EXISTS "Allow all for sharp_alarms" ON sharp_alarms;
DROP POLICY IF EXISTS "Allow all for insider_alarms" ON insider_alarms;
DROP POLICY IF EXISTS "Allow all for bigmoney_alarms" ON bigmoney_alarms;
DROP POLICY IF EXISTS "Allow all for volumeshock_alarms" ON volumeshock_alarms;
DROP POLICY IF EXISTS "Allow all for dropping_alarms" ON dropping_alarms;
DROP POLICY IF EXISTS "Allow all for publicmove_alarms" ON publicmove_alarms;
DROP POLICY IF EXISTS "Allow all for volume_leader_alarms" ON volume_leader_alarms;

CREATE POLICY "Allow all for sharp_alarms" ON sharp_alarms FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for insider_alarms" ON insider_alarms FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for bigmoney_alarms" ON bigmoney_alarms FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for volumeshock_alarms" ON volumeshock_alarms FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for dropping_alarms" ON dropping_alarms FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for publicmove_alarms" ON publicmove_alarms FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for volume_leader_alarms" ON volume_leader_alarms FOR ALL USING (true) WITH CHECK (true);

-- İndeksler
CREATE INDEX IF NOT EXISTS idx_sharp_home ON sharp_alarms(home);
CREATE INDEX IF NOT EXISTS idx_sharp_created ON sharp_alarms(created_at);
CREATE INDEX IF NOT EXISTS idx_insider_home ON insider_alarms(home);
CREATE INDEX IF NOT EXISTS idx_insider_created ON insider_alarms(created_at);
CREATE INDEX IF NOT EXISTS idx_bigmoney_home ON bigmoney_alarms(home);
CREATE INDEX IF NOT EXISTS idx_bigmoney_created ON bigmoney_alarms(created_at);
CREATE INDEX IF NOT EXISTS idx_volumeshock_home ON volumeshock_alarms(home);
CREATE INDEX IF NOT EXISTS idx_volumeshock_created ON volumeshock_alarms(created_at);
CREATE INDEX IF NOT EXISTS idx_dropping_home ON dropping_alarms(home);
CREATE INDEX IF NOT EXISTS idx_dropping_created ON dropping_alarms(created_at);
CREATE INDEX IF NOT EXISTS idx_publicmove_home ON publicmove_alarms(home);
CREATE INDEX IF NOT EXISTS idx_publicmove_created ON publicmove_alarms(created_at);
CREATE INDEX IF NOT EXISTS idx_volumeleader_home ON volume_leader_alarms(home);
CREATE INDEX IF NOT EXISTS idx_volumeleader_created ON volume_leader_alarms(created_at);

SELECT 'Tüm alarm tabloları başarıyla güncellendi! (V2.1 - Non-destructive)' as result;
