create or replace function public.sxf_match_history_bulk_v1(
  p_home text,
  p_away text,
  p_league text default ''
)
returns jsonb
language sql
stable
security invoker
set search_path = public
as $$
  select jsonb_build_object(
    'moneyway_1x2', coalesce((
      select jsonb_agg(to_jsonb(x) order by x.scraped_at)
      from (
        select * from public.moneyway_1x2_history
        where home = p_home and away = p_away
          and (coalesce(p_league, '') = '' or league = p_league)
        order by scraped_at asc
        limit 10000
      ) x
    ), '[]'::jsonb),
    'moneyway_ou25', coalesce((
      select jsonb_agg(to_jsonb(x) order by x.scraped_at)
      from (
        select * from public.moneyway_ou25_history
        where home = p_home and away = p_away
          and (coalesce(p_league, '') = '' or league = p_league)
        order by scraped_at asc
        limit 10000
      ) x
    ), '[]'::jsonb),
    'moneyway_btts', coalesce((
      select jsonb_agg(to_jsonb(x) order by x.scraped_at)
      from (
        select * from public.moneyway_btts_history
        where home = p_home and away = p_away
          and (coalesce(p_league, '') = '' or league = p_league)
        order by scraped_at asc
        limit 10000
      ) x
    ), '[]'::jsonb),
    'dropping_1x2', coalesce((
      select jsonb_agg(to_jsonb(x) order by x.scraped_at)
      from (
        select * from public.dropping_1x2_history
        where home = p_home and away = p_away
          and (coalesce(p_league, '') = '' or league = p_league)
        order by scraped_at asc
        limit 10000
      ) x
    ), '[]'::jsonb),
    'dropping_ou25', coalesce((
      select jsonb_agg(to_jsonb(x) order by x.scraped_at)
      from (
        select * from public.dropping_ou25_history
        where home = p_home and away = p_away
          and (coalesce(p_league, '') = '' or league = p_league)
        order by scraped_at asc
        limit 10000
      ) x
    ), '[]'::jsonb),
    'dropping_btts', coalesce((
      select jsonb_agg(to_jsonb(x) order by x.scraped_at)
      from (
        select * from public.dropping_btts_history
        where home = p_home and away = p_away
          and (coalesce(p_league, '') = '' or league = p_league)
        order by scraped_at asc
        limit 10000
      ) x
    ), '[]'::jsonb)
  );
$$;

grant execute on function public.sxf_match_history_bulk_v1(text, text, text)
to anon, authenticated, service_role;
