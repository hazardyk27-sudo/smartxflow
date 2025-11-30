-- SmartXFlow Supabase Schema
-- Run this in Supabase SQL Editor

-- 1. MATCHES TABLE - Unique matches
CREATE TABLE IF NOT EXISTS matches (
    id BIGSERIAL PRIMARY KEY,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    league TEXT,
    match_date TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(home_team, away_team, match_date)
);

-- 2. ODDS_SNAPSHOTS TABLE - All market data in one table
CREATE TABLE IF NOT EXISTS odds_snapshots (
    id BIGSERIAL PRIMARY KEY,
    match_id BIGINT REFERENCES matches(id) ON DELETE CASCADE,
    market TEXT NOT NULL,
    scraped_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- 1X2 / Dropping 1X2 fields
    odds_1 NUMERIC,
    odds_x NUMERIC,
    odds_2 NUMERIC,
    pct_1 TEXT,
    amt_1 TEXT,
    pct_x TEXT,
    amt_x TEXT,
    pct_2 TEXT,
    amt_2 TEXT,
    trend_1 TEXT,
    trend_x TEXT,
    trend_2 TEXT,
    
    -- O/U 2.5 fields
    under_odds NUMERIC,
    over_odds NUMERIC,
    line TEXT,
    pct_under TEXT,
    amt_under TEXT,
    pct_over TEXT,
    amt_over TEXT,
    trend_under TEXT,
    trend_over TEXT,
    
    -- BTTS fields
    yes_odds NUMERIC,
    no_odds NUMERIC,
    pct_yes TEXT,
    amt_yes TEXT,
    pct_no TEXT,
    amt_no TEXT,
    trend_yes TEXT,
    trend_no TEXT,
    
    -- Common
    volume TEXT
);

-- 3. ALERTS TABLE - Smart Money alarms
CREATE TABLE IF NOT EXISTS alerts (
    id BIGSERIAL PRIMARY KEY,
    match_id BIGINT REFERENCES matches(id) ON DELETE CASCADE,
    alert_type TEXT NOT NULL,
    market TEXT NOT NULL,
    side TEXT,
    money_diff NUMERIC,
    odds_from NUMERIC,
    odds_to NUMERIC,
    details JSONB,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_matches_teams ON matches(home_team, away_team);
CREATE INDEX IF NOT EXISTS idx_snapshots_match_id ON odds_snapshots(match_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_market ON odds_snapshots(market);
CREATE INDEX IF NOT EXISTS idx_snapshots_scraped_at ON odds_snapshots(scraped_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_match_id ON alerts(match_id);
CREATE INDEX IF NOT EXISTS idx_alerts_active ON alerts(is_active) WHERE is_active = TRUE;

-- Enable Row Level Security
ALTER TABLE matches ENABLE ROW LEVEL SECURITY;
ALTER TABLE odds_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE alerts ENABLE ROW LEVEL SECURITY;

-- Allow all access (for development - tighten in production)
DROP POLICY IF EXISTS "Allow all matches" ON matches;
DROP POLICY IF EXISTS "Allow all snapshots" ON odds_snapshots;
DROP POLICY IF EXISTS "Allow all alerts" ON alerts;

CREATE POLICY "Allow all matches" ON matches FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all snapshots" ON odds_snapshots FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all alerts" ON alerts FOR ALL USING (true) WITH CHECK (true);

-- 4. SHARP_CONFIG TABLE - V2 Alarm System Configuration
CREATE TABLE IF NOT EXISTS sharp_config (
    id INT PRIMARY KEY DEFAULT 1,
    
    -- Ağırlıklar (Weights)
    weight_volume NUMERIC DEFAULT 1.0,
    weight_odds NUMERIC DEFAULT 1.0,
    weight_share NUMERIC DEFAULT 0.5,
    weight_momentum NUMERIC DEFAULT 0.5,
    
    -- Çarpanlar
    volume_multiplier NUMERIC DEFAULT 10.0,
    normalization_factor NUMERIC DEFAULT 1.0,
    
    -- Piyasa Hacim Eşikleri (Min Market Volume)
    min_volume_1x2 INT DEFAULT 3000,
    min_volume_ou25 INT DEFAULT 2000,
    min_volume_btts INT DEFAULT 1500,
    
    -- Skor Eşikleri
    sharp_score_threshold INT DEFAULT 50,
    min_share_pct_threshold INT DEFAULT 15,
    
    -- Seviye Eşikleri
    threshold_strong_sharp INT DEFAULT 60,
    threshold_very_sharp INT DEFAULT 75,
    threshold_real_sharp INT DEFAULT 90,
    
    -- Hacim Şoku Aralıkları (JSON)
    shock_ranges JSONB DEFAULT '{"normal": [0, 2], "light": [2, 4], "strong": [4, 6], "very_strong": [6, 8], "extreme": [8, 999]}',
    
    -- Meta
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    updated_by VARCHAR(100),
    
    -- Tek satır constraint
    CONSTRAINT single_row CHECK (id = 1)
);

-- Varsayılan satırı ekle
INSERT INTO sharp_config (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

-- RLS for sharp_config
ALTER TABLE sharp_config ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Allow all sharp_config" ON sharp_config;
CREATE POLICY "Allow all sharp_config" ON sharp_config FOR ALL USING (true) WITH CHECK (true);
