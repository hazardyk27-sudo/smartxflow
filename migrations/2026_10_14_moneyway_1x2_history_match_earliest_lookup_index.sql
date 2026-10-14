-- Accelerate legacy earliest-valid 1X2 history lookups used by current UI/read paths:
--   home = ? AND away = ? AND date = ?
--   odds1/oddsx/odds2 != ''
--   ORDER BY scraped_at ASC LIMIT 1
--
-- Keep the index partial so empty/incomplete market rows do not inflate it.

CREATE INDEX IF NOT EXISTS moneyway_1x2_history_match_earliest_valid_idx
ON public.moneyway_1x2_history (home, away, date, scraped_at ASC)
WHERE odds1 <> '' AND oddsx <> '' AND odds2 <> '';
