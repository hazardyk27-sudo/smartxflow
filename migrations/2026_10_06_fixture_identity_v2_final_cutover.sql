begin;

-- Fixture Identity V2 final cutover.
-- Preconditions deliberately fail closed. This migration is only safe after the
-- prematch runtime has been switched to prematch_authoritative_runtime.py and
-- SUPABASE_SERVICE_ROLE_KEY is available to that runtime.
do $$
begin
    if not exists (
        select 1
        from pg_proc p
        join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'public'
          and p.proname = 'record_betwatch_fixture_batch_v2'
    ) then
        raise exception 'fixture_identity_v2_final_cutover: authoritative RPC missing';
    end if;

    if exists (
        select 1 from public.fixtures where fixture_uid is null
    ) then
        raise exception 'fixture_identity_v2_final_cutover: fixture_uid NULL rows exist';
    end if;

    if exists (
        select fixture_uid
        from public.fixtures
        group by fixture_uid
        having count(*) > 1
    ) then
        raise exception 'fixture_identity_v2_final_cutover: duplicate fixture_uid exists';
    end if;

    if exists (
        select league, home_team, away_team, kickoff_utc
        from public.fixtures
        group by league, home_team, away_team, kickoff_utc
        having count(*) > 1
    ) then
        raise exception 'fixture_identity_v2_final_cutover: exact physical duplicate exists';
    end if;

    if exists (
        select s.fixture_uid
        from public.fixture_source_ids s
        left join public.fixtures f on f.fixture_uid = s.fixture_uid
        where s.source = 'betwatch'
          and f.fixture_uid is null
    ) then
        raise exception 'fixture_identity_v2_final_cutover: orphan Betwatch registry row exists';
    end if;

    if exists (
        select fixture_uid
        from public.fixture_source_ids
        where source = 'betwatch'
        group by fixture_uid
        having count(distinct source_event_id) > 1
    ) then
        raise exception 'fixture_identity_v2_final_cutover: Betwatch UID multi-owner exists';
    end if;

    if not exists (
        select 1
        from pg_constraint
        where conrelid = 'public.fixtures'::regclass
          and conname = 'fixtures_match_id_hash_key'
          and contype = 'u'
    ) then
        raise exception 'fixture_identity_v2_final_cutover: temporary legacy hash safety constraint missing';
    end if;

    if not exists (
        select 1
        from pg_indexes
        where schemaname = 'public'
          and tablename = 'fixture_source_ids'
          and indexname = 'fixture_source_ids_betwatch_fixture_uid_uidx'
    ) then
        raise exception 'fixture_identity_v2_final_cutover: Betwatch UID ownership index missing';
    end if;
end;
$$;

-- After the provider-authoritative runtime is active, legacy matchup hash is a
-- compatibility fingerprint only and must no longer define physical uniqueness.
alter table public.fixtures
    drop constraint fixtures_match_id_hash_key;

create index if not exists fixtures_match_id_hash_idx
    on public.fixtures (match_id_hash);

commit;
