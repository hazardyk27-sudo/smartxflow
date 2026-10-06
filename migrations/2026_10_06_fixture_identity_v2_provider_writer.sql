-- Fixture Identity V2 Part 7: provider-authoritative fixture writer.
-- IMPORTANT: source-only preparation in Preview. Do not apply to production
-- until the explicit release gate is approved.
--
-- Goals:
-- * Betwatch source_event_id becomes the authoritative physical-fixture key.
-- * fixture_uid stays immutable for an already-mapped provider event.
-- * same legacy match_id_hash may represent multiple physical rematches.
-- * exact-physical/provider ambiguity fails the entire RPC transaction closed.
-- * no reader cutover and no history/snapshot migration happens here.

-- Preconditions: every fixture already has a UID and one Betwatch event must not
-- own the same fixture UID as another Betwatch event.
do $$
begin
    if exists (
        select 1
        from public.fixtures
        where fixture_uid is null
    ) then
        raise exception 'fixture_identity_v2_provider_writer: fixture_uid NULL rows exist';
    end if;

    if exists (
        select fixture_uid
        from public.fixture_source_ids
        where source = 'betwatch'
        group by fixture_uid
        having count(distinct source_event_id) > 1
    ) then
        raise exception 'fixture_identity_v2_provider_writer: Betwatch fixture_uid ownership conflict exists';
    end if;
end;
$$;

-- DB-level invariant: one Betwatch event per fixture UID.
create unique index if not exists fixture_source_ids_betwatch_fixture_uid_uidx
    on public.fixture_source_ids (fixture_uid)
    where source = 'betwatch';

-- fixture_uid is the durable fixture identity from this point forward.
alter table public.fixtures
    alter column fixture_uid set not null;

-- Retire legacy hash uniqueness while keeping lookup performance. This is the
-- schema change that allows a future rematch to retain the same legacy matchup
-- fingerprint without overwriting the earlier physical fixture.
alter table public.fixtures
    drop constraint if exists fixtures_match_id_hash_key;

create index if not exists fixtures_match_id_hash_idx
    on public.fixtures (match_id_hash);

create or replace function public.record_betwatch_fixture_batch_v2(
    p_observed_at timestamptz,
    p_rows jsonb
)
returns table(
    received_count bigint,
    mapped_updated_count bigint,
    linked_existing_count bigint,
    inserted_new_count bigint
)
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_observed_at timestamptz := coalesce(p_observed_at, now());
    v_row record;
    v_uid uuid;
    v_existing_hash text;
    v_exact_count bigint;
    v_exact_uid uuid;
    v_owner_event text;
    v_mapped_updated bigint := 0;
    v_linked_existing bigint := 0;
    v_inserted_new bigint := 0;
begin
    if p_rows is null or jsonb_typeof(p_rows) <> 'array' then
        raise exception 'rows must be a JSON array';
    end if;

    -- Validate required identity before any write occurs.
    if exists (
        select 1
        from jsonb_to_recordset(p_rows) as x(
            source_event_id text,
            match_id_hash text,
            home_team text,
            away_team text,
            league text,
            kickoff_utc timestamptz
        )
        where btrim(coalesce(x.source_event_id, '')) = ''
           or btrim(coalesce(x.match_id_hash, '')) = ''
           or btrim(coalesce(x.home_team, '')) = ''
           or btrim(coalesce(x.away_team, '')) = ''
           or btrim(coalesce(x.league, '')) = ''
           or x.kickoff_utc is null
    ) then
        raise exception 'provider fixture row has incomplete identity';
    end if;

    -- One provider event cannot describe more than one physical fixture in the
    -- same payload.
    if exists (
        select source_event_id
        from jsonb_to_recordset(p_rows) as x(
            source_event_id text,
            match_id_hash text,
            home_team text,
            away_team text,
            league text,
            kickoff_utc timestamptz
        )
        group by source_event_id
        having count(distinct row(
            btrim(league),
            btrim(home_team),
            btrim(away_team),
            kickoff_utc
        )) > 1
    ) then
        raise exception 'provider event collision inside fixture batch';
    end if;

    -- One exact physical fixture cannot arrive under multiple Betwatch IDs.
    if exists (
        select 1
        from jsonb_to_recordset(p_rows) as x(
            source_event_id text,
            match_id_hash text,
            home_team text,
            away_team text,
            league text,
            kickoff_utc timestamptz
        )
        group by btrim(league), btrim(home_team), btrim(away_team), kickoff_utc
        having count(distinct btrim(source_event_id)) > 1
    ) then
        raise exception 'exact physical fixture has multiple provider event ids';
    end if;

    for v_row in
        select distinct on (btrim(source_event_id))
            btrim(source_event_id) as source_event_id,
            btrim(match_id_hash) as match_id_hash,
            left(btrim(home_team), 100) as home_team,
            left(btrim(away_team), 100) as away_team,
            left(btrim(league), 150) as league,
            kickoff_utc
        from jsonb_to_recordset(p_rows) as x(
            source_event_id text,
            match_id_hash text,
            home_team text,
            away_team text,
            league text,
            kickoff_utc timestamptz
        )
        order by btrim(source_event_id)
    loop
        -- Serialize the provider identity and exact physical identity to prevent
        -- concurrent double-creation.
        perform pg_advisory_xact_lock(hashtext('betwatch:' || v_row.source_event_id));
        perform pg_advisory_xact_lock(hashtext(
            'fixture:' || v_row.league || '|' || v_row.home_team || '|' ||
            v_row.away_team || '|' || v_row.kickoff_utc::text
        ));

        v_uid := null;
        select s.fixture_uid
          into v_uid
        from public.fixture_source_ids s
        where s.source = 'betwatch'
          and s.source_event_id = v_row.source_event_id
        for update;

        if v_uid is not null then
            v_existing_hash := null;
            select f.match_id_hash
              into v_existing_hash
            from public.fixtures f
            where f.fixture_uid = v_uid
            for update;

            if v_existing_hash is null then
                raise exception 'orphan Betwatch registry mapping for event %', v_row.source_event_id;
            end if;

            -- During the transition legacy references still depend on hash. A
            -- provider event may move kickoff while retaining UID, but a hash
            -- identity drift must wait for the later reader cutover.
            if v_existing_hash <> v_row.match_id_hash then
                raise exception 'mapped legacy hash drift for event %', v_row.source_event_id;
            end if;

            if exists (
                select 1
                from public.fixtures f
                where f.fixture_uid <> v_uid
                  and f.league = v_row.league
                  and f.home_team = v_row.home_team
                  and f.away_team = v_row.away_team
                  and f.kickoff_utc = v_row.kickoff_utc
            ) then
                raise exception 'mapped physical collision for event %', v_row.source_event_id;
            end if;

            update public.fixtures
               set home_team = v_row.home_team,
                   away_team = v_row.away_team,
                   league = v_row.league,
                   kickoff_utc = v_row.kickoff_utc,
                   fixture_date = v_row.kickoff_utc::date
             where fixture_uid = v_uid;

            update public.fixture_source_ids
               set last_seen_at = greatest(last_seen_at, v_observed_at),
                   seen_count = seen_count + 1
             where source = 'betwatch'
               and source_event_id = v_row.source_event_id
               and fixture_uid = v_uid;

            v_mapped_updated := v_mapped_updated + 1;
            continue;
        end if;

        select count(*), min(f.fixture_uid::text)::uuid
          into v_exact_count, v_exact_uid
        from public.fixtures f
        where f.league = v_row.league
          and f.home_team = v_row.home_team
          and f.away_team = v_row.away_team
          and f.kickoff_utc = v_row.kickoff_utc;

        if v_exact_count > 1 then
            raise exception 'exact physical fixture is ambiguous for event %', v_row.source_event_id;
        end if;

        if v_exact_count = 1 then
            v_owner_event := null;
            select s.source_event_id
              into v_owner_event
            from public.fixture_source_ids s
            where s.source = 'betwatch'
              and s.fixture_uid = v_exact_uid
            limit 1;

            if v_owner_event is not null and v_owner_event <> v_row.source_event_id then
                raise exception 'exact fixture already owned by Betwatch event %', v_owner_event;
            end if;

            insert into public.fixture_source_ids (
                source,
                source_event_id,
                fixture_uid,
                first_seen_at,
                last_seen_at,
                seen_count
            ) values (
                'betwatch',
                v_row.source_event_id,
                v_exact_uid,
                v_observed_at,
                v_observed_at,
                1
            );

            v_linked_existing := v_linked_existing + 1;
            continue;
        end if;

        -- No exact physical candidate: create a new immutable UID. Existing rows
        -- with the same legacy hash are intentionally ignored; they may be an
        -- earlier physical rematch and must never be overwritten or merged.
        v_uid := gen_random_uuid();

        insert into public.fixtures (
            match_id_hash,
            home_team,
            away_team,
            league,
            kickoff_utc,
            fixture_date,
            fixture_uid
        ) values (
            v_row.match_id_hash,
            v_row.home_team,
            v_row.away_team,
            v_row.league,
            v_row.kickoff_utc,
            v_row.kickoff_utc::date,
            v_uid
        );

        insert into public.fixture_source_ids (
            source,
            source_event_id,
            fixture_uid,
            first_seen_at,
            last_seen_at,
            seen_count
        ) values (
            'betwatch',
            v_row.source_event_id,
            v_uid,
            v_observed_at,
            v_observed_at,
            1
        );

        v_inserted_new := v_inserted_new + 1;
    end loop;

    return query
    select
        jsonb_array_length(p_rows)::bigint,
        v_mapped_updated,
        v_linked_existing,
        v_inserted_new;
end;
$$;

revoke all on function public.record_betwatch_fixture_batch_v2(timestamptz, jsonb)
    from public, anon, authenticated;
grant execute on function public.record_betwatch_fixture_batch_v2(timestamptz, jsonb)
    to service_role;

-- Intentionally NOT done in Part 7:
-- * no reader cutover
-- * no current/history/snapshot key rewrite
-- * no production migration application without explicit approval
-- * no legacy hash deletion from rows
