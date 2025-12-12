-- ============================================
-- SmartXFlow Phase 2 - Fixtures & Snapshots Schema
-- Per replit.md Immutable Database Contract
-- ============================================

-- 1. FIXTURES TABLE
-- Central table for all matches with unique match_id_hash
CREATE TABLE IF NOT EXISTS fixtures (
    internal_id SERIAL PRIMARY KEY,
    match_id_hash VARCHAR(12) NOT NULL UNIQUE,
    home_team VARCHAR(100) NOT NULL,
    away_team VARCHAR(100) NOT NULL,
    league VARCHAR(150) NOT NULL,
    kickoff_utc TIMESTAMP WITH TIME ZONE NOT NULL,
    fixture_date DATE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for fixtures
CREATE INDEX IF NOT EXISTS idx_fixtures_hash ON fixtures(match_id_hash);
CREATE INDEX IF NOT EXISTS idx_fixtures_date ON fixtures(fixture_date);
CREATE INDEX IF NOT EXISTS idx_fixtures_kickoff ON fixtures(kickoff_utc);

-- 2. MONEYWAY_SNAPSHOTS TABLE
-- Time-series moneyway data linked via match_id_hash
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

-- Indexes for moneyway_snapshots
CREATE INDEX IF NOT EXISTS idx_mw_hash ON moneyway_snapshots(match_id_hash);
CREATE INDEX IF NOT EXISTS idx_mw_scraped ON moneyway_snapshots(scraped_at_utc);
CREATE INDEX IF NOT EXISTS idx_mw_market ON moneyway_snapshots(market, selection);

-- 3. DROPPING_ODDS_SNAPSHOTS TABLE
-- Time-series dropping odds data linked via match_id_hash
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

-- Indexes for dropping_odds_snapshots
CREATE INDEX IF NOT EXISTS idx_do_hash ON dropping_odds_snapshots(match_id_hash);
CREATE INDEX IF NOT EXISTS idx_do_scraped ON dropping_odds_snapshots(scraped_at_utc);
CREATE INDEX IF NOT EXISTS idx_do_market ON dropping_odds_snapshots(market, selection);

-- ============================================
-- RPC FUNCTION: get_full_match_snapshot
-- Returns all data for a match by match_id_hash
-- ============================================
CREATE OR REPLACE FUNCTION get_full_match_snapshot(p_match_id_hash VARCHAR(12))
RETURNS JSON AS $$
DECLARE
    result JSON;
    fixture_record RECORD;
    moneyway_data JSON;
    dropping_data JSON;
BEGIN
    -- Get fixture metadata
    SELECT internal_id, match_id_hash, home_team, away_team, league, 
           kickoff_utc, fixture_date, created_at
    INTO fixture_record
    FROM fixtures
    WHERE match_id_hash = p_match_id_hash;
    
    -- Get moneyway snapshots
    SELECT json_agg(row_to_json(m))
    INTO moneyway_data
    FROM (
        SELECT market, selection, odds, volume, share, scraped_at_utc
        FROM moneyway_snapshots
        WHERE match_id_hash = p_match_id_hash
        ORDER BY scraped_at_utc DESC
    ) m;
    
    -- Get dropping odds snapshots
    SELECT json_agg(row_to_json(d))
    INTO dropping_data
    FROM (
        SELECT market, selection, opening_odds, current_odds, drop_pct, volume, scraped_at_utc
        FROM dropping_odds_snapshots
        WHERE match_id_hash = p_match_id_hash
        ORDER BY scraped_at_utc DESC
    ) d;
    
    -- Build result JSON
    result := json_build_object(
        'metadata', CASE WHEN fixture_record IS NOT NULL THEN
            json_build_object(
                'match_id', fixture_record.match_id_hash,
                'internal_id', fixture_record.internal_id,
                'home', fixture_record.home_team,
                'away', fixture_record.away_team,
                'league', fixture_record.league,
                'kickoff_utc', fixture_record.kickoff_utc,
                'fixture_date', fixture_record.fixture_date,
                'source', 'fixture_table'
            )
        ELSE
            json_build_object(
                'match_id', p_match_id_hash,
                'internal_id', NULL,
                'home', NULL,
                'away', NULL,
                'league', NULL,
                'kickoff_utc', NULL,
                'fixture_date', NULL,
                'source', 'not_found'
            )
        END,
        'moneyway', COALESCE(moneyway_data, '[]'::json),
        'dropping_odds', COALESCE(dropping_data, '[]'::json),
        'updated_at_utc', NOW()
    );
    
    RETURN result;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- COMMENTS
-- ============================================
COMMENT ON TABLE fixtures IS 'Central table for all matches - Phase 2 schema per replit.md contract';
COMMENT ON COLUMN fixtures.match_id_hash IS '12-char MD5 hash: league|kickoff|home|away normalized';
COMMENT ON TABLE moneyway_snapshots IS 'Time-series moneyway data with FK to fixtures';
COMMENT ON TABLE dropping_odds_snapshots IS 'Time-series dropping odds data with FK to fixtures';
COMMENT ON FUNCTION get_full_match_snapshot IS 'RPC function for /api/match/<hash>/snapshot endpoint';
