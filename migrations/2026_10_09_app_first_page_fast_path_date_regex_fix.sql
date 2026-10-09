-- SmartXFlow /app first-page fast path date-regex correction.
--
-- The original RPC used an over-escaped regex inside dynamic SQL, so ISO
-- kickoff strings such as 2026-10-11T01:00:00+00:00 did not match. Keep the
-- original migration immutable and replace only the reader function here.

create or replace function public.sxf_matches_first_page_v1(
    p_market text,
    p_limit integer default 20,
    p_date_gte timestamptz default null
)
returns table(row_data jsonb, total_count bigint)
language plpgsql
stable
security invoker
set search_path = public
as $$
declare
    safe_limit integer := greatest(1, least(coalesce(p_limit, 20), 100));
    stmt text;
begin
    if p_market not in (
        'moneyway_1x2', 'moneyway_ou25', 'moneyway_btts',
        'dropping_1x2', 'dropping_ou25', 'dropping_btts'
    ) then
        raise exception 'unsupported market: %', p_market using errcode = '22023';
    end if;

    stmt := format($sql$
        select to_jsonb(t) as row_data,
               count(*) over() as total_count
          from public.%I as t
         where $1 is null
            or (
                case
                    when coalesce(t.date, '') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T'
                    then t.date::timestamptz
                    else null
                end
            ) >= $1
         order by public.sxf_parse_volume_v1(t.volume) desc nulls last,
                  t.date asc,
                  t.id asc
         limit $2
    $sql$, p_market);

    return query execute stmt using p_date_gte, safe_limit;
end;
$$;

revoke all on function public.sxf_matches_first_page_v1(text, integer, timestamptz) from public;
grant execute on function public.sxf_matches_first_page_v1(text, integer, timestamptz) to anon, authenticated, service_role;
