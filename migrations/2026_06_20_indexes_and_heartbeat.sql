-- Migration: 2026-06-20
-- Supabase dashboard SQL Editor'de çalıştır
-- 1. scraper_heartbeat tablosu (master/slave koordinasyonu + watchdog için)
CREATE TABLE IF NOT EXISTS public.scraper_heartbeat (
    source TEXT PRIMARY KEY,
    last_heartbeat TIMESTAMPTZ,
    status TEXT DEFAULT 'unknown',
    match_count INTEGER DEFAULT 0,
    error_message TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. live_snapshots indexleri (781K satır, 435 yazma/dk)
CREATE INDEX IF NOT EXISTS idx_live_snap_hash ON live_snapshots(match_id_hash);
CREATE INDEX IF NOT EXISTS idx_live_snap_at   ON live_snapshots(snapshot_at);

-- 3. moneyway_snapshots indexleri (29M satır — cleanup sonrasi 2.5M olacak)
CREATE INDEX IF NOT EXISTS idx_mw_snap_at   ON moneyway_snapshots(scraped_at_utc);
CREATE INDEX IF NOT EXISTS idx_mw_snap_hash ON moneyway_snapshots(match_id_hash);

-- 4. dropping_odds_snapshots indexleri
CREATE INDEX IF NOT EXISTS idx_do_snap_at   ON dropping_odds_snapshots(scraped_at_utc);
CREATE INDEX IF NOT EXISTS idx_do_snap_hash ON dropping_odds_snapshots(match_id_hash);

-- 5. History tablolari (cleanup + batch fetch icin)
CREATE INDEX IF NOT EXISTS idx_mw1x2_hist_at   ON moneyway_1x2_history(scraped_at);
CREATE INDEX IF NOT EXISTS idx_mwou25_hist_at  ON moneyway_ou25_history(scraped_at);
CREATE INDEX IF NOT EXISTS idx_mwbtts_hist_at  ON moneyway_btts_history(scraped_at);
CREATE INDEX IF NOT EXISTS idx_do1x2_hist_at   ON dropping_1x2_history(scraped_at);
CREATE INDEX IF NOT EXISTS idx_doou25_hist_at  ON dropping_ou25_history(scraped_at);
CREATE INDEX IF NOT EXISTS idx_dobtts_hist_at  ON dropping_btts_history(scraped_at);

-- 6. live_fixtures index
CREATE INDEX IF NOT EXISTS idx_live_fix_date ON live_fixtures(fixture_date);
