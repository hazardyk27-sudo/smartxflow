-- Fixture Identity V2 Part 5 postflight
-- READ ONLY. This file intentionally contains SELECT statements only.
-- Goal: verify provider-gated current UID coverage and prove there is no
-- orphan/mismatched UID propagation into current/history/snapshot tables.

-- 1) Betwatch registry integrity.
select
  count(*) as registry_rows,
  count(distinct source_event_id) as provider_ids,
  count(distinct fixture_uid) as fixture_uids,
  min(seen_count) as min_seen_count,
  max(seen_count) as max_seen_count
from fixture_source_ids
where source = 'betwatch';

select count(*) as fixture_uids_with_multiple_betwatch_events
from (
  select fixture_uid
  from fixture_source_ids
  where source = 'betwatch'
  group by fixture_uid
  having count(distinct source_event_id) > 1
) x;

select count(*) as orphan_registry_rows
from fixture_source_ids s
left join fixtures f on f.fixture_uid = s.fixture_uid
where s.source = 'betwatch'
  and f.fixture_uid is null;

-- 2) Current-table coverage and exact physical integrity.
with current_rows as (
  select 'moneyway_1x2'::text as table_name, league, home, away, date::timestamptz as kickoff, fixture_uid from moneyway_1x2
  union all select 'dropping_1x2', league, home, away, date::timestamptz, fixture_uid from dropping_1x2
  union all select 'moneyway_ou25', league, home, away, date::timestamptz, fixture_uid from moneyway_ou25
  union all select 'dropping_ou25', league, home, away, date::timestamptz, fixture_uid from dropping_ou25
  union all select 'moneyway_btts', league, home, away, date::timestamptz, fixture_uid from moneyway_btts
  union all select 'dropping_btts', league, home, away, date::timestamptz, fixture_uid from dropping_btts
), resolved as (
  select
    c.*,
    f.fixture_uid as exact_uid,
    exists (
      select 1
      from fixture_source_ids s
      where s.source = 'betwatch'
        and s.fixture_uid = f.fixture_uid
    ) as has_betwatch_registry
  from current_rows c
  left join fixtures f
    on f.league = c.league
   and f.home_team = c.home
   and f.away_team = c.away
   and f.kickoff_utc = c.kickoff
)
select
  table_name,
  count(*) as total_rows,
  count(*) filter (where fixture_uid is not null) as uid_nonnull,
  count(*) filter (where exact_uid is not null) as exact_fixture_rows,
  count(*) filter (where exact_uid is not null and has_betwatch_registry) as provider_proven_rows,
  count(*) filter (where exact_uid is null) as unresolved_physical_rows,
  count(*) filter (where fixture_uid is not null and exact_uid is null) as orphan_or_unresolved_uid_rows,
  count(*) filter (where fixture_uid is not null and exact_uid is not null and fixture_uid <> exact_uid) as physical_mismatch_rows
from resolved
group by table_name
order by table_name;

-- 3) List current exact fixtures still lacking Betwatch provider proof.
with current_unique as (
  select distinct league, home, away, date::timestamptz as kickoff
  from moneyway_1x2
), resolved as (
  select c.*, f.match_id_hash, f.fixture_uid as exact_uid
  from current_unique c
  left join fixtures f
    on f.league = c.league
   and f.home_team = c.home
   and f.away_team = c.away
   and f.kickoff_utc = c.kickoff
)
select
  league,
  home,
  away,
  kickoff,
  match_id_hash,
  exact_uid
from resolved r
where exact_uid is not null
  and not exists (
    select 1
    from fixture_source_ids s
    where s.source = 'betwatch'
      and s.fixture_uid = r.exact_uid
  )
order by kickoff, league, home, away;

-- 4) History/snapshot leakage guard. These must remain NULL until an immutable
-- provider-verifiable identity is stored on the individual historical/snapshot row.
select 'moneyway_1x2_history' as table_name, count(*) filter (where fixture_uid is not null) as uid_nonnull from moneyway_1x2_history
union all select 'dropping_1x2_history', count(*) filter (where fixture_uid is not null) from dropping_1x2_history
union all select 'moneyway_ou25_history', count(*) filter (where fixture_uid is not null) from moneyway_ou25_history
union all select 'dropping_ou25_history', count(*) filter (where fixture_uid is not null) from dropping_ou25_history
union all select 'moneyway_btts_history', count(*) filter (where fixture_uid is not null) from moneyway_btts_history
union all select 'dropping_btts_history', count(*) filter (where fixture_uid is not null) from dropping_btts_history
union all select 'moneyway_snapshots', count(*) filter (where fixture_uid is not null) from moneyway_snapshots;

-- 5) Legacy uniqueness remains in force during Part 5.
select
  indexname,
  indexdef
from pg_indexes
where schemaname = 'public'
  and tablename = 'fixtures'
  and indexname in ('fixtures_match_id_hash_key', 'fixtures_fixture_uid_uidx')
order by indexname;
