# Fixture Identity V2 — Safe Rollout Contract

Status: PART 4 / ADDITIVE REFERENCES + PROVIDER-GATED DUAL-WRITE PREVIEW

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

- 718 prematch rows in the first sampled response.
- Every sampled row exposed `match_id` as a non-empty numeric field.
- The full response contained zero duplicate `match_id` values.
- `league_id` also exists, but it is a league identifier and must never be used as
  fixture identity.
- No alternate event/fixture identifier was needed for the sampled payload.

A later Part 2 read-only sample contained 714 rows, 714 unique `match_id` values,
714 unique canonical hashes, zero duplicate provider IDs, and zero cases where one
canonical hash represented multiple different provider IDs inside that payload.

`match_id` is therefore the approved Betwatch provider identity.

## 3. Identity invariants

1. `fixture_uid` never depends on mutable team spelling, league spelling or kickoff.
2. `(source, source_event_id)` maps to at most one `fixture_uid`.
3. One `fixture_uid` may have mappings from several providers in the future, but
   must not silently accumulate different Betwatch event IDs for different
   physical events.
4. A missing provider ID fails closed; code must not invent an ID from another
   similarly-named payload field.
5. Different provider IDs must be allowed to represent later rematches even when
   the legacy `match_id_hash` is identical.
6. A kickoff change must not create a new identity when the provider event ID is
   unchanged.
7. Ambiguous fallback matching must never silently merge fixtures. Prefer an
   unresolved/provisional fixture over a false merge.
8. Existing production readers stay on the legacy path until shadow verification,
   reference migration and explicit release approval are complete.

## 4. Additive schema now present

The production database contains the additive Identity V2 shape while legacy
reader behavior remains unchanged.

    fixtures
      internal_id        existing PK during migration
      fixture_uid        UUID, UNIQUE, default gen_random_uuid()
      match_id_hash      existing compatibility key, unchanged and still UNIQUE
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
      seen_count         BIGINT
      PRIMARY KEY(source, source_event_id)

Part 4 also adds nullable `fixture_uid` references to the reviewed current,
history, snapshot, alarm/signal and related reference tables. These columns are
additive only: no reader is allowed to prefer them yet.

`match_id_hash UNIQUE` remains untouched. It is considered for removal only after
UID-first fixture writes, reader cutover and all reference/integrity checks pass.

## 5. Resolver order

When a provider row arrives in the future UID-authoritative writer:

1. exact `(source, source_event_id)` registry match -> existing `fixture_uid`;
2. if no provider mapping exists, evaluate reviewed physical candidates;
3. auto-link only when exactly one candidate meets strict confidence rules;
4. otherwise leave the identity unresolved/provisional and report ambiguity.

A fallback must never overwrite a provider-backed identity.

During Part 4 coexistence, the legacy fixture upsert still runs first. Shadow and
reference dual-write are deliberately non-authoritative and may only annotate a
row when provider identity and exact physical metadata agree.

## 6. Safe migration phases

### Phase A — additive fixture identity — COMPLETE

- added `fixtures.fixture_uid`;
- backfilled only fixture-row UIDs;
- added provider registry;
- no legacy constraint removed;
- no reader switched.

### Phase B — shadow provider identity — COMPLETE

- Betwatch `match_id` staged without affecting fetch success;
- provider mappings recorded in `fixture_source_ids`;
- conflicts fail closed and never merge/delete fixtures;
- three live samples proved stable provider-ID -> UID mapping.

### Phase C — additive references + dual-write — PART 4 CURRENT

- reviewed reference tables have nullable `fixture_uid` columns;
- current prematch dual-write requires provider registry proof plus exact
  league/home/away/kickoff agreement;
- a different Betwatch event ID cannot reuse a UID already owned by another
  Betwatch event during legacy-hash coexistence;
- current/history legacy hash fields and logical keys remain unchanged;
- snapshot/history rows without immutable proof stay NULL rather than being
  guessed from hash.

### Phase D — controlled reader/writer cutover — NOT STARTED

Only after explicit release approval:

- fixture creation/update becomes provider-identity-first;
- readers prefer `fixture_uid` with reviewed legacy fallback;
- snapshot/history/signal/alarm/archive consumers move to UID where proven;
- foreign keys are added where operationally safe.

### Phase E — legacy uniqueness retirement — NOT STARTED

Only after all consumers are UID-safe:

- remove `UNIQUE(match_id_hash)`;
- keep `match_id_hash` indexed as compatibility/fingerprint data;
- block new hash-only physical-fixture identity decisions.

## 7. Part 1 safety boundary

Part 1 was deliberately non-invasive:

- no Supabase migration;
- no production data mutation;
- no `match_id_hash` change;
- no scraper/runtime identity cutover;
- no Replit source edit;
- no `main` promotion or Hetzner deployment.

The executable addition was a side-effect-free provider identity helper plus
regression tests.

## 8. Part 2 read-only production preflight — 2026-10-05

Production was inspected with SELECT-only queries before the migration:

- 2,179 fixture rows; 2,179 distinct legacy hashes.
- No missing hash, kickoff, home, away or league values in current fixtures.
- `fixture_uid` and `fixture_source_ids` did not previously exist.
- `pgcrypto` and `uuid-ossp` were already installed; `gen_random_uuid()` was available.
- No existing foreign-key constraints referenced `fixtures`.
- Historical legacy-hash reuse already existed, proving history must not be
  assigned from hash alone.
- Existing snapshot reference debt remains separate from V2 and is not hidden by
  this migration.

## 9. Part 2 migration + postflight — 2026-10-05

Applied Supabase migration:

    fixture_identity_v2_additive_20261005
    migration version: 20261005200329

Postflight verification:

- fixtures: 2,179 rows at migration time.
- non-null `fixture_uid`: 2,179 / 2,179.
- distinct `fixture_uid`: 2,179.
- duplicate UID groups: 0.
- distinct legacy hashes: 2,179.
- `fixtures_match_id_hash_key` remains UNIQUE.
- `fixtures_fixture_uid_uidx` is UNIQUE.
- registry FK points to `fixtures(fixture_uid)` with UPDATE/DELETE RESTRICT.

No current market row, history row, snapshot row, Alarm, Sinyal, Learning Archive
record, team name, league name, kickoff, or legacy hash was rewritten by Part 2.

## 10. Part 3 shadow verification — 2026-10-06

Production shadow RPC:

    2026_10_06_fixture_identity_v2_shadow_rpc.sql

A three-sample live probe, with roughly 45 seconds between samples, produced:

- 710 Betwatch registry rows;
- 710 distinct provider IDs;
- 710 distinct fixture UIDs;
- every mapping observed exactly 3 times;
- 0 provider/event conflicts;
- 0 fixture UID with multiple Betwatch provider IDs;
- 0 orphan registry rows.

A runtime import-path discrepancy was also found: the deployed standalone scraper
could resolve `desktop/scraper_standalone/betwatch_client.py`. Shadow staging was
therefore added to that runtime copy as well instead of assuming the root client
was authoritative at runtime.

## 11. Part 4 reference migration + history audit — 2026-10-06

Applied additive reference-column migration:

    fixture_identity_v2_reference_columns_20261006
    migration version: 20261005224958

All new reference columns are nullable. No `NOT NULL`, default, reader cutover,
legacy-key removal, history rewrite or snapshot rewrite is part of the migration.

Production history proved why hash-only backfill is forbidden. Legacy hashes seen
at more than one kickoff were observed in:

- `moneyway_1x2_history`: 68 hashes;
- `dropping_1x2_history`: 68 hashes;
- `moneyway_ou25_history`: 59 hashes;
- `dropping_ou25_history`: 59 hashes;
- `moneyway_btts_history`: 33 hashes;
- `dropping_btts_history`: 33 hashes.

Exact `hash + league + home + away + kickoff` dry-run candidates existed in large
numbers, but historical rows were intentionally not backfilled because immutable
provider identity is not stored on each old row. Ambiguous/unproven rows remain
NULL rather than inheriting the current fixture UID from a reused hash.

`moneyway_snapshots` is also left fail-closed: its current shape does not carry
league/team/kickoff/provider-event evidence sufficient to prove a physical event.

## 12. Part 4 current backfill + integrity result — 2026-10-06

Current prematch rows were first dry-run against exact physical metadata. Every
current row resolved to exactly one fixture at audit time, but only rows with an
additional Betwatch registry proof were eligible for production backfill.

The production backfill required all of:

- exact league;
- exact home team;
- exact away team;
- exact kickoff instant;
- exactly one Betwatch registry row for the fixture UID;
- provider mapping observed at least three times in the Part 3 shadow sample.

Rows updated:

- `moneyway_1x2`: 703; 7 left NULL;
- `dropping_1x2`: 703; 7 left NULL;
- `moneyway_ou25`: 546; 5 left NULL;
- `dropping_ou25`: 546; 5 left NULL;
- `moneyway_btts`: 383; 2 left NULL;
- `dropping_btts`: 383; 2 left NULL.

Total populated current references: 3,264.

Post-backfill integrity:

- orphan populated current UID references: 0;
- populated current rows whose league/home/away/kickoff disagreed with their UID's
  fixture: 0;
- Betwatch registry: 710 rows / 710 provider IDs / 710 fixture UIDs;
- fixture UIDs with multiple Betwatch event IDs: 0;
- orphan registry rows: 0;
- all six history tables still have 0 populated `fixture_uid` rows;
- `moneyway_snapshots` still has 0 populated `fixture_uid` rows;
- `fixtures_match_id_hash_key` remains UNIQUE;
- `fixtures_fixture_uid_uidx` remains UNIQUE.

The unverified current rows remain NULL by design. Part 4 does not guess them.

## 13. Part 4 source behavior and CI

Preview source now contains a provider-gated current reference path:

- shadow staging retains the Betwatch event ID and the payload's physical
  `(league, home, away, kickoff)` context;
- before a shadow binding is submitted, a fixture UID already owned by another
  Betwatch event causes a fail-closed collision instead of a rematch merge;
- current dual-write resolves event ID -> registry UID and verifies the exact
  physical fixture before attaching `fixture_uid`;
- failure to prove identity leaves UID absent while legacy current/history writing
  continues;
- snapshot UID enrichment is disabled until provider-verifiable snapshot identity
  exists.

`Hash System Tests` passed after the rematch collision regression and provider-gate
module were added to the CI path and compile checks.

Production readers have NOT been switched to UID. `main`/Hetzner promotion has NOT
been performed. Those remain explicit later phases requiring approval.

## 14. Source artifacts

- `migrations/2026_10_05_fixture_identity_v2_additive.sql`
- `migrations/2026_10_06_fixture_identity_v2_shadow_rpc.sql`
- `migrations/2026_10_06_fixture_identity_v2_reference_columns.sql`
- `core/fixture_identity_v2.py`
- `core/fixture_identity_shadow.py`
- `core/fixture_uid_provider_gate.py`
- `core/fixture_uid_dual_write.py`
- `core/current_table_sync.py`
- `scripts/fixture_identity_v2_dry_run.sql`
- `scripts/run_fixture_identity_shadow_probe.py`
- `scripts/run_fixture_uid_dual_write_probe.py`
- `tests/test_fixture_identity_shadow.py`
- `tests/test_fixture_uid_dual_write.py`
- `tests/test_fixture_uid_snapshot_dual_write.py`
