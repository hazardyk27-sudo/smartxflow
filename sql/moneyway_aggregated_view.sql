-- =====================================================
-- MONEYWAY AGGREGATED VIEW
-- Selection'ları pivot ederek eski şema formatına dönüştürür
-- BigMoney/VolumeShock hesaplamaları için gerekli
-- =====================================================

-- 1X2 Market için aggregated view
CREATE OR REPLACE VIEW moneyway_1x2_latest AS
WITH latest_snapshots AS (
    SELECT DISTINCT ON (match_id_hash, selection)
        match_id_hash,
        selection,
        volume,
        odds,
        share,
        scraped_at_utc
    FROM moneyway_snapshots
    WHERE market = '1X2'
    ORDER BY match_id_hash, selection, scraped_at_utc DESC
),
pivoted AS (
    SELECT 
        match_id_hash,
        MAX(scraped_at_utc) as scraped_at,
        MAX(CASE WHEN selection = '1' THEN volume ELSE 0 END) as vol_1,
        MAX(CASE WHEN selection = 'X' THEN volume ELSE 0 END) as vol_x,
        MAX(CASE WHEN selection = '2' THEN volume ELSE 0 END) as vol_2,
        MAX(CASE WHEN selection = '1' THEN odds ELSE 0 END) as odds_1,
        MAX(CASE WHEN selection = 'X' THEN odds ELSE 0 END) as odds_x,
        MAX(CASE WHEN selection = '2' THEN odds ELSE 0 END) as odds_2,
        MAX(CASE WHEN selection = '1' THEN share ELSE 0 END) as pct_1,
        MAX(CASE WHEN selection = 'X' THEN share ELSE 0 END) as pct_x,
        MAX(CASE WHEN selection = '2' THEN share ELSE 0 END) as pct_2
    FROM latest_snapshots
    GROUP BY match_id_hash
)
SELECT 
    p.*,
    f.home_team as home,
    f.away_team as away,
    f.league,
    f.kickoff_utc as date,
    f.fixture_date as match_date
FROM pivoted p
LEFT JOIN fixtures f ON f.match_id_hash = p.match_id_hash;

-- O/U 2.5 Market için aggregated view
CREATE OR REPLACE VIEW moneyway_ou25_latest AS
WITH latest_snapshots AS (
    SELECT DISTINCT ON (match_id_hash, selection)
        match_id_hash,
        selection,
        volume,
        odds,
        share,
        scraped_at_utc
    FROM moneyway_snapshots
    WHERE market = 'O/U 2.5'
    ORDER BY match_id_hash, selection, scraped_at_utc DESC
),
pivoted AS (
    SELECT 
        match_id_hash,
        MAX(scraped_at_utc) as scraped_at,
        MAX(CASE WHEN selection = 'Over' THEN volume ELSE 0 END) as vol_over,
        MAX(CASE WHEN selection = 'Under' THEN volume ELSE 0 END) as vol_under,
        MAX(CASE WHEN selection = 'Over' THEN odds ELSE 0 END) as odds_over,
        MAX(CASE WHEN selection = 'Under' THEN odds ELSE 0 END) as odds_under,
        MAX(CASE WHEN selection = 'Over' THEN share ELSE 0 END) as pct_over,
        MAX(CASE WHEN selection = 'Under' THEN share ELSE 0 END) as pct_under
    FROM latest_snapshots
    GROUP BY match_id_hash
)
SELECT 
    p.*,
    f.home_team as home,
    f.away_team as away,
    f.league,
    f.kickoff_utc as date,
    f.fixture_date as match_date
FROM pivoted p
LEFT JOIN fixtures f ON f.match_id_hash = p.match_id_hash;

-- BTTS Market için aggregated view
CREATE OR REPLACE VIEW moneyway_btts_latest AS
WITH latest_snapshots AS (
    SELECT DISTINCT ON (match_id_hash, selection)
        match_id_hash,
        selection,
        volume,
        odds,
        share,
        scraped_at_utc
    FROM moneyway_snapshots
    WHERE market = 'BTTS'
    ORDER BY match_id_hash, selection, scraped_at_utc DESC
),
pivoted AS (
    SELECT 
        match_id_hash,
        MAX(scraped_at_utc) as scraped_at,
        MAX(CASE WHEN selection = 'Yes' THEN volume ELSE 0 END) as vol_yes,
        MAX(CASE WHEN selection = 'No' THEN volume ELSE 0 END) as vol_no,
        MAX(CASE WHEN selection = 'Yes' THEN odds ELSE 0 END) as odds_yes,
        MAX(CASE WHEN selection = 'No' THEN odds ELSE 0 END) as odds_no,
        MAX(CASE WHEN selection = 'Yes' THEN share ELSE 0 END) as pct_yes,
        MAX(CASE WHEN selection = 'No' THEN share ELSE 0 END) as pct_no
    FROM latest_snapshots
    GROUP BY match_id_hash
)
SELECT 
    p.*,
    f.home_team as home,
    f.away_team as away,
    f.league,
    f.kickoff_utc as date,
    f.fixture_date as match_date
FROM pivoted p
LEFT JOIN fixtures f ON f.match_id_hash = p.match_id_hash;

-- =====================================================
-- KONTROL
-- =====================================================
-- View'ları test et
-- SELECT * FROM moneyway_1x2_latest LIMIT 5;
-- SELECT * FROM moneyway_ou25_latest LIMIT 5;
-- SELECT * FROM moneyway_btts_latest LIMIT 5;
