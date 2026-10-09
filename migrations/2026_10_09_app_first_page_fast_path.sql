-- SmartXFlow /app first-page fast path.
--
-- Purpose: return the globally highest-volume first page from a current prematch
-- market table without transferring the whole market snapshot to the web app.
-- The current tables are still authoritative; this function changes only the
-- read shape used by the first paint.

create or replace function public.sxf_parse_volume_v1(p_volume text)
returns numeric
language plpgsql
immutable
security invoker
set search_path = public
as $$
declare
    cleaned text;
    multiplier numeric := 1;
    normalized text := upper(trim(coalesce(p_volume, '')));
begin
    if normalized = '' then
        return null;
    end if;

    if normalized ~ 'K$' then
        multiplier := 1000;
    elsif normalized ~ 'M$' then
        multiplier := 1000000;
    elsif normalized ~ 'B$' then
        multiplier := 1000000000;
    end if;

    cleaned := regexp_replace(normalized, '[^0-9.]', '', 'g');
    if cleaned = '' then
        return null;
    end if;

    return cleaned::numeric * multiplier;
exception
    when invalid_text_representation then
        return null;
end;
$$;

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
                    when coalesce(t.date, '') ~ '^\\d{4}-\\d{2}-\\d{2}T'
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

revoke all on function public.sxf_parse_volume_v1(text) from public;
revoke all on function public.sxf_matches_first_page_v1(text, integer, timestamptz) from public;
grant execute on function public.sxf_parse_volume_v1(text) to anon, authenticated, service_role;
grant execute on function public.sxf_matches_first_page_v1(text, integer, timestamptz) to anon, authenticated, service_role;
