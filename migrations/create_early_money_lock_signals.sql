-- Early Money Lock Signals tablosu
-- sinyal_engine.py tarafından kullanılır.
-- Supabase SQL Editor'da çalıştırın.

CREATE TABLE IF NOT EXISTS early_money_lock_signals (
    id bigserial PRIMARY KEY,
    match_key text NOT NULL,
    home_team text,
    away_team text,
    league text,
    match_date text,
    kickoff_utc text,
    selection_code text NOT NULL,
    selection_label text,
    pct_now text,
    volume_now text,
    consecutive_snapshots integer DEFAULT 5,
    created_at timestamptz DEFAULT now(),
    last_updated_at timestamptz,
    result text,
    UNIQUE (match_key, selection_code)
);
