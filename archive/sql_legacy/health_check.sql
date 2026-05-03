-- ============================================
-- SmartXFlow Health Check SQL Queries
-- Per replit.md Immutable Contract
-- Run these queries to validate data integrity
-- ============================================

-- ============================================
-- 1. DUPLICATE HASH CONTROL
-- Should return 0 rows - duplicates are NEVER allowed
-- ============================================
SELECT 
    match_id_hash, 
    COUNT(*) as duplicate_count
FROM fixtures 
GROUP BY match_id_hash 
HAVING COUNT(*) > 1;

-- ============================================
-- 2a. ORPHAN MONEYWAY SNAPSHOTS
-- Snapshots without matching fixture (should be 0)
-- ============================================
SELECT 
    s.id, 
    s.match_id_hash,
    s.market,
    s.selection,
    s.scraped_at_utc
FROM moneyway_snapshots s 
LEFT JOIN fixtures f ON f.match_id_hash = s.match_id_hash 
WHERE f.internal_id IS NULL;

-- ============================================
-- 2b. ORPHAN DROPPING ODDS SNAPSHOTS
-- Snapshots without matching fixture (should be 0)
-- ============================================
SELECT 
    d.id, 
    d.match_id_hash,
    d.market,
    d.selection,
    d.scraped_at_utc
FROM dropping_odds_snapshots d 
LEFT JOIN fixtures f ON f.match_id_hash = d.match_id_hash 
WHERE f.internal_id IS NULL;

-- ============================================
-- 3. FIXTURES WITHOUT SNAPSHOTS
-- Fixtures with no moneyway or dropping snapshots
-- ============================================
SELECT 
    f.match_id_hash, 
    f.home_team, 
    f.away_team,
    f.league,
    f.kickoff_utc,
    f.created_at
FROM fixtures f 
LEFT JOIN moneyway_snapshots mw ON mw.match_id_hash = f.match_id_hash 
LEFT JOIN dropping_odds_snapshots do ON do.match_id_hash = f.match_id_hash
WHERE mw.id IS NULL AND do.id IS NULL;

-- ============================================
-- 4. STALE FIXTURES (30+ minutes without snapshot)
-- Fixtures that should have snapshots but don't
-- ============================================
SELECT 
    f.match_id_hash, 
    f.home_team,
    f.away_team,
    f.kickoff_utc,
    COALESCE(
        (SELECT MAX(scraped_at_utc) FROM moneyway_snapshots WHERE match_id_hash = f.match_id_hash),
        (SELECT MAX(scraped_at_utc) FROM dropping_odds_snapshots WHERE match_id_hash = f.match_id_hash)
    ) AS last_snapshot,
    NOW() - COALESCE(
        (SELECT MAX(scraped_at_utc) FROM moneyway_snapshots WHERE match_id_hash = f.match_id_hash),
        (SELECT MAX(scraped_at_utc) FROM dropping_odds_snapshots WHERE match_id_hash = f.match_id_hash),
        f.created_at
    ) AS time_since_last
FROM fixtures f 
WHERE f.kickoff_utc > NOW()
  AND (
    SELECT MAX(scraped_at_utc) 
    FROM moneyway_snapshots 
    WHERE match_id_hash = f.match_id_hash
  ) < NOW() - INTERVAL '30 minutes'
   OR (
    SELECT MAX(scraped_at_utc) 
    FROM moneyway_snapshots 
    WHERE match_id_hash = f.match_id_hash
  ) IS NULL;

-- ============================================
-- 5. SUMMARY STATISTICS
-- Quick overview of data state
-- ============================================
SELECT 
    'fixtures' AS table_name,
    COUNT(*) AS row_count,
    MIN(created_at) AS oldest_record,
    MAX(created_at) AS newest_record
FROM fixtures
UNION ALL
SELECT 
    'moneyway_snapshots' AS table_name,
    COUNT(*) AS row_count,
    MIN(scraped_at_utc) AS oldest_record,
    MAX(scraped_at_utc) AS newest_record
FROM moneyway_snapshots
UNION ALL
SELECT 
    'dropping_odds_snapshots' AS table_name,
    COUNT(*) AS row_count,
    MIN(scraped_at_utc) AS oldest_record,
    MAX(scraped_at_utc) AS newest_record
FROM dropping_odds_snapshots;

-- ============================================
-- 6. FIXTURE FK INTEGRITY CHECK
-- Verify all snapshot fixture_id references are valid
-- ============================================
SELECT 
    'moneyway_snapshots' AS source_table,
    COUNT(*) AS broken_fk_count
FROM moneyway_snapshots s
WHERE NOT EXISTS (SELECT 1 FROM fixtures f WHERE f.internal_id = s.fixture_id)
UNION ALL
SELECT 
    'dropping_odds_snapshots' AS source_table,
    COUNT(*) AS broken_fk_count
FROM dropping_odds_snapshots d
WHERE NOT EXISTS (SELECT 1 FROM fixtures f WHERE f.internal_id = d.fixture_id);

-- ============================================
-- 7. TODAY'S FIXTURES SNAPSHOT COVERAGE
-- Check if today's matches have recent snapshots
-- ============================================
SELECT 
    f.match_id_hash,
    f.home_team,
    f.away_team,
    f.kickoff_utc,
    (SELECT COUNT(*) FROM moneyway_snapshots WHERE match_id_hash = f.match_id_hash) AS mw_snapshot_count,
    (SELECT COUNT(*) FROM dropping_odds_snapshots WHERE match_id_hash = f.match_id_hash) AS do_snapshot_count,
    (SELECT MAX(scraped_at_utc) FROM moneyway_snapshots WHERE match_id_hash = f.match_id_hash) AS last_mw_snapshot,
    (SELECT MAX(scraped_at_utc) FROM dropping_odds_snapshots WHERE match_id_hash = f.match_id_hash) AS last_do_snapshot
FROM fixtures f
WHERE f.fixture_date = CURRENT_DATE
ORDER BY f.kickoff_utc;
