-- ==============================================================================
-- SmartXFlow Supabase Schema V3.0 - MİNİMAL VE TEMİZ
-- ==============================================================================
-- Bu dosya sadece aktif kullanılan tabloları ve kolonları içerir
-- Supabase Dashboard > SQL Editor'da çalıştırın
-- Tarih: Aralık 2025

-- ==============================================================================
-- BÖLÜM 1: ALARM TABLOLARI (7 tablo)
-- ==============================================================================

-- 1.1 Sharp Alarms
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
    amount_change NUMERIC,
    weights JSONB,
    match_date TEXT,
    event_time TEXT,
    trigger_at TEXT,
    created_at TEXT,
    alarm_type TEXT DEFAULT 'sharp',
    UNIQUE(home, away, market, selection)
);

-- 1.2 Insider Alarms
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

-- 1.3 BigMoney Alarms
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

-- 1.4 VolumeShock Alarms
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

-- 1.5 Dropping Alarms
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

-- 1.6 PublicMove Alarms
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

-- 1.7 Volume Leader Alarms
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

-- ==============================================================================
-- BÖLÜM 2: AYAR TABLOSU
-- ==============================================================================

CREATE TABLE IF NOT EXISTS alarm_settings (
    id SERIAL PRIMARY KEY,
    alarm_type TEXT UNIQUE NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    config JSONB,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ==============================================================================
-- BÖLÜM 3: MAÇ VERİLERİ TABLOLARI
-- ==============================================================================

-- 3.1 Matches tablosu
CREATE TABLE IF NOT EXISTS matches (
    id SERIAL PRIMARY KEY,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    league TEXT,
    match_date TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(home_team, away_team, match_date)
);

-- 3.2 Odds Snapshots tablosu
CREATE TABLE IF NOT EXISTS odds_snapshots (
    id SERIAL PRIMARY KEY,
    match_id INTEGER REFERENCES matches(id),
    market TEXT NOT NULL,
    volume TEXT,
    odds_1 NUMERIC,
    odds_x NUMERIC,
    odds_2 NUMERIC,
    pct_1 TEXT,
    pct_x TEXT,
    pct_2 TEXT,
    amt_1 TEXT,
    amt_x TEXT,
    amt_2 TEXT,
    trend_1 TEXT,
    trend_x TEXT,
    trend_2 TEXT,
    over_odds NUMERIC,
    under_odds NUMERIC,
    line TEXT,
    pct_over TEXT,
    pct_under TEXT,
    amt_over TEXT,
    amt_under TEXT,
    trend_over TEXT,
    trend_under TEXT,
    yes_odds NUMERIC,
    no_odds NUMERIC,
    pct_yes TEXT,
    pct_no TEXT,
    amt_yes TEXT,
    amt_no TEXT,
    trend_yes TEXT,
    trend_no TEXT,
    scraped_at TIMESTAMPTZ DEFAULT NOW()
);

-- ==============================================================================
-- BÖLÜM 4: HISTORY TABLOLARI (6 tablo)
-- ==============================================================================

-- 4.1 Moneyway 1X2 History
CREATE TABLE IF NOT EXISTS moneyway_1x2_history (
    id SERIAL PRIMARY KEY,
    home TEXT NOT NULL,
    away TEXT NOT NULL,
    league TEXT,
    date TEXT,
    volume TEXT,
    odds1 NUMERIC,
    oddsx NUMERIC,
    odds2 NUMERIC,
    pct1 TEXT,
    pctx TEXT,
    pct2 TEXT,
    amt1 TEXT,
    amtx TEXT,
    amt2 TEXT,
    trend1 TEXT,
    trendx TEXT,
    trend2 TEXT,
    odds1_prev NUMERIC,
    oddsx_prev NUMERIC,
    odds2_prev NUMERIC,
    scraped_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4.2 Moneyway O/U 2.5 History
CREATE TABLE IF NOT EXISTS moneyway_ou25_history (
    id SERIAL PRIMARY KEY,
    home TEXT NOT NULL,
    away TEXT NOT NULL,
    league TEXT,
    date TEXT,
    volume TEXT,
    line TEXT DEFAULT '2.5',
    over NUMERIC,
    under NUMERIC,
    pctover TEXT,
    pctunder TEXT,
    amtover TEXT,
    amtunder TEXT,
    trendover TEXT,
    trendunder TEXT,
    over_prev NUMERIC,
    under_prev NUMERIC,
    scraped_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4.3 Moneyway BTTS History
CREATE TABLE IF NOT EXISTS moneyway_btts_history (
    id SERIAL PRIMARY KEY,
    home TEXT NOT NULL,
    away TEXT NOT NULL,
    league TEXT,
    date TEXT,
    volume TEXT,
    oddsyes NUMERIC,
    oddsno NUMERIC,
    pctyes TEXT,
    pctno TEXT,
    amtyes TEXT,
    amtno TEXT,
    trendyes TEXT,
    trendno TEXT,
    oddsyes_prev NUMERIC,
    oddsno_prev NUMERIC,
    scraped_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4.4 Dropping 1X2 History
CREATE TABLE IF NOT EXISTS dropping_1x2_history (
    id SERIAL PRIMARY KEY,
    home TEXT NOT NULL,
    away TEXT NOT NULL,
    league TEXT,
    date TEXT,
    odds1 NUMERIC,
    oddsx NUMERIC,
    odds2 NUMERIC,
    opening1 NUMERIC,
    openingx NUMERIC,
    opening2 NUMERIC,
    drop1 NUMERIC,
    dropx NUMERIC,
    drop2 NUMERIC,
    scraped_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4.5 Dropping O/U 2.5 History
CREATE TABLE IF NOT EXISTS dropping_ou25_history (
    id SERIAL PRIMARY KEY,
    home TEXT NOT NULL,
    away TEXT NOT NULL,
    league TEXT,
    date TEXT,
    line TEXT DEFAULT '2.5',
    over NUMERIC,
    under NUMERIC,
    opening_over NUMERIC,
    opening_under NUMERIC,
    drop_over NUMERIC,
    drop_under NUMERIC,
    scraped_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4.6 Dropping BTTS History
CREATE TABLE IF NOT EXISTS dropping_btts_history (
    id SERIAL PRIMARY KEY,
    home TEXT NOT NULL,
    away TEXT NOT NULL,
    league TEXT,
    date TEXT,
    oddsyes NUMERIC,
    oddsno NUMERIC,
    opening_yes NUMERIC,
    opening_no NUMERIC,
    drop_yes NUMERIC,
    drop_no NUMERIC,
    scraped_at TIMESTAMPTZ DEFAULT NOW()
);

-- ==============================================================================
-- BÖLÜM 5: ROW LEVEL SECURITY (RLS)
-- ==============================================================================

ALTER TABLE sharp_alarms ENABLE ROW LEVEL SECURITY;
ALTER TABLE insider_alarms ENABLE ROW LEVEL SECURITY;
ALTER TABLE bigmoney_alarms ENABLE ROW LEVEL SECURITY;
ALTER TABLE volumeshock_alarms ENABLE ROW LEVEL SECURITY;
ALTER TABLE dropping_alarms ENABLE ROW LEVEL SECURITY;
ALTER TABLE publicmove_alarms ENABLE ROW LEVEL SECURITY;
ALTER TABLE volume_leader_alarms ENABLE ROW LEVEL SECURITY;
ALTER TABLE alarm_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE matches ENABLE ROW LEVEL SECURITY;
ALTER TABLE odds_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE moneyway_1x2_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE moneyway_ou25_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE moneyway_btts_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE dropping_1x2_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE dropping_ou25_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE dropping_btts_history ENABLE ROW LEVEL SECURITY;

-- ==============================================================================
-- BÖLÜM 6: POLICY'LER (Herkese okuma/yazma izni)
-- ==============================================================================

DROP POLICY IF EXISTS "Allow all for sharp_alarms" ON sharp_alarms;
DROP POLICY IF EXISTS "Allow all for insider_alarms" ON insider_alarms;
DROP POLICY IF EXISTS "Allow all for bigmoney_alarms" ON bigmoney_alarms;
DROP POLICY IF EXISTS "Allow all for volumeshock_alarms" ON volumeshock_alarms;
DROP POLICY IF EXISTS "Allow all for dropping_alarms" ON dropping_alarms;
DROP POLICY IF EXISTS "Allow all for publicmove_alarms" ON publicmove_alarms;
DROP POLICY IF EXISTS "Allow all for volume_leader_alarms" ON volume_leader_alarms;
DROP POLICY IF EXISTS "Allow all for alarm_settings" ON alarm_settings;
DROP POLICY IF EXISTS "Allow all for matches" ON matches;
DROP POLICY IF EXISTS "Allow all for odds_snapshots" ON odds_snapshots;
DROP POLICY IF EXISTS "Allow all for moneyway_1x2_history" ON moneyway_1x2_history;
DROP POLICY IF EXISTS "Allow all for moneyway_ou25_history" ON moneyway_ou25_history;
DROP POLICY IF EXISTS "Allow all for moneyway_btts_history" ON moneyway_btts_history;
DROP POLICY IF EXISTS "Allow all for dropping_1x2_history" ON dropping_1x2_history;
DROP POLICY IF EXISTS "Allow all for dropping_ou25_history" ON dropping_ou25_history;
DROP POLICY IF EXISTS "Allow all for dropping_btts_history" ON dropping_btts_history;

CREATE POLICY "Allow all for sharp_alarms" ON sharp_alarms FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for insider_alarms" ON insider_alarms FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for bigmoney_alarms" ON bigmoney_alarms FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for volumeshock_alarms" ON volumeshock_alarms FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for dropping_alarms" ON dropping_alarms FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for publicmove_alarms" ON publicmove_alarms FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for volume_leader_alarms" ON volume_leader_alarms FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for alarm_settings" ON alarm_settings FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for matches" ON matches FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for odds_snapshots" ON odds_snapshots FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for moneyway_1x2_history" ON moneyway_1x2_history FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for moneyway_ou25_history" ON moneyway_ou25_history FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for moneyway_btts_history" ON moneyway_btts_history FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for dropping_1x2_history" ON dropping_1x2_history FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for dropping_ou25_history" ON dropping_ou25_history FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for dropping_btts_history" ON dropping_btts_history FOR ALL USING (true) WITH CHECK (true);

-- ==============================================================================
-- BÖLÜM 7: İNDEKSLER (Performans için)
-- ==============================================================================

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
CREATE INDEX IF NOT EXISTS idx_alarm_settings_type ON alarm_settings(alarm_type);
CREATE INDEX IF NOT EXISTS idx_matches_teams ON matches(home_team, away_team);
CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(match_date);
CREATE INDEX IF NOT EXISTS idx_moneyway_1x2_teams ON moneyway_1x2_history(home, away);
CREATE INDEX IF NOT EXISTS idx_moneyway_ou25_teams ON moneyway_ou25_history(home, away);
CREATE INDEX IF NOT EXISTS idx_moneyway_btts_teams ON moneyway_btts_history(home, away);
CREATE INDEX IF NOT EXISTS idx_dropping_1x2_teams ON dropping_1x2_history(home, away);
CREATE INDEX IF NOT EXISTS idx_dropping_ou25_teams ON dropping_ou25_history(home, away);
CREATE INDEX IF NOT EXISTS idx_dropping_btts_teams ON dropping_btts_history(home, away);

-- ==============================================================================
-- BÖLÜM 8: EKSİK KOLONLARI EKLE (mevcut tablolara)
-- ==============================================================================

ALTER TABLE sharp_alarms ADD COLUMN IF NOT EXISTS amount_change NUMERIC;
ALTER TABLE sharp_alarms ADD COLUMN IF NOT EXISTS smart_score NUMERIC;
ALTER TABLE sharp_alarms ADD COLUMN IF NOT EXISTS volume_shock_multiplier NUMERIC;
ALTER TABLE sharp_alarms ADD COLUMN IF NOT EXISTS opening_odds NUMERIC;
ALTER TABLE sharp_alarms ADD COLUMN IF NOT EXISTS drop_percentage NUMERIC;
ALTER TABLE sharp_alarms ADD COLUMN IF NOT EXISTS share_change_percent NUMERIC;
ALTER TABLE sharp_alarms ADD COLUMN IF NOT EXISTS weights JSONB;

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

ALTER TABLE volumeshock_alarms ADD COLUMN IF NOT EXISTS multiplier NUMERIC;
ALTER TABLE volumeshock_alarms ADD COLUMN IF NOT EXISTS new_money NUMERIC;
ALTER TABLE volumeshock_alarms ADD COLUMN IF NOT EXISTS avg_last_10 NUMERIC;
ALTER TABLE volumeshock_alarms ADD COLUMN IF NOT EXISTS hours_to_kickoff NUMERIC;

ALTER TABLE dropping_alarms ADD COLUMN IF NOT EXISTS open_odds NUMERIC;
ALTER TABLE dropping_alarms ADD COLUMN IF NOT EXISTS drop_percentage NUMERIC;
ALTER TABLE dropping_alarms ADD COLUMN IF NOT EXISTS level TEXT;

ALTER TABLE publicmove_alarms ADD COLUMN IF NOT EXISTS share_before NUMERIC;
ALTER TABLE publicmove_alarms ADD COLUMN IF NOT EXISTS share_after NUMERIC;
ALTER TABLE publicmove_alarms ADD COLUMN IF NOT EXISTS delta NUMERIC;

-- ==============================================================================
-- FİNAL KONTROL
-- ==============================================================================
SELECT 'SmartXFlow Schema V3.0 - Minimal ve Temiz - Başarıyla Oluşturuldu!' as result;
SELECT 
    COUNT(*) as total_tables,
    'Aktif tablo sayısı' as description
FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_type = 'BASE TABLE';
