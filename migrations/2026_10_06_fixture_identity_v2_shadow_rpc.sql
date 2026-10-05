-- Fixture Identity V2 Part 3: shadow-only provider registry writer.
-- This migration is additive. It must never change fixture selection, merge
-- production fixtures, alter match_id_hash, or switch any reader/writer path.

alter table public.fixture_source_ids
    add column if not exists seen_count bigint not null default 1;

alter table public.fixture_source_ids
    drop constraint if exists fixture_source_ids_seen_count_chk;

alter table public.fixture_source_ids
    add constraint fixture_source_ids_seen_count_chk
        check (seen_count >= 1);

create or replace function public.record_fixture_identity_shadow_batch(
    p_source text,
    p_observed_at timestamptz,
    p_bindings jsonb
)
returns table(
    inserted_count bigint,
    matched_count bigint,
    conflict_count bigint,
    received_count bigint
)
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_source text := lower(btrim(coalesce(p_source, '')));
    v_observed_at timestamptz := coalesce(p_observed_at, now());
begin
    if v_source = '' then
        raise exception 'source is required';
    end if;
    if p_bindings is null or jsonb_typeof(p_bindings) <> 'array' then
        raise exception 'bindings must be a JSON array';
    end if;

    return query
    with raw as (
        select
            btrim(x.source_event_id) as source_event_id,
            x.fixture_uid
        from jsonb_to_recordset(p_bindings)
            as x(source_event_id text, fixture_uid uuid)
        where btrim(coalesce(x.source_event_id, '')) <> ''
          and x.fixture_uid is not null
    ),
    ambiguous as (
        select source_event_id
        from raw
        group by source_event_id
        having count(distinct fixture_uid) > 1
    ),
    incoming as (
        select r.source_event_id, min(r.fixture_uid::text)::uuid as fixture_uid
        from raw r
        left join ambiguous a using (source_event_id)
        where a.source_event_id is null
        group by r.source_event_id
    ),
    classified as (
        select
            i.source_event_id,
            i.fixture_uid,
            e.fixture_uid as existing_fixture_uid,
            case
                when e.source_event_id is null then 'insert'
                when e.fixture_uid = i.fixture_uid then 'match'
                else 'conflict'
            end as class
        from incoming i
        left join public.fixture_source_ids e
          on e.source = v_source
         and e.source_event_id = i.source_event_id
    ),
    write_rows as (
        insert into public.fixture_source_ids (
            source,
            source_event_id,
            fixture_uid,
            first_seen_at,
            last_seen_at,
            seen_count
        )
        select
            v_source,
            c.source_event_id,
            c.fixture_uid,
            v_observed_at,
            v_observed_at,
            1
        from classified c
        where c.class in ('insert', 'match')
        on conflict (source, source_event_id) do update
            set last_seen_at = greatest(
                    public.fixture_source_ids.last_seen_at,
                    excluded.last_seen_at
                ),
                seen_count = public.fixture_source_ids.seen_count + 1
            where public.fixture_source_ids.fixture_uid = excluded.fixture_uid
        returning source_event_id
    )
    select
        count(*) filter (where c.class = 'insert')::bigint as inserted_count,
        count(*) filter (where c.class = 'match')::bigint as matched_count,
        (
            count(*) filter (where c.class = 'conflict')
            + (select count(*) from ambiguous)
        )::bigint as conflict_count,
        (
            select count(distinct source_event_id)
            from raw
        )::bigint as received_count
    from classified c;
end;
$$;

revoke all on function public.record_fixture_identity_shadow_batch(text, timestamptz, jsonb)
    from public, anon, authenticated;
grant execute on function public.record_fixture_identity_shadow_batch(text, timestamptz, jsonb)
    to service_role;

-- Intentionally NOT done in Part 3:
-- * no match_id_hash uniqueness/index changes
-- * no fixture merge/update through provider identity
-- * no fixture_uid reader cutover
-- * no snapshot/history/signal/alarm/archive reference migration
-- * no destructive cleanup
