-- SmartXFlow Eksik Tablolar
-- Bu SQL'i Supabase SQL Editor'de çalıştırın

-- moneyway_snapshots tablosu
CREATE TABLE IF NOT EXISTS moneyway_snapshots (
  id SERIAL PRIMARY KEY,
  match_id_hash VARCHAR(12) NOT NULL,
  market VARCHAR(10) NOT NULL,
  selection VARCHAR(10) NOT NULL,
  odds DECIMAL(6,2),
  volume DECIMAL(12,2),
  share DECIMAL(5,2),
  scraped_at_utc TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_mw_snap_hash ON moneyway_snapshots(match_id_hash);
CREATE INDEX IF NOT EXISTS idx_mw_snap_scraped ON moneyway_snapshots(scraped_at_utc);

-- dropping_odds_snapshots tablosu
CREATE TABLE IF NOT EXISTS dropping_odds_snapshots (
  id SERIAL PRIMARY KEY,
  match_id_hash VARCHAR(12) NOT NULL,
  market VARCHAR(10) NOT NULL,
  selection VARCHAR(10) NOT NULL,
  opening_odds DECIMAL(6,2),
  current_odds DECIMAL(6,2),
  drop_pct DECIMAL(5,2),
  volume DECIMAL(12,2),
  scraped_at_utc TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_do_snap_hash ON dropping_odds_snapshots(match_id_hash);
CREATE INDEX IF NOT EXISTS idx_do_snap_scraped ON dropping_odds_snapshots(scraped_at_utc);

-- alarm_config tablosu
CREATE TABLE IF NOT EXISTS alarm_config (
  id SERIAL PRIMARY KEY,
  alarm_type VARCHAR(50) NOT NULL UNIQUE,
  config JSONB NOT NULL DEFAULT '{}',
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Alarm tabloları
CREATE TABLE IF NOT EXISTS alarms_sharp (
  id SERIAL PRIMARY KEY,
  match_id_hash VARCHAR(12),
  home VARCHAR(100),
  away VARCHAR(100),
  league VARCHAR(150),
  market VARCHAR(20),
  selection VARCHAR(10),
  event_time TIMESTAMP WITH TIME ZONE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  data JSONB
);

CREATE TABLE IF NOT EXISTS alarms_insider (
  id SERIAL PRIMARY KEY,
  match_id_hash VARCHAR(12),
  home VARCHAR(100),
  away VARCHAR(100),
  league VARCHAR(150),
  market VARCHAR(20),
  selection VARCHAR(10),
  event_time TIMESTAMP WITH TIME ZONE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  data JSONB
);

CREATE TABLE IF NOT EXISTS alarms_bigmoney (
  id SERIAL PRIMARY KEY,
  match_id_hash VARCHAR(12),
  home VARCHAR(100),
  away VARCHAR(100),
  league VARCHAR(150),
  market VARCHAR(20),
  selection VARCHAR(10),
  incoming_money DECIMAL(12,2),
  event_time TIMESTAMP WITH TIME ZONE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  alarm_history JSONB,
  data JSONB
);

CREATE TABLE IF NOT EXISTS alarms_volumeshock (
  id SERIAL PRIMARY KEY,
  match_id_hash VARCHAR(12),
  home VARCHAR(100),
  away VARCHAR(100),
  league VARCHAR(150),
  market VARCHAR(20),
  selection VARCHAR(10),
  volume_shock_value DECIMAL(10,2),
  event_time TIMESTAMP WITH TIME ZONE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  alarm_history JSONB,
  data JSONB
);

CREATE TABLE IF NOT EXISTS alarms_dropping (
  id SERIAL PRIMARY KEY,
  match_id_hash VARCHAR(12),
  home VARCHAR(100),
  away VARCHAR(100),
  league VARCHAR(150),
  market VARCHAR(20),
  selection VARCHAR(10),
  opening_odds DECIMAL(6,2),
  current_odds DECIMAL(6,2),
  drop_pct DECIMAL(5,2),
  event_time TIMESTAMP WITH TIME ZONE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  data JSONB
);

CREATE TABLE IF NOT EXISTS alarms_publicmove (
  id SERIAL PRIMARY KEY,
  match_id_hash VARCHAR(12),
  home VARCHAR(100),
  away VARCHAR(100),
  league VARCHAR(150),
  market VARCHAR(20),
  selection VARCHAR(10),
  event_time TIMESTAMP WITH TIME ZONE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  data JSONB
);

CREATE TABLE IF NOT EXISTS alarms_volumeleader (
  id SERIAL PRIMARY KEY,
  match_id_hash VARCHAR(12),
  home VARCHAR(100),
  away VARCHAR(100),
  league VARCHAR(150),
  market VARCHAR(20),
  selection VARCHAR(10),
  event_time TIMESTAMP WITH TIME ZONE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  data JSONB
);

CREATE TABLE IF NOT EXISTS alarms_mim (
  id SERIAL PRIMARY KEY,
  match_id_hash VARCHAR(12),
  home VARCHAR(100),
  away VARCHAR(100),
  league VARCHAR(150),
  market VARCHAR(20),
  selection VARCHAR(10),
  mim_value DECIMAL(5,4),
  event_time TIMESTAMP WITH TIME ZONE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  data JSONB
);
