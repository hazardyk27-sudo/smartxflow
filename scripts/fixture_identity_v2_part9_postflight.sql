-- Fixture Identity V2 Part 9 production migration postflight.
-- READ ONLY: every statement in this file is SELECT/WITH only.
-- Run immediately after applying 2026_10_06_fixture_identity_v2_provider_writer.sql
-- and before enabling the authoritative writer flag in Preview runtime.

-- 1) Migration schema contract.
select
    bool_or(indexname = 'fixtures_match_id_hash_key') as legacy_hash_unique_present,
    bool_or(indexname = 'fixtures_fixture_uid_uidx') as fixture_uid_unique_present,
    bool_or(indexname = 'fixture_source_ids_betwatch_fixture_uid_uidx') as betwatch_uid_unique_present,
    bool_or(indexname = 'fixtures_match_id_hash_idx') as nonunique_hash_index_present
from pg_indexes
where schemaname = 'public';

select
    is_nullable,
    column_default
from information_schema.columns
where table_schema = 'public'
  and table_name = 'fixtures'
  and column_name = 'fixture_uid';

select exists (
    select 1
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public'
      and p.proname = 'record_betwatch_fixture_batch_v2'
) as provider_writer_rpc_present;

select
    has_function_privilege('service_role', 'public.record_betwatch_fixture_batch_v2(timestamptz,jsonb)', 'EXECUTE') as service_role_execute,
    has_function_privilege('anon', 'public.record_betwatch_fixture_batch_v2(timestamptz,jsonb)', 'EXECUTE') as anon_execute,
    has_function_privilege('authenticated', 'public.record_betwatch_fixture_batch_v2(timestamptz,jsonb)', 'EXECUTE') as authenticated_execute,
    exists (
        select 1
        from information_schema.routine_privileges
        where routine_schema = 'public'
          and routine_name = 'record_betwatch_fixture_batch_v2'
          and grantee = 'PUBLIC'
          and privilege_type = 'EXECUTE'
    ) as public_execute;

-- 2) Core fixture/registry integrity must be unchanged by DDL installation.
select
    count(*) as fixture_rows,
    count(*) filter (where fixture_uid is null) as fixture_uid_null_rows,
    count(distinct fixture_uid) as distinct_fixture_uids,
    count(distinct match_id_hash) as distinct_legacy_hashes
from public.fixtures;

select count(*) as duplicate_fixture_uid_groups
from (
    select fixture_uid
    from public.fixtures
    group by fixture_uid
    having count(*) > 1
) d;

select count(*) as exact_physical_duplicate_groups
from (
    select league, home_team, away_team, kickoff_utc
    from public.fixtures
    group by league, home_team, away_team, kickoff_utc
    having count(*) > 1
) d;

select
    count(*) as registry_rows,
    count(distinct source_event_id) as provider_ids,
    count(distinct fixture_uid) as registry_fixture_uids
from public.fixture_source_ids
where source = 'betwatch';

select count(*) as betwatch_uid_multi_event_groups
from (
    select fixture_uid
    from public.fixture_source_ids
    where source = 'betwatch'
    group by fixture_uid
    having count(distinct source_event_id) > 1
) d;

select count(*) as orphan_betwatch_registry_rows
from public.fixture_source_ids s
left join public.fixtures f on f.fixture_uid = s.fixture_uid
where s.source = 'betwatch'
  and f.fixture_uid is null;

-- 3) Existing populated current UID references must still be exact.
with current_rows as (
    select 'moneyway_1x2'::text as table_name, fixture_uid, league, home, away, date from public.moneyway_1x2
    union all
    select 'dropping_1x2', fixture_uid, league, home, away, date from public.dropping_1x2
    union all
    select 'moneyway_ou25', fixture_uid, league, home, away, date from public.moneyway_ou25
    union all
    select 'dropping_ou25', fixture_uid, league, home, away, date from public.dropping_ou25
    union all
    select 'moneyway_btts', fixture_uid, league, home, away, date from public.moneyway_btts
    union all
    select 'dropping_btts', fixture_uid, league, home, away, date from public.dropping_btts
)
select
    table_name,
    count(*) as total_rows,
    count(*) filter (where fixture_uid is not null) as uid_rows,
    count(*) filter (
        where fixture_uid is not null and f.fixture_uid is null
    ) as orphan_uid_rows,
    count(*) filter (
        where fixture_uid is not null
          and f.fixture_uid is not null
          and (
              f.league is distinct from current_rows.league
              or f.home_team is distinct from current_rows.home
              or f.away_team is distinct from current_rows.away
              or f.kickoff_utc is distinct from current_rows.date::timestamptz
          )
    ) as physical_mismatch_rows
from current_rows
left join public.fixtures f using (fixture_uid)
group by table_name
order by table_name;

-- 4) Observe reference rollout state. Immediately after migration these should
-- remain unchanged; after Preview activation, only newly provider-proven rows may grow.
select 'moneyway_1x2_history'::text as table_name, count(*) filter (where fixture_uid is not null) as uid_rows from public.moneyway_1x2_history
union all select 'dropping_1x2_history', count(*) filter (where fixture_uid is not null) from public.dropping_1x2_history
union all select 'moneyway_ou25_history', count(*) filter (where fixture_uid is not null) from public.moneyway_ou25_history
union all select 'dropping_ou25_history', count(*) filter (where fixture_uid is not null) from public.dropping_ou25_history
union all select 'moneyway_btts_history', count(*) filter (where fixture_uid is not null) from public.moneyway_btts_history
union all select 'dropping_btts_history', count(*) filter (where fixture_uid is not null) from public.dropping_btts_history
union all select 'moneyway_snapshots', count(*) filter (where fixture_uid is not null) from public.moneyway_snapshots;

-- 5) Hash duplication becomes legal only as a compatibility fingerprint.
select count(*) as duplicate_legacy_hash_groups
from (
    select match_id_hash
    from public.fixtures
    group by match_id_hash
    having count(*) > 1
) d;
