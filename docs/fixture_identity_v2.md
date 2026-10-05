# Fixture Identity V2 — Safe Rollout Contract

Status: PART 1 / DESIGN + PROVIDER AUDIT

This document defines the migration contract for giving every physical football
fixture one durable SmartXFlow identity without breaking the currently-running
`match_id_hash` system.

## 1. Why V2 exists

`match_id_hash` is intentionally a legacy matchup fingerprint:

    md5(normalize(league) | normalize(home) | normalize(away))[:12]

Kickoff is not part of that hash. This keeps the hash stable when kickoff changes,
but it also means two later rematches in the same league can legitimately produce
the same hash. Therefore `match_id_hash` cannot be the permanent identity of one
physical event.

Identity V2 separates:

- `match_id_hash`: compatibility/fingerprint key.
- `fixture_uid`: SmartXFlow's immutable identity for one physical fixture.
- provider identity: `(source, source_event_id)` mapping a provider event to one
  `fixture_uid`.

## 2. Betwatch provider audit — 2026-10-05

A read-only live audit of `/football/prematch` found:

- 718 prematch rows in the sampled response.
- Every sampled row exposed `match_id` as a non-empty numeric field.
- The full response contained zero duplicate `match_id` values.
- `league_id` also exists, but it is a league identifier and must never be used as
  fixture identity.
- No alternate event/fixture identifier was needed for the sampled payload.

`match_id` is therefore the approved Betwatch provider-identity candidate for
shadow work.

Important: uniqueness inside one response is proven; long-term cross-scrape
stability must still be measured in shadow mode before it is allowed to control
production fixture writes.

## 3. Identity invariants

1. `fixture_uid` never depends on mutable team spelling, league spelling or kickoff.
2. `(source, source_event_id)` maps to at most one `fixture_uid`.
3. One `fixture_uid` may have several provider mappings in the future.
4. A missing provider ID fails closed; code must not invent an ID from another
   similarly-named payload field.
5. Different provider IDs must be allowed even when `match_id_hash` is identical.
   This is how rematches are separated.
6. A kickoff change must not create a new identity when the provider event ID is
   unchanged.
7. Ambiguous fallback matching must never silently merge fixtures. Prefer a new
   provisional fixture over a false merge.
8. Existing production readers/writers stay on the legacy path until shadow
   verification passes and explicit release approval is given.

## 4. Target schema (future additive migration)

No schema change is applied in Part 1.

Planned additive shape:

    fixtures
      internal_id        existing PK during migration
      fixture_uid        UUID NULL initially, later NOT NULL + UNIQUE
      match_id_hash      existing compatibility key
      home_team
      away_team
      league
      kickoff_utc
      ...

    fixture_source_ids
      fixture_uid        UUID FK -> fixtures.fixture_uid
      source             TEXT NOT NULL
      source_event_id    TEXT NOT NULL
      first_seen_at      TIMESTAMPTZ NOT NULL
      last_seen_at       TIMESTAMPTZ NOT NULL
      UNIQUE(source, source_event_id)

`match_id_hash UNIQUE` remains untouched during additive and shadow phases. It is
considered for removal only after UID dual-write, backfill, reference migration,
and integrity checks have passed.

## 5. Resolver order (future)

When a provider row arrives:

1. exact `(source, source_event_id)` registry match -> existing `fixture_uid`;
2. if no provider ID, evaluate a reviewed fallback candidate using normalized
   league/home/away plus kickoff proximity;
3. auto-link only when exactly one candidate meets strict confidence rules;
4. otherwise create/retain a provisional new fixture and report ambiguity.

The fallback must not be allowed to overwrite a provider-backed identity.

## 6. Safe migration phases

### Phase A — additive only

- add nullable `fixture_uid`;
- add provider registry;
- no current constraint removed;
- no reader switched;
- no production upsert path changed.

### Phase B — backfill + audit

- give existing fixture rows UUIDs;
- backfill references only where deterministic;
- produce ambiguity/orphan reports;
- never guess on conflicting historical rows.

### Phase C — dual write + shadow resolver

- current production behavior remains hash-backed;
- new provider identity is written in parallel;
- compare legacy outcome vs UID resolver every scrape;
- required counters: missing provider IDs, duplicate provider IDs, one provider ID
  -> multiple UIDs, one UID -> conflicting providers, ambiguous fallbacks.

### Phase D — controlled cutover

Only after shadow verification and explicit release approval:

- readers prefer `fixture_uid` with legacy fallback;
- writers resolve provider identity before fixture update/insert;
- snapshot/history/signal/alarm/archive references move to UID;
- DB foreign keys are added where safe.

### Phase E — legacy uniqueness retirement

Only after all consumers are UID-safe:

- remove `UNIQUE(match_id_hash)`;
- keep `match_id_hash` indexed as a compatibility/fingerprint field;
- block new hash-only fixture upserts.

## 7. Part 1 safety boundary

Part 1 is deliberately non-invasive:

- no Supabase migration;
- no production data mutation;
- no `match_id_hash` change;
- no scraper/runtime import of Identity V2;
- no Replit source edit;
- no `main` promotion or Hetzner deployment.

The only executable addition is a side-effect-free provider identity helper plus
regression tests. Production behavior is therefore unchanged.
