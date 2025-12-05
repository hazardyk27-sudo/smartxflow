-- SmartXFlow Alarm Tabloları - Supabase Dashboard > SQL Editor'da çalıştırın

-- 1. Sharp Alarms
CREATE TABLE IF NOT EXISTS sharp_alarms (
    id SERIAL PRIMARY KEY,
    home TEXT NOT NULL,
    away TEXT NOT NULL,
    market TEXT NOT NULL,
    selection TEXT NOT NULL,
    sharp_score NUMERIC,
    volume_contrib NUMERIC,
    odds_contrib NUMERIC,
    share_contrib NUMERIC,
    volume NUMERIC,
    previous_odds NUMERIC,
    current_odds NUMERIC,
    previous_share NUMERIC,
    current_share NUMERIC,
    match_date TEXT,
    event_time TEXT,
    trigger_at TEXT,
    created_at TEXT,
    alarm_type TEXT DEFAULT 'sharp',
    UNIQUE(home, away, market, selection)
);

-- 2. Insider Alarms
CREATE TABLE IF NOT EXISTS insider_alarms (
    id SERIAL PRIMARY KEY,
    home TEXT NOT NULL,
    away TEXT NOT NULL,
    market TEXT NOT NULL,
    selection TEXT NOT NULL,
    oran_dusus_pct NUMERIC,
    gelen_para NUMERIC,
    hacim_sok NUMERIC,
    opening_odds NUMERIC,
    current_odds NUMERIC,
    match_date TEXT,
    event_time TEXT,
    trigger_at TEXT,
    created_at TEXT,
    alarm_type TEXT DEFAULT 'insider',
    UNIQUE(home, away, market, selection)
);

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
    alarm_type TEXT DEFAULT 'bigmoney',
    match_date TEXT,
    event_time TEXT,
    trigger_at TEXT,
    created_at TEXT,
    UNIQUE(home, away, market, selection)
);

-- 4. VolumeShock Alarms
CREATE TABLE IF NOT EXISTS volumeshock_alarms (
    id SERIAL PRIMARY KEY,
    home TEXT NOT NULL,
    away TEXT NOT NULL,
    market TEXT NOT NULL,
    selection TEXT NOT NULL,
    volume_shock_value NUMERIC,
    incoming_money NUMERIC,
    avg_previous NUMERIC,
    match_date TEXT,
    event_time TEXT,
    trigger_at TEXT,
    created_at TEXT,
    alarm_type TEXT DEFAULT 'volumeshock',
    UNIQUE(home, away, market, selection)
);

-- 5. Dropping Alarms
CREATE TABLE IF NOT EXISTS dropping_alarms (
    id SERIAL PRIMARY KEY,
    home TEXT NOT NULL,
    away TEXT NOT NULL,
    market TEXT NOT NULL,
    selection TEXT NOT NULL,
    opening_odds NUMERIC,
    current_odds NUMERIC,
    drop_pct NUMERIC,
    level TEXT,
    match_date TEXT,
    event_time TEXT,
    trigger_at TEXT,
    created_at TEXT,
    alarm_type TEXT DEFAULT 'dropping',
    UNIQUE(home, away, market, selection)
);

-- 6. PublicMove Alarms
CREATE TABLE IF NOT EXISTS publicmove_alarms (
    id SERIAL PRIMARY KEY,
    home TEXT NOT NULL,
    away TEXT NOT NULL,
    market TEXT NOT NULL,
    selection TEXT NOT NULL,
    trap_score NUMERIC,
    volume NUMERIC,
    odds_drop NUMERIC,
    share_change NUMERIC,
    match_date TEXT,
    event_time TEXT,
    trigger_at TEXT,
    created_at TEXT,
    alarm_type TEXT DEFAULT 'publicmove',
    UNIQUE(home, away, market, selection)
);

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

-- Anon key ile erişim için policy'ler
CREATE POLICY "Allow all for sharp_alarms" ON sharp_alarms FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for insider_alarms" ON insider_alarms FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for bigmoney_alarms" ON bigmoney_alarms FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for volumeshock_alarms" ON volumeshock_alarms FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for dropping_alarms" ON dropping_alarms FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for publicmove_alarms" ON publicmove_alarms FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for volume_leader_alarms" ON volume_leader_alarms FOR ALL USING (true) WITH CHECK (true);

-- İndeksler (performans için)
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
