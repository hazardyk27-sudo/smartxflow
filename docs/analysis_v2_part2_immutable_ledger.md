# Analysis V2 — Part 2 Immutable Signal Ledger

Date: 2026-10-02

## Objective

Remove the two largest backtest-integrity risks found in Analysis V1:

1. signals disappearing after they stop satisfying the live threshold;
2. settlement being vulnerable to fuzzy/team-name matching.

Analysis V2 treats a signal as an event ledger. Once a signal is triggered,
its trigger-time facts are permanent.

## Storage model

### 1. `analysis_v2_signal_events`

One row per trigger event. Immutable.

Required identity:

- `signal_uid`
- `engine_key`
- `engine_version`
- canonical 12-char `match_id_hash`
- `market_key`
- `selection_code`
- `triggered_at`

Frozen trigger-time facts can include:

- opening odds;
- 6h / 2h / 30m odds;
- trigger odds;
- trigger money percentage;
- trigger selection amount;
- trigger total market volume;
- 6h / 2h / 30m new-money deltas;
- price movement percentages;
- hours to kickoff;
- engine parameters;
- evidence/raw trigger JSON.

The database rejects UPDATE and DELETE.

### 2. `analysis_v2_signal_state_events`

Append-only lifecycle observations:

- `ACTIVE`
- `WEAKENED`
- `INVALIDATED`
- `SETTLED`

A signal that weakens is **not removed**. A new state event explains why.

This eliminates V1 survivorship bias caused by deleting signals after their
criteria stopped being true.

### 3. `analysis_v2_signal_settlement_events`

Append-only result history.

Settlement requires the exact canonical `match_id_hash`. A database trigger
rejects a settlement whose match hash differs from the immutable signal event.

There is intentionally no fuzzy team-name fallback.

Corrections are represented as a new settlement event, preserving the original
result event for auditability.

## Idempotency

The Python ledger creates deterministic IDs:

- `signal_uid`
- `state_uid`
- `settlement_uid`

Retries therefore use PostgREST conflict-ignore semantics instead of producing
duplicate trigger/state/result events.

The application writer exposes POST/append operations only. It has no PATCH or
DELETE API for V2 ledger data.

## Settlement support

`analysis_v2/settlement.py` settles:

- 1X2: 1 / X / 2
- Double Chance: 1X / X2 / 12
- Draw No Bet: 1 / 2, draw = PUSH
- O/U 2.5: O / U
- BTTS: Y / N

Flat-stake return is stored from the **trigger odds**, allowing historical ROI
to be computed from the price that actually existed when the signal fired.

## Canonical hash issue found during Part 2

A read-only production audit on 2026-10-02 compared the active fixture
`match_id_hash` to `core.hash_utils.make_match_id_hash`.

Observed:

- active matches checked: 945
- mismatched fixture hashes: 161

Root cause:

`betwatch_prematch.py` had its own weaker hash normalizer, while history and
other subsystems use `core/hash_utils.py`.

Examples included team suffixes, punctuation and accented/non-ASCII forms.

Part 2 removes the scraper-local implementation and delegates fixture identity
to the repository-wide canonical hash helper. Future Betwatch fixtures and
moneyway snapshots therefore use the same identity contract as history and
Analysis V2.

A read-only audit helper was added:

`scripts/audit_match_hash_contract.py`

It reports mismatches and canonical collisions without printing credentials.

## Deployment note

The code fix changes **future writes**. Existing bad fixture hashes must be
audited/repaired as a controlled migration before V2 settlement is enabled in
production. Do not silently rewrite production fixture identities during
Preview development.

## Invariants for all later V2 engines

Every V2 signal engine must:

1. know its `engine_key` and `engine_version`;
2. have a canonical `match_id_hash`;
3. freeze trigger odds/money/time facts at trigger;
4. append lifecycle state changes instead of deleting a signal;
5. settle only by exact hash;
6. keep the original trigger record forever.
