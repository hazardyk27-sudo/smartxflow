-- Read-only Fixture Identity V2 preflight/postflight checks.
-- Safe to run against production: SELECT statements only.

-- 1) Current fixture completeness and legacy uniqueness.
select
    count(*) as fixture_count,
    count(distinct match_id_hash) as distinct_hashes,
    count(*) filter (where match_id_hash is null or match_id_hash = '') as missing_hashes,
    count(*) filter (where kickoff_utc is null) as missing_kickoff,
    count(*) filter (where home_team is null or home_team = '') as missing_home,
    count(*) filter (where away_team is null or away_team = '') as missing_away,
    count(*) filter (where league is null or league = '') as missing_league
from public.fixtures;

-- 2) Historical evidence that one legacy matchup hash can span multiple
-- physical fixture days. These rows must NOT be blindly assigned to one UID.
-- Run table-by-table on large production histories to avoid a single expensive
-- cross-history aggregation.
with repeated as (
    select
        match_id_hash,
        count(distinct date::timestamptz) as distinct_kickoffs
    from public.moneyway_1x2_history
    where match_id_hash is not null
      and match_id_hash <> ''
      and date is not null
    group by match_id_hash
    having count(distinct date::timestamptz) > 1
)
select
    'moneyway_1x2_history' as table_name,
    count(*) as hashes_seen_on_multiple_kickoffs,
    coalesce(max(distinct_kickoffs), 0) as max_distinct_kickoffs,
    count(*) filter (where distinct_kickoffs >= 3) as hashes_on_3plus_kickoffs
from repeated;

with repeated as (
    select match_id_hash, count(distinct date::timestamptz) as distinct_kickoffs
    from public.moneyway_ou25_history
    where match_id_hash is not null and match_id_hash <> '' and date is not null
    group by match_id_hash
    having count(distinct date::timestamptz) > 1
)
select 'moneyway_ou25_history' as table_name,
       count(*) as hashes_seen_on_multiple_kickoffs,
       coalesce(max(distinct_kickoffs), 0) as max_distinct_kickoffs,
       count(*) filter (where distinct_kickoffs >= 3) as hashes_on_3plus_kickoffs
from repeated;

with repeated as (
    select match_id_hash, count(distinct date::timestamptz) as distinct_kickoffs
    from public.moneyway_btts_history
    where match_id_hash is not null and match_id_hash <> '' and date is not null
    group by match_id_hash
    having count(distinct date::timestamptz) > 1
)
select 'moneyway_btts_history' as table_name,
       count(*) as hashes_seen_on_multiple_kickoffs,
       coalesce(max(distinct_kickoffs), 0) as max_distinct_kickoffs,
       count(*) filter (where distinct_kickoffs >= 3) as hashes_on_3plus_kickoffs
from repeated;

-- Dropping history mirrors the same physical-fixture risk and is audited
-- independently rather than inferred from moneyway history.
with repeated as (
    select match_id_hash, count(distinct date::timestamptz) as distinct_kickoffs
    from public.dropping_1x2_history
    where match_id_hash is not null and match_id_hash <> '' and date is not null
    group by match_id_hash
    having count(distinct date::timestamptz) > 1
)
select 'dropping_1x2_history' as table_name,
       count(*) as hashes_seen_on_multiple_kickoffs,
       coalesce(max(distinct_kickoffs), 0) as max_distinct_kickoffs,
       count(*) filter (where distinct_kickoffs >= 3) as hashes_on_3plus_kickoffs
from repeated;

with repeated as (
    select match_id_hash, count(distinct date::timestamptz) as distinct_kickoffs
    from public.dropping_ou25_history
    where match_id_hash is not null and match_id_hash <> '' and date is not null
    group by match_id_hash
    having count(distinct date::timestamptz) > 1
)
select 'dropping_ou25_history' as table_name,
       count(*) as hashes_seen_on_multiple_kickoffs,
       coalesce(max(distinct_kickoffs), 0) as max_distinct_kickoffs,
       count(*) filter (where distinct_kickoffs >= 3) as hashes_on_3plus_kickoffs
from repeated;

with repeated as (
    select match_id_hash, count(distinct date::timestamptz) as distinct_kickoffs
    from public.dropping_btts_history
    where match_id_hash is not null and match_id_hash <> '' and date is not null
    group by match_id_hash
    having count(distinct date::timestamptz) > 1
)
select 'dropping_btts_history' as table_name,
       count(*) as hashes_seen_on_multiple_kickoffs,
       coalesce(max(distinct_kickoffs), 0) as max_distinct_kickoffs,
       count(*) filter (where distinct_kickoffs >= 3) as hashes_on_3plus_kickoffs
from repeated;

-- 3) Existing snapshot reference debt. Identity V2 must not pretend these are
-- fixed; hash-only snapshot rows cannot prove a physical provider event.
select
    count(*) as total_snapshots,
    count(*) filter (where f.match_id_hash is null) as orphan_snapshots,
    count(distinct s.match_id_hash) as distinct_snapshot_hashes,
    count(distinct s.match_id_hash) filter (where f.match_id_hash is null) as orphan_distinct_hashes,
    count(*) filter (where s.fixture_uid is not null) as uid_populated_snapshots
from public.moneyway_snapshots s
left join public.fixtures f on f.match_id_hash = s.match_id_hash;

-- 4) Fixture UID and provider-registry invariants.
select
    count(*) as fixture_count,
    count(*) filter (where fixture_uid is null) as fixture_uid_nulls,
    count(distinct fixture_uid) as distinct_fixture_uids
from public.fixtures;

select fixture_uid, count(*) as rows
from public.fixtures
where fixture_uid is not null
group by fixture_uid
having count(*) > 1;

select source, source_event_id, count(distinct fixture_uid) as uid_count
from public.fixture_source_ids
group by source, source_event_id
having count(distinct fixture_uid) > 1;

-- One Betwatch physical event may keep its UID across kickoff changes, but one
-- UID must not silently accumulate different Betwatch event IDs during the
-- legacy UNIQUE(match_id_hash) coexistence period.
select fixture_uid, count(*) as betwatch_event_count
from public.fixture_source_ids
where source = 'betwatch'
group by fixture_uid
having count(*) > 1;

select count(*) as orphan_registry_rows
from public.fixture_source_ids s
left join public.fixtures f on f.fixture_uid = s.fixture_uid
where f.fixture_uid is null;

-- 5) Part 4 current-table deterministic coverage.
-- Safe current candidates require exact physical metadata AND exactly one
-- observed Betwatch registry mapping with at least three shadow observations.
with betwatch_registry as (
    select
        fixture_uid,
        count(*) as event_count,
        min(seen_count) as min_seen_count
    from public.fixture_source_ids
    where source = 'betwatch'
    group by fixture_uid
), current_rows as (
    select 'moneyway_1x2'::text as table_name, league, home, away, date from public.moneyway_1x2
    union all select 'moneyway_ou25', league, home, away, date from public.moneyway_ou25
    union all select 'moneyway_btts', league, home, away, date from public.moneyway_btts
    union all select 'dropping_1x2', league, home, away, date from public.dropping_1x2
    union all select 'dropping_ou25', league, home, away, date from public.dropping_ou25
    union all select 'dropping_btts', league, home, away, date from public.dropping_btts
), candidates as (
    select
        c.table_name,
        f.fixture_uid,
        r.event_count,
        r.min_seen_count
    from current_rows c
    left join public.fixtures f
      on f.league = c.league
     and f.home_team = c.home
     and f.away_team = c.away
     and f.kickoff_utc = c.date::timestamptz
    left join betwatch_registry r on r.fixture_uid = f.fixture_uid
)
select
    table_name,
    count(*) as total_rows,
    count(fixture_uid) as exact_fixture_rows,
    count(*) filter (where event_count = 1 and min_seen_count >= 3) as provider_verified_candidates,
    count(*) filter (where fixture_uid is null) as unresolved_physical_rows,
    count(*) filter (where fixture_uid is not null and event_count is null) as missing_registry_rows
from candidates
group by table_name
order by table_name;

-- 6) Part 4 current-table post-backfill integrity.
-- Expected for populated UIDs: orphan_uid=0 and wrong_physical_uid=0.
with audit as (
    select 'moneyway_1x2'::text as table_name, t.fixture_uid,
           (f.fixture_uid is null) as orphan_uid,
           (f.fixture_uid is not null and (
              t.league <> f.league or t.home <> f.home_team or t.away <> f.away_team
              or t.date::timestamptz <> f.kickoff_utc
           )) as wrong_physical_uid
    from public.moneyway_1x2 t left join public.fixtures f on f.fixture_uid=t.fixture_uid
    union all
    select 'moneyway_ou25', t.fixture_uid, (f.fixture_uid is null),
           (f.fixture_uid is not null and (t.league<>f.league or t.home<>f.home_team or t.away<>f.away_team or t.date::timestamptz<>f.kickoff_utc))
    from public.moneyway_ou25 t left join public.fixtures f on f.fixture_uid=t.fixture_uid
    union all
    select 'moneyway_btts', t.fixture_uid, (f.fixture_uid is null),
           (f.fixture_uid is not null and (t.league<>f.league or t.home<>f.home_team or t.away<>f.away_team or t.date::timestamptz<>f.kickoff_utc))
    from public.moneyway_btts t left join public.fixtures f on f.fixture_uid=t.fixture_uid
    union all
    select 'dropping_1x2', t.fixture_uid, (f.fixture_uid is null),
           (f.fixture_uid is not null and (t.league<>f.league or t.home<>f.home_team or t.away<>f.away_team or t.date::timestamptz<>f.kickoff_utc))
    from public.dropping_1x2 t left join public.fixtures f on f.fixture_uid=t.fixture_uid
    union all
    select 'dropping_ou25', t.fixture_uid, (f.fixture_uid is null),
           (f.fixture_uid is not null and (t.league<>f.league or t.home<>f.home_team or t.away<>f.away_team or t.date::timestamptz<>f.kickoff_utc))
    from public.dropping_ou25 t left join public.fixtures f on f.fixture_uid=t.fixture_uid
    union all
    select 'dropping_btts', t.fixture_uid, (f.fixture_uid is null),
           (f.fixture_uid is not null and (t.league<>f.league or t.home<>f.home_team or t.away<>f.away_team or t.date::timestamptz<>f.kickoff_utc))
    from public.dropping_btts t left join public.fixtures f on f.fixture_uid=t.fixture_uid
)
select
    table_name,
    count(*) as total_rows,
    count(*) filter (where fixture_uid is not null) as uid_nonnull,
    count(*) filter (where fixture_uid is null) as uid_null,
    count(*) filter (where fixture_uid is not null and orphan_uid) as orphan_uid,
    count(*) filter (where fixture_uid is not null and wrong_physical_uid) as wrong_physical_uid
from audit
group by table_name
order by table_name;

-- 7) History/snapshot remain fail-closed until immutable provider identity can be
-- proven for the individual historical row. Any non-zero result here requires a
-- deliberate, separately-reviewed backfill rather than hash-only inference.
select 'moneyway_1x2_history'::text as table_name, count(*) filter(where fixture_uid is not null) as uid_nonnull from public.moneyway_1x2_history
union all select 'moneyway_ou25_history', count(*) filter(where fixture_uid is not null) from public.moneyway_ou25_history
union all select 'moneyway_btts_history', count(*) filter(where fixture_uid is not null) from public.moneyway_btts_history
union all select 'dropping_1x2_history', count(*) filter(where fixture_uid is not null) from public.dropping_1x2_history
union all select 'dropping_ou25_history', count(*) filter(where fixture_uid is not null) from public.dropping_ou25_history
union all select 'dropping_btts_history', count(*) filter(where fixture_uid is not null) from public.dropping_btts_history
union all select 'moneyway_snapshots', count(*) filter(where fixture_uid is not null) from public.moneyway_snapshots;
