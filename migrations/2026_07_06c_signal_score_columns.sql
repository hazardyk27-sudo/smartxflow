-- Diğer sinyal kartlarına maç skoru ekle (Confirmed Money, Confirmed Money V2, Early Money Lock, Fake Sharp)
-- Bu SQL'i Supabase SQL Editor'da çalıştırın.
-- underdog_signals tablosunda zaten var olan `score` kolonunun eşdeğeri.

ALTER TABLE confirmed_money_signals ADD COLUMN IF NOT EXISTS score text;
ALTER TABLE confirmed_money_v2_signals ADD COLUMN IF NOT EXISTS score text;
ALTER TABLE early_money_lock_signals ADD COLUMN IF NOT EXISTS score text;
ALTER TABLE fake_sharp_signals ADD COLUMN IF NOT EXISTS score text;
