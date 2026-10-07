create or replace function public.polymarket_latest_trade_checkpoints(condition_ids text[])
returns table(condition_id text, traded_at timestamptz)
language sql
stable
security invoker
set search_path = public
as $$
  select t.condition_id, max(t.traded_at) as traded_at
  from public.polymarket_trades as t
  where t.condition_id = any(condition_ids)
  group by t.condition_id;
$$;

grant execute on function public.polymarket_latest_trade_checkpoints(text[])
to anon, authenticated, service_role;
