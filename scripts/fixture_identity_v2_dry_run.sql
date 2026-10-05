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
with repeated as (
    select
        match_id_hash,
        count(distinct date::date) as distinct_days
    from public.moneyway_1x2_history
    where match_id_hash is not null
      and match_id_hash <> ''
      and date is not null
    group by match_id_hash
    having count(distinct date::date) > 1
)
select
    count(*) as hashes_seen_on_multiple_days,
    coalesce(max(distinct_days), 0) as max_distinct_days,
    count(*) filter (where distinct_days >= 3) as hashes_on_3plus_days
from repeated;

-- 3) Existing snapshot reference debt. Identity V2 must not pretend these are
-- fixed; historical remapping is a later explicit step.
select
    count(*) as total_snapshots,
    count(*) filter (where f.match_id_hash is null) as orphan_snapshots,
    count(distinct s.match_id_hash) as distinct_snapshot_hashes,
    count(distinct s.match_id_hash) filter (where f.match_id_hash is null) as orphan_distinct_hashes
from public.moneyway_snapshots s
left join public.fixtures f on f.match_id_hash = s.match_id_hash;

-- 4) Post-migration verification. Run only after the additive migration exists.
-- Expected: fixture_uid nulls=0, duplicate non-null UIDs=0, registry conflicts=0.
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
