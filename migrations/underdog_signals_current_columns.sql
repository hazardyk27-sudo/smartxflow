-- Underdog Engine: current_* ve last_updated_at kolonlarını ekle
-- Bu SQL'i Supabase SQL Editor'da çalıştırın.
-- Migration: Task #88 — Underdog Engine current values tracking

ALTER TABLE underdog_signals ADD COLUMN IF NOT EXISTS current_odds text;
ALTER TABLE underdog_signals ADD COLUMN IF NOT EXISTS current_pct text;
ALTER TABLE underdog_signals ADD COLUMN IF NOT EXISTS current_amt text;
ALTER TABLE underdog_signals ADD COLUMN IF NOT EXISTS current_volume text;
ALTER TABLE underdog_signals ADD COLUMN IF NOT EXISTS last_updated_at timestamptz;
