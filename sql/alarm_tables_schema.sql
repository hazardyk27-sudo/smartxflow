-- ALARM TABLOLARI - HASH BAZLI (match_id_hash)
-- String eslesmesi YOK - sadece match_id_hash ile join

-- 1. SHARP ALARMS
CREATE TABLE IF NOT EXISTS sharp_alarms (
    id SERIAL PRIMARY KEY,
    match_id_hash VARCHAR(12) NOT NULL REFERENCES fixtures(match_id_hash),
    home VARCHAR(100) NOT NULL,  -- display only
    away VARCHAR(100) NOT NULL,  -- display only
    league VARCHAR(150),
    market VARCHAR(20) NOT NULL,
    selection VARCHAR(20) NOT NULL,
    alarm_type VARCHAR(20) DEFAULT 'sharp',
    trigger_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    odds_change DECIMAL(6,2),
    amount_change DECIMAL(12,2),
    share_change DECIMAL(5,2),
    alarm_history JSONB DEFAULT '[]',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (match_id_hash, market, selection, alarm_type)
);

-- 2. INSIDER ALARMS
CREATE TABLE IF NOT EXISTS insider_alarms (
    id SERIAL PRIMARY KEY,
    match_id_hash VARCHAR(12) NOT NULL REFERENCES fixtures(match_id_hash),
    home VARCHAR(100) NOT NULL,
    away VARCHAR(100) NOT NULL,
    league VARCHAR(150),
    market VARCHAR(20) NOT NULL,
    selection VARCHAR(20) NOT NULL,
    alarm_type VARCHAR(20) DEFAULT 'insider',
    trigger_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    opening_odds DECIMAL(6,2),
    current_odds DECIMAL(6,2),
    drop_pct DECIMAL(5,2),
    total_money DECIMAL(12,2),
    alarm_history JSONB DEFAULT '[]',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (match_id_hash, market, selection, alarm_type)
);

-- 3. BIGMONEY ALARMS
CREATE TABLE IF NOT EXISTS bigmoney_alarms (
    id SERIAL PRIMARY KEY,
    match_id_hash VARCHAR(12) NOT NULL REFERENCES fixtures(match_id_hash),
    home VARCHAR(100) NOT NULL,
    away VARCHAR(100) NOT NULL,
    league VARCHAR(150),
    market VARCHAR(20) NOT NULL,
    selection VARCHAR(20) NOT NULL,
    alarm_type VARCHAR(20) DEFAULT 'bigmoney',
    trigger_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    incoming_money DECIMAL(12,2),
    total_selection DECIMAL(12,2),
    is_huge BOOLEAN DEFAULT FALSE,
    alarm_history JSONB DEFAULT '[]',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (match_id_hash, market, selection, alarm_type)
);

-- 4. VOLUMESHOCK ALARMS
CREATE TABLE IF NOT EXISTS volumeshock_alarms (
    id SERIAL PRIMARY KEY,
    match_id_hash VARCHAR(12) NOT NULL REFERENCES fixtures(match_id_hash),
    home VARCHAR(100) NOT NULL,
    away VARCHAR(100) NOT NULL,
    league VARCHAR(150),
    market VARCHAR(20) NOT NULL,
    selection VARCHAR(20) NOT NULL,
    alarm_type VARCHAR(20) DEFAULT 'volumeshock',
    trigger_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    incoming_money DECIMAL(12,2),
    avg_previous DECIMAL(12,2),
    volume_shock_value DECIMAL(6,2),
    alarm_history JSONB DEFAULT '[]',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (match_id_hash, market, selection, alarm_type)
);

-- 5. DROPPING ALARMS
CREATE TABLE IF NOT EXISTS dropping_alarms (
    id SERIAL PRIMARY KEY,
    match_id_hash VARCHAR(12) NOT NULL REFERENCES fixtures(match_id_hash),
    home VARCHAR(100) NOT NULL,
    away VARCHAR(100) NOT NULL,
    league VARCHAR(150),
    market VARCHAR(20) NOT NULL,
    selection VARCHAR(20) NOT NULL,
    alarm_type VARCHAR(20) DEFAULT 'dropping',
    trigger_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    opening_odds DECIMAL(6,2),
    current_odds DECIMAL(6,2),
    drop_pct DECIMAL(5,2),
    alarm_history JSONB DEFAULT '[]',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (match_id_hash, market, selection, alarm_type)
);

-- 6. PUBLICMOVE ALARMS
CREATE TABLE IF NOT EXISTS publicmove_alarms (
    id SERIAL PRIMARY KEY,
    match_id_hash VARCHAR(12) NOT NULL REFERENCES fixtures(match_id_hash),
    home VARCHAR(100) NOT NULL,
    away VARCHAR(100) NOT NULL,
    league VARCHAR(150),
    market VARCHAR(20) NOT NULL,
    selection VARCHAR(20) NOT NULL,
    alarm_type VARCHAR(20) DEFAULT 'publicmove',
    trigger_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    odds_direction VARCHAR(10),
    share_direction VARCHAR(10),
    current_odds DECIMAL(6,2),
    current_share DECIMAL(5,2),
    alarm_history JSONB DEFAULT '[]',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (match_id_hash, market, selection, alarm_type)
);

-- 7. VOLUMELEADER ALARMS
CREATE TABLE IF NOT EXISTS volumeleader_alarms (
    id SERIAL PRIMARY KEY,
    match_id_hash VARCHAR(12) NOT NULL REFERENCES fixtures(match_id_hash),
    home VARCHAR(100) NOT NULL,
    away VARCHAR(100) NOT NULL,
    league VARCHAR(150),
    market VARCHAR(20) NOT NULL,
    old_leader VARCHAR(20),
    new_leader VARCHAR(20) NOT NULL,
    alarm_type VARCHAR(20) DEFAULT 'volumeleader',
    trigger_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    old_leader_share DECIMAL(5,2),
    new_leader_share DECIMAL(5,2),
    alarm_history JSONB DEFAULT '[]',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (match_id_hash, market, new_leader, alarm_type)
);

-- 8. MIM ALARMS
CREATE TABLE IF NOT EXISTS mim_alarms (
    id SERIAL PRIMARY KEY,
    match_id_hash VARCHAR(12) NOT NULL REFERENCES fixtures(match_id_hash),
    home VARCHAR(100) NOT NULL,
    away VARCHAR(100) NOT NULL,
    league VARCHAR(150),
    market VARCHAR(20) NOT NULL,
    selection VARCHAR(20),
    alarm_type VARCHAR(20) DEFAULT 'mim',
    trigger_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    impact_value DECIMAL(6,4),
    prev_volume DECIMAL(12,2),
    curr_volume DECIMAL(12,2),
    alarm_history JSONB DEFAULT '[]',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (match_id_hash, market, alarm_type)
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
