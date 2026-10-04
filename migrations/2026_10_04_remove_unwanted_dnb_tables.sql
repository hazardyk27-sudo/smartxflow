-- SmartXFlow does not persist Draw No Bet or Double Chance market tables.
-- These two DNB tables were created during an abandoned preview experiment and
-- are intentionally removed. They are empty at migration time.

drop table if exists public.moneyway_draw_no_bet_history;
drop table if exists public.moneyway_draw_no_bet;
