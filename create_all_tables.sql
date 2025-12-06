-- =============================================
-- TÜM TABLOLARI SIFIRDAN OLUŞTUR
-- Supabase SQL Editor'da çalıştır
-- =============================================

-- 1. ESKİ TABLOLARI SİL
DROP TABLE IF EXISTS moneyway_1x2 CASCADE;
DROP TABLE IF EXISTS moneyway_ou25 CASCADE;
DROP TABLE IF EXISTS moneyway_btts CASCADE;
DROP TABLE IF EXISTS dropping_1x2 CASCADE;
DROP TABLE IF EXISTS dropping_ou25 CASCADE;
DROP TABLE IF EXISTS dropping_btts CASCADE;
DROP TABLE IF EXISTS moneyway_1x2_history CASCADE;
DROP TABLE IF EXISTS moneyway_ou25_history CASCADE;
DROP TABLE IF EXISTS moneyway_btts_history CASCADE;
DROP TABLE IF EXISTS dropping_1x2_history CASCADE;
DROP TABLE IF EXISTS dropping_ou25_history CASCADE;
DROP TABLE IF EXISTS dropping_btts_history CASCADE;

-- =============================================
-- MONEYWAY ANA TABLOLAR
-- =============================================

CREATE TABLE moneyway_1x2 (
    id SERIAL PRIMARY KEY,
    league TEXT,
    date TEXT,
    home TEXT,
    odds1 TEXT,
    oddsx TEXT,
    odds2 TEXT,
    pct1 TEXT,
    amt1 TEXT,
    pctx TEXT,
    amtx TEXT,
    pct2 TEXT,
    amt2 TEXT,
    away TEXT,
    volume TEXT
);

CREATE TABLE moneyway_ou25 (
    id SERIAL PRIMARY KEY,
    league TEXT,
    date TEXT,
    home TEXT,
    under TEXT,
    line TEXT,
    over TEXT,
    pctunder TEXT,
    amtunder TEXT,
    pctover TEXT,
    amtover TEXT,
    away TEXT,
    volume TEXT
);

CREATE TABLE moneyway_btts (
    id SERIAL PRIMARY KEY,
    league TEXT,
    date TEXT,
    home TEXT,
    yes TEXT,
    no TEXT,
    pctyes TEXT,
    amtyes TEXT,
    pctno TEXT,
    amtno TEXT,
    away TEXT,
    volume TEXT
);

-- =============================================
-- DROPPING ANA TABLOLAR
-- =============================================

CREATE TABLE dropping_1x2 (
    id SERIAL PRIMARY KEY,
    league TEXT,
    date TEXT,
    home TEXT,
    odds1 TEXT,
    odds1_prev TEXT,
    oddsx TEXT,
    oddsx_prev TEXT,
    odds2 TEXT,
    odds2_prev TEXT,
    trend1 TEXT,
    trendx TEXT,
    trend2 TEXT,
    away TEXT,
    volume TEXT
);

CREATE TABLE dropping_ou25 (
    id SERIAL PRIMARY KEY,
    league TEXT,
    date TEXT,
    home TEXT,
    under TEXT,
    under_prev TEXT,
    line TEXT,
    over TEXT,
    over_prev TEXT,
    trendunder TEXT,
    trendover TEXT,
    pctunder TEXT,
    amtunder TEXT,
    pctover TEXT,
    amtover TEXT,
    away TEXT,
    volume TEXT
);

CREATE TABLE dropping_btts (
    id SERIAL PRIMARY KEY,
    league TEXT,
    date TEXT,
    home TEXT,
    oddsyes TEXT,
    oddsyes_prev TEXT,
    oddsno TEXT,
    oddsno_prev TEXT,
    trendyes TEXT,
    trendno TEXT,
    pctyes TEXT,
    amtyes TEXT,
    pctno TEXT,
    amtno TEXT,
    away TEXT,
    volume TEXT
);

-- =============================================
-- HISTORY TABLOLAR (scraped_at eklendi)
-- =============================================

CREATE TABLE moneyway_1x2_history (
    id SERIAL PRIMARY KEY,
    league TEXT,
    date TEXT,
    home TEXT,
    odds1 TEXT,
    oddsx TEXT,
    odds2 TEXT,
    pct1 TEXT,
    amt1 TEXT,
    pctx TEXT,
    amtx TEXT,
    pct2 TEXT,
    amt2 TEXT,
    away TEXT,
    volume TEXT,
    scraped_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE moneyway_ou25_history (
    id SERIAL PRIMARY KEY,
    league TEXT,
    date TEXT,
    home TEXT,
    under TEXT,
    line TEXT,
    over TEXT,
    pctunder TEXT,
    amtunder TEXT,
    pctover TEXT,
    amtover TEXT,
    away TEXT,
    volume TEXT,
    scraped_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE moneyway_btts_history (
    id SERIAL PRIMARY KEY,
    league TEXT,
    date TEXT,
    home TEXT,
    yes TEXT,
    no TEXT,
    pctyes TEXT,
    amtyes TEXT,
    pctno TEXT,
    amtno TEXT,
    away TEXT,
    volume TEXT,
    scraped_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE dropping_1x2_history (
    id SERIAL PRIMARY KEY,
    league TEXT,
    date TEXT,
    home TEXT,
    odds1 TEXT,
    odds1_prev TEXT,
    oddsx TEXT,
    oddsx_prev TEXT,
    odds2 TEXT,
    odds2_prev TEXT,
    trend1 TEXT,
    trendx TEXT,
    trend2 TEXT,
    away TEXT,
    volume TEXT,
    scraped_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE dropping_ou25_history (
    id SERIAL PRIMARY KEY,
    league TEXT,
    date TEXT,
    home TEXT,
    under TEXT,
    under_prev TEXT,
    line TEXT,
    over TEXT,
    over_prev TEXT,
    trendunder TEXT,
    trendover TEXT,
    pctunder TEXT,
    amtunder TEXT,
    pctover TEXT,
    amtover TEXT,
    away TEXT,
    volume TEXT,
    scraped_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE dropping_btts_history (
    id SERIAL PRIMARY KEY,
    league TEXT,
    date TEXT,
    home TEXT,
    oddsyes TEXT,
    oddsyes_prev TEXT,
    oddsno TEXT,
    oddsno_prev TEXT,
    trendyes TEXT,
    trendno TEXT,
    pctyes TEXT,
    amtyes TEXT,
    pctno TEXT,
    amtno TEXT,
    away TEXT,
    volume TEXT,
    scraped_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================
-- RLS (Row Level Security) - Herkes okuyabilir/yazabilir
-- =============================================

ALTER TABLE moneyway_1x2 ENABLE ROW LEVEL SECURITY;
ALTER TABLE moneyway_ou25 ENABLE ROW LEVEL SECURITY;
ALTER TABLE moneyway_btts ENABLE ROW LEVEL SECURITY;
ALTER TABLE dropping_1x2 ENABLE ROW LEVEL SECURITY;
ALTER TABLE dropping_ou25 ENABLE ROW LEVEL SECURITY;
ALTER TABLE dropping_btts ENABLE ROW LEVEL SECURITY;
ALTER TABLE moneyway_1x2_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE moneyway_ou25_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE moneyway_btts_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE dropping_1x2_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE dropping_ou25_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE dropping_btts_history ENABLE ROW LEVEL SECURITY;

CREATE POLICY "anon_all_moneyway_1x2" ON moneyway_1x2 FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY "anon_all_moneyway_ou25" ON moneyway_ou25 FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY "anon_all_moneyway_btts" ON moneyway_btts FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY "anon_all_dropping_1x2" ON dropping_1x2 FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY "anon_all_dropping_ou25" ON dropping_ou25 FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY "anon_all_dropping_btts" ON dropping_btts FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY "anon_all_moneyway_1x2_history" ON moneyway_1x2_history FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY "anon_all_moneyway_ou25_history" ON moneyway_ou25_history FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY "anon_all_moneyway_btts_history" ON moneyway_btts_history FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY "anon_all_dropping_1x2_history" ON dropping_1x2_history FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY "anon_all_dropping_ou25_history" ON dropping_ou25_history FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY "anon_all_dropping_btts_history" ON dropping_btts_history FOR ALL TO anon USING (true) WITH CHECK (true);

SELECT 'Tüm tablolar başarıyla oluşturuldu!' as result;
