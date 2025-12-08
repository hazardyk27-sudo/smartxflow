-- SmartXFlow Performance Indexes
-- Bu script Supabase SQL Editor'de çalıştırılmalıdır
-- UI ile uyumlu - mevcut yapıyı değiştirmez, sadece indeks ekler

-- =====================================================
-- MONEYWAY HISTORY TABLOLARI
-- =====================================================

-- moneyway_1x2_history: home, away, scraped_at için composite index
CREATE INDEX IF NOT EXISTS idx_moneyway_1x2_history_home_away 
ON moneyway_1x2_history(home, away);

CREATE INDEX IF NOT EXISTS idx_moneyway_1x2_history_scraped_at 
ON moneyway_1x2_history(scraped_at DESC);

CREATE INDEX IF NOT EXISTS idx_moneyway_1x2_history_date 
ON moneyway_1x2_history(date);

-- moneyway_ou25_history
CREATE INDEX IF NOT EXISTS idx_moneyway_ou25_history_home_away 
ON moneyway_ou25_history(home, away);

CREATE INDEX IF NOT EXISTS idx_moneyway_ou25_history_scraped_at 
ON moneyway_ou25_history(scraped_at DESC);

CREATE INDEX IF NOT EXISTS idx_moneyway_ou25_history_date 
ON moneyway_ou25_history(date);

-- moneyway_btts_history
CREATE INDEX IF NOT EXISTS idx_moneyway_btts_history_home_away 
ON moneyway_btts_history(home, away);

CREATE INDEX IF NOT EXISTS idx_moneyway_btts_history_scraped_at 
ON moneyway_btts_history(scraped_at DESC);

CREATE INDEX IF NOT EXISTS idx_moneyway_btts_history_date 
ON moneyway_btts_history(date);

-- =====================================================
-- DROPPING HISTORY TABLOLARI
-- =====================================================

-- dropping_1x2_history
CREATE INDEX IF NOT EXISTS idx_dropping_1x2_history_home_away 
ON dropping_1x2_history(home, away);

CREATE INDEX IF NOT EXISTS idx_dropping_1x2_history_scraped_at 
ON dropping_1x2_history(scraped_at DESC);

CREATE INDEX IF NOT EXISTS idx_dropping_1x2_history_date 
ON dropping_1x2_history(date);

-- dropping_ou25_history
CREATE INDEX IF NOT EXISTS idx_dropping_ou25_history_home_away 
ON dropping_ou25_history(home, away);

CREATE INDEX IF NOT EXISTS idx_dropping_ou25_history_scraped_at 
ON dropping_ou25_history(scraped_at DESC);

CREATE INDEX IF NOT EXISTS idx_dropping_ou25_history_date 
ON dropping_ou25_history(date);

-- dropping_btts_history
CREATE INDEX IF NOT EXISTS idx_dropping_btts_history_home_away 
ON dropping_btts_history(home, away);

CREATE INDEX IF NOT EXISTS idx_dropping_btts_history_scraped_at 
ON dropping_btts_history(scraped_at DESC);

CREATE INDEX IF NOT EXISTS idx_dropping_btts_history_date 
ON dropping_btts_history(date);

-- =====================================================
-- ALARM TABLOLARI
-- =====================================================

-- sharp_alarms
CREATE INDEX IF NOT EXISTS idx_sharp_alarms_created_at 
ON sharp_alarms(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_sharp_alarms_match 
ON sharp_alarms(home, away);

-- insider_alarms
CREATE INDEX IF NOT EXISTS idx_insider_alarms_created_at 
ON insider_alarms(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_insider_alarms_match 
ON insider_alarms(home, away);

-- bigmoney_alarms
CREATE INDEX IF NOT EXISTS idx_bigmoney_alarms_created_at 
ON bigmoney_alarms(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_bigmoney_alarms_match 
ON bigmoney_alarms(home, away);

-- volumeshock_alarms
CREATE INDEX IF NOT EXISTS idx_volumeshock_alarms_created_at 
ON volumeshock_alarms(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_volumeshock_alarms_match 
ON volumeshock_alarms(home, away);

-- dropping_alarms
CREATE INDEX IF NOT EXISTS idx_dropping_alarms_created_at 
ON dropping_alarms(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_dropping_alarms_match 
ON dropping_alarms(home, away);

-- publicmove_alarms
CREATE INDEX IF NOT EXISTS idx_publicmove_alarms_created_at 
ON publicmove_alarms(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_publicmove_alarms_match 
ON publicmove_alarms(home, away);

-- volume_leader_alarms
CREATE INDEX IF NOT EXISTS idx_volume_leader_alarms_created_at 
ON volume_leader_alarms(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_volume_leader_alarms_match 
ON volume_leader_alarms(home, away);

-- =====================================================
-- MATCHES TABLOSU
-- =====================================================

CREATE INDEX IF NOT EXISTS idx_matches_teams 
ON matches(home_team, away_team);

CREATE INDEX IF NOT EXISTS idx_matches_date 
ON matches(match_date);

CREATE INDEX IF NOT EXISTS idx_matches_created_at 
ON matches(created_at DESC);

-- =====================================================
-- ANALYZE (İstatistikleri güncelle)
-- =====================================================

ANALYZE moneyway_1x2_history;
ANALYZE moneyway_ou25_history;
ANALYZE moneyway_btts_history;
ANALYZE dropping_1x2_history;
ANALYZE dropping_ou25_history;
ANALYZE dropping_btts_history;
ANALYZE sharp_alarms;
ANALYZE insider_alarms;
ANALYZE bigmoney_alarms;
ANALYZE volumeshock_alarms;
ANALYZE dropping_alarms;
ANALYZE publicmove_alarms;
ANALYZE volume_leader_alarms;
ANALYZE matches;

-- =====================================================
-- VERIFY INDEXES (Kontrol için)
-- =====================================================

-- Oluşturulan indeksleri görmek için:
-- SELECT indexname, tablename FROM pg_indexes WHERE schemaname = 'public' ORDER BY tablename;
