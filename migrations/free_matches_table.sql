-- SmartXFlow: free_matches tablosu
-- Admin panelden seçilen ücretsiz test maçlarını kalıcı olarak saklar
-- Supabase Dashboard > SQL Editor'da çalıştırın

CREATE TABLE IF NOT EXISTS public.free_matches (
    id              SERIAL PRIMARY KEY,
    match_id_hash   VARCHAR(20)  NOT NULL UNIQUE,
    home_team       VARCHAR(200),
    away_team       VARCHAR(200),
    league          VARCHAR(200),
    fixture_date    DATE,
    selected_at     TIMESTAMPTZ  DEFAULT NOW(),
    active          BOOLEAN      DEFAULT TRUE
);
