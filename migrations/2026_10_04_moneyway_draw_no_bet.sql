-- Provider-backed Betwatch Moneyway Draw no Bet storage.
-- Double Chance is intentionally not created: SmartXFlow never synthesizes DC from 1X2.

create table if not exists public.moneyway_draw_no_bet (
    id bigserial primary key,
    league text,
    date text,
    home text,
    away text,
    odds1 text,
    odds2 text,
    trend1 text,
    trend2 text,
    pct1 text,
    amt1 text,
    pct2 text,
    amt2 text,
    volume text,
    constraint moneyway_draw_no_bet_unique unique (league, home, away, date)
);

create table if not exists public.moneyway_draw_no_bet_history (
    id bigserial primary key,
    league text,
    date text,
    home text,
    away text,
    odds1 text,
    odds2 text,
    trend1 text,
    trend2 text,
    pct1 text,
    amt1 text,
    pct2 text,
    amt2 text,
    volume text,
    scraped_at text,
    match_id_hash varchar(64)
);

create index if not exists idx_moneyway_dnb_history_match_scraped
    on public.moneyway_draw_no_bet_history (match_id_hash, scraped_at);

alter table public.moneyway_draw_no_bet enable row level security;
alter table public.moneyway_draw_no_bet_history enable row level security;

drop policy if exists anon_all on public.moneyway_draw_no_bet;
create policy anon_all on public.moneyway_draw_no_bet
    for all to anon using (true) with check (true);

drop policy if exists anon_all on public.moneyway_draw_no_bet_history;
create policy anon_all on public.moneyway_draw_no_bet_history
    for all to anon using (true) with check (true);

grant select, insert, update, delete on table public.moneyway_draw_no_bet to anon, authenticated, service_role;
grant select, insert, update, delete on table public.moneyway_draw_no_bet_history to anon, authenticated, service_role;
grant usage, select on sequence public.moneyway_draw_no_bet_id_seq to anon, authenticated, service_role;
grant usage, select on sequence public.moneyway_draw_no_bet_history_id_seq to anon, authenticated, service_role;
