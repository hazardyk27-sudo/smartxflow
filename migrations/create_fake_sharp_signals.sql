-- Fake Sharp Signals tablosu
-- sinyal_engine.py tarafından kullanılır.
-- Supabase SQL Editor'da çalıştırın.

CREATE TABLE IF NOT EXISTS fake_sharp_signals (
    id bigserial PRIMARY KEY,
    match_key text NOT NULL,
    home_team text,
    away_team text,
    league text,
    match_date text,
    selection_code text NOT NULL,
    selection_label text,
    odds_16h text,
    odds_now text,
    current_odds text,
    pct_now text,
    current_pct text,
    volume_now text,
    current_volume text,
    odds_rise_pct real,
    created_at timestamptz DEFAULT now(),
    last_updated_at timestamptz,
    result text
);

CREATE UNIQUE INDEX IF NOT EXISTS fake_sharp_signals_match_key_sel_code_idx
    ON fake_sharp_signals (match_key, selection_code);

-- Mevcut tabloya result kolonu ekle (zaten varsa atlar):
ALTER TABLE fake_sharp_signals ADD COLUMN IF NOT EXISTS result text;
