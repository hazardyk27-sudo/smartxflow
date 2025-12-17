-- ALARM TABLOLARI - HASH BAZLI (match_id_hash)
-- String eslesmesi YOK - sadece match_id_hash ile join
-- RLS AKTIF - Client sadece okur, Scraper/Admin service role ile yazar
-- FK YOK - Bagimsiz tablolar (fixtures'a bagimlilik kaldirildi)

CREATE TABLE IF NOT EXISTS sharp_alarms (
    id SERIAL PRIMARY KEY,
    match_id_hash VARCHAR(12) NOT NULL,
    home VARCHAR(100) NOT NULL,
    away VARCHAR(100) NOT NULL,
    league VARCHAR(150),
    market VARCHAR(20) NOT NULL,
    selection VARCHAR(20) NOT NULL,
    trigger_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    odds_change DECIMAL(6,2),
    amount_change DECIMAL(12,2),
    share_change DECIMAL(5,2),
    alarm_history JSONB DEFAULT '[]',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT sharp_hash_len CHECK (char_length(match_id_hash) = 12),
    UNIQUE (match_id_hash, market, selection)
);

CREATE TABLE IF NOT EXISTS insider_alarms (
    id SERIAL PRIMARY KEY,
    match_id_hash VARCHAR(12) NOT NULL,
    home VARCHAR(100) NOT NULL,
    away VARCHAR(100) NOT NULL,
    league VARCHAR(150),
    market VARCHAR(20) NOT NULL,
    selection VARCHAR(20) NOT NULL,
    trigger_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    opening_odds DECIMAL(6,2),
    current_odds DECIMAL(6,2),
    drop_pct DECIMAL(5,2),
    total_money DECIMAL(12,2),
    alarm_history JSONB DEFAULT '[]',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT insider_hash_len CHECK (char_length(match_id_hash) = 12),
    UNIQUE (match_id_hash, market, selection)
);

CREATE TABLE IF NOT EXISTS bigmoney_alarms (
    id SERIAL PRIMARY KEY,
    match_id_hash VARCHAR(12) NOT NULL,
    home VARCHAR(100) NOT NULL,
    away VARCHAR(100) NOT NULL,
    league VARCHAR(150),
    market VARCHAR(20) NOT NULL,
    selection VARCHAR(20) NOT NULL,
    trigger_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    incoming_money DECIMAL(12,2),
    total_selection DECIMAL(12,2),
    is_huge BOOLEAN DEFAULT FALSE,
    alarm_history JSONB DEFAULT '[]',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT bigmoney_hash_len CHECK (char_length(match_id_hash) = 12),
    UNIQUE (match_id_hash, market, selection)
);

CREATE TABLE IF NOT EXISTS volumeshock_alarms (
    id SERIAL PRIMARY KEY,
    match_id_hash VARCHAR(12) NOT NULL,
    home VARCHAR(100) NOT NULL,
    away VARCHAR(100) NOT NULL,
    league VARCHAR(150),
    market VARCHAR(20) NOT NULL,
    selection VARCHAR(20) NOT NULL,
    trigger_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    incoming_money DECIMAL(12,2),
    avg_previous DECIMAL(12,2),
    volume_shock_value DECIMAL(6,2),
    alarm_history JSONB DEFAULT '[]',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT volumeshock_hash_len CHECK (char_length(match_id_hash) = 12),
    UNIQUE (match_id_hash, market, selection)
);

CREATE TABLE IF NOT EXISTS dropping_alarms (
    id SERIAL PRIMARY KEY,
    match_id_hash VARCHAR(12) NOT NULL,
    home VARCHAR(100) NOT NULL,
    away VARCHAR(100) NOT NULL,
    league VARCHAR(150),
    market VARCHAR(20) NOT NULL,
    selection VARCHAR(20) NOT NULL,
    trigger_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    opening_odds DECIMAL(6,2),
    current_odds DECIMAL(6,2),
    drop_pct DECIMAL(5,2),
    alarm_history JSONB DEFAULT '[]',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT dropping_hash_len CHECK (char_length(match_id_hash) = 12),
    UNIQUE (match_id_hash, market, selection)
);

CREATE TABLE IF NOT EXISTS publicmove_alarms (
    id SERIAL PRIMARY KEY,
    match_id_hash VARCHAR(12) NOT NULL,
    home VARCHAR(100) NOT NULL,
    away VARCHAR(100) NOT NULL,
    league VARCHAR(150),
    market VARCHAR(20) NOT NULL,
    selection VARCHAR(20) NOT NULL,
    trigger_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    odds_direction VARCHAR(10),
    share_direction VARCHAR(10),
    current_odds DECIMAL(6,2),
    current_share DECIMAL(5,2),
    alarm_history JSONB DEFAULT '[]',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT publicmove_hash_len CHECK (char_length(match_id_hash) = 12),
    UNIQUE (match_id_hash, market, selection)
);

CREATE TABLE IF NOT EXISTS volumeleader_alarms (
    id SERIAL PRIMARY KEY,
    match_id_hash VARCHAR(12) NOT NULL,
    home VARCHAR(100) NOT NULL,
    away VARCHAR(100) NOT NULL,
    league VARCHAR(150),
    market VARCHAR(20) NOT NULL,
    old_leader VARCHAR(20),
    new_leader VARCHAR(20) NOT NULL,
    trigger_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    old_leader_share DECIMAL(5,2),
    new_leader_share DECIMAL(5,2),
    alarm_history JSONB DEFAULT '[]',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT volumeleader_hash_len CHECK (char_length(match_id_hash) = 12),
    UNIQUE (match_id_hash, market, new_leader)
);

CREATE TABLE IF NOT EXISTS mim_alarms (
    id SERIAL PRIMARY KEY,
    match_id_hash VARCHAR(12) NOT NULL,
    home VARCHAR(100) NOT NULL,
    away VARCHAR(100) NOT NULL,
    league VARCHAR(150),
    market VARCHAR(20) NOT NULL,
    selection VARCHAR(20),
    trigger_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    impact_value DECIMAL(6,4),
    prev_volume DECIMAL(12,2),
    curr_volume DECIMAL(12,2),
    alarm_history JSONB DEFAULT '[]',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT mim_hash_len CHECK (char_length(match_id_hash) = 12),
    UNIQUE (match_id_hash, market)
);

-- INDEXES
CREATE INDEX IF NOT EXISTS idx_sharp_hash ON sharp_alarms(match_id_hash);
CREATE INDEX IF NOT EXISTS idx_insider_hash ON insider_alarms(match_id_hash);
CREATE INDEX IF NOT EXISTS idx_bigmoney_hash ON bigmoney_alarms(match_id_hash);
CREATE INDEX IF NOT EXISTS idx_volumeshock_hash ON volumeshock_alarms(match_id_hash);
CREATE INDEX IF NOT EXISTS idx_dropping_hash ON dropping_alarms(match_id_hash);
CREATE INDEX IF NOT EXISTS idx_publicmove_hash ON publicmove_alarms(match_id_hash);
CREATE INDEX IF NOT EXISTS idx_volumeleader_hash ON volumeleader_alarms(match_id_hash);
CREATE INDEX IF NOT EXISTS idx_mim_hash ON mim_alarms(match_id_hash);

CREATE INDEX IF NOT EXISTS idx_sharp_trigger ON sharp_alarms(trigger_at);
CREATE INDEX IF NOT EXISTS idx_insider_trigger ON insider_alarms(trigger_at);
CREATE INDEX IF NOT EXISTS idx_bigmoney_trigger ON bigmoney_alarms(trigger_at);
CREATE INDEX IF NOT EXISTS idx_volumeshock_trigger ON volumeshock_alarms(trigger_at);
CREATE INDEX IF NOT EXISTS idx_dropping_trigger ON dropping_alarms(trigger_at);
CREATE INDEX IF NOT EXISTS idx_publicmove_trigger ON publicmove_alarms(trigger_at);
CREATE INDEX IF NOT EXISTS idx_volumeleader_trigger ON volumeleader_alarms(trigger_at);
CREATE INDEX IF NOT EXISTS idx_mim_trigger ON mim_alarms(trigger_at);

-- RLS AKTIF ET
ALTER TABLE sharp_alarms ENABLE ROW LEVEL SECURITY;
ALTER TABLE insider_alarms ENABLE ROW LEVEL SECURITY;
ALTER TABLE bigmoney_alarms ENABLE ROW LEVEL SECURITY;
ALTER TABLE volumeshock_alarms ENABLE ROW LEVEL SECURITY;
ALTER TABLE dropping_alarms ENABLE ROW LEVEL SECURITY;
ALTER TABLE publicmove_alarms ENABLE ROW LEVEL SECURITY;
ALTER TABLE volumeleader_alarms ENABLE ROW LEVEL SECURITY;
ALTER TABLE mim_alarms ENABLE ROW LEVEL SECURITY;

-- SELECT POLICY - Herkes okuyabilir (anon dahil)
CREATE POLICY "Allow public read sharp" ON sharp_alarms FOR SELECT USING (true);
CREATE POLICY "Allow public read insider" ON insider_alarms FOR SELECT USING (true);
CREATE POLICY "Allow public read bigmoney" ON bigmoney_alarms FOR SELECT USING (true);
CREATE POLICY "Allow public read volumeshock" ON volumeshock_alarms FOR SELECT USING (true);
CREATE POLICY "Allow public read dropping" ON dropping_alarms FOR SELECT USING (true);
CREATE POLICY "Allow public read publicmove" ON publicmove_alarms FOR SELECT USING (true);
CREATE POLICY "Allow public read volumeleader" ON volumeleader_alarms FOR SELECT USING (true);
CREATE POLICY "Allow public read mim" ON mim_alarms FOR SELECT USING (true);

-- INSERT/UPDATE/DELETE YOK - Service role RLS'yi bypass eder
-- Client tarafindan yazma denemesi otomatik olarak reddedilir
