-- Fixture Identity V2, additive phase only.
-- This migration must not change or remove the legacy match_id_hash contract.
-- Runtime readers/writers continue using the existing hash path until a later,
-- explicitly approved cutover.

create extension if not exists pgcrypto;

alter table public.fixtures
    add column if not exists fixture_uid uuid;

alter table public.fixtures
    alter column fixture_uid set default gen_random_uuid();

-- Backfill only the new identity column. Existing fixture fields are untouched.
update public.fixtures
set fixture_uid = gen_random_uuid()
where fixture_uid is null;

-- Keep fixture_uid nullable during shadow rollout. The default above gives all
-- new rows a UUID even while legacy writers remain unchanged.
create unique index if not exists fixtures_fixture_uid_uidx
    on public.fixtures (fixture_uid);

create table if not exists public.fixture_source_ids (
    source text not null,
    source_event_id text not null,
    fixture_uid uuid not null,
    first_seen_at timestamptz not null default now(),
    last_seen_at timestamptz not null default now(),
    primary key (source, source_event_id),
    constraint fixture_source_ids_fixture_uid_fkey
        foreign key (fixture_uid)
        references public.fixtures (fixture_uid)
        on update restrict
        on delete restrict,
    constraint fixture_source_ids_source_canonical_chk
        check (source <> '' and source = lower(btrim(source))),
    constraint fixture_source_ids_event_id_nonempty_chk
        check (btrim(source_event_id) <> ''),
    constraint fixture_source_ids_seen_order_chk
        check (last_seen_at >= first_seen_at)
);

create index if not exists fixture_source_ids_fixture_uid_idx
    on public.fixture_source_ids (fixture_uid);

alter table public.fixture_source_ids enable row level security;
revoke all privileges on table public.fixture_source_ids from anon, authenticated, service_role;
grant select, insert, update on table public.fixture_source_ids to service_role;

-- Intentionally NOT done in this phase:
-- * no match_id_hash constraint/index changes
-- * no NOT NULL enforcement on fixture_uid
-- * no snapshot/history/signal/alarm foreign-key migration
-- * no runtime resolver switch
-- * no deletion or rewrite of legacy data
