# SmartXFlow Moneyway source integrity — 2026-10-21 (Step 3)

## Live Supabase evidence

Time: approximately 2026-10-21T01:28Z, read-only production SQL.

- `moneyway_snapshots` was ingesting fresh records: 2,674 new rows from
  387 physical fixture UIDs in the last 15 minutes, latest source timestamp
  approximately 2026-10-21T01:20:15Z. The `scrape_complete` producer uses
  legacy label `source='replit'`; that label alone does NOT establish which
  server physically owns the production master lease.
- Of groups keyed by `fixture_uid,market,scraped_at_utc` in a 60-minute
  window:
  - 1X2: 851/1,524 groups structurally complete; 673 missing selections;
  - OU25: 355/712 complete; 357 missing;
  - BTTS: 274/522 complete; 248 missing.
- All records in the *latest* provider batch had numeric odd/volume/share
  fields, and all partial groups summed to 100% share over the *available*
  selections. This is not proof of completeness. Single-sided 100% money
  groups are incomplete and cannot support a valid signal.
- Joining partial groups against current Moneyway tables found zero cases
  where **every missing selection already had a stored current price**.
  This is consistent with unavailable source prices, but current tables
  are mutable so this alone cannot prove the upstream payload at scrape time.
- Source-quality-driven `WAITING_DATA` jobs mostly had
  `last_error_code='SOURCE_INCOMPLETE'` including
  `EARLY_CORE`, `EARLY_RETENTION`, `EARLY_T12`, and `BASE`.
  No missing checkpoint snapshot can be reconstructed by extrapolating
  a later market quote.

## Verified source-code defect

Both copies of `betwatch_client.map_market` previously decided the 1X2
selection based partly on runner array position and, with three runners,
forcibly overwrote the second mapped code with X when index 1 was not
draw. A legitimate provider array `[home,away,draw]` could become
`[1,X,X]`, dropping the away selection and associating the wrong quote with
X after dict overwrite in `betwatch_prematch.py`.

Source fix on GitHub `preview`:
- Require unique explicit side label or verified team identity.
- Pass fixture home/away identities from both prematch scraper code paths.
- Recognize any permutation of three correctly named runners.
- Reject duplicate or ambiguous runner names; never invent quotes.
- Preserve the frozen Base signal threshold code and historical snapshots.

## Monitoring / no-fabrication guard

`core/moneyway_ingest_quality.py` reports per-batch grouped counts for all
three supported markets: `complete`, `missing_sides`,
`duplicate_sides`, `invalid_fields`, `bad_share_sum`.
`betwatch_prematch.py` logs these aggregates and exposes them in
`writer.last_scrape_stats['snapshot_quality']`.

The derived quality metrics are telemetry, not a source watermark or a
guarantee that the Betwatch upstream offers both sides at every checkpoint.
No historical SQL backfill or synthetic market data is authorized.
Remaining `WAITING_DATA` due genuine unavailable prices may persist
even after the parser bug is fixed; handling stale incomplete jobs and
retry policies is a separate lifecycle step.

## Release check

Tests must verify permutation symmetry, reject ambiguity, preserve OU25/BTTS,
report missing sides despite sum(share)==100, and respect existing scraper
identity integration. After deploy, compare new per-batch quality logs and
Supabase complete-group percentages with the pre-release baseline.

## Focused pre-release test result

GitHub Actions isolated source suite on `preview`:
`pytest_exit_code=0`, **25 passed** at commit
`28131ce108ec8e28f906c611ae93cf33e5baf164`.
Both source client implementations, the prematch writer integration, six
runner-order permutations, missing-price refusal, and completeness telemetry
were included.

Release does not retroactively alter historical source observations.
After Hetzner deploy, compare the next successful moneyway snapshot batch
rather than inferring success from service state alone.

## Live correction: verified Betwatch 'The Draw' label

After the first strict mapping release, the 2026-10-21T01:47:06Z scrape
produced 466 OU25/BTTS snapshot rows and zero 1X2 rows. This was a
regression, not evidence of no Match Odds market. A **read-only** single
`GET /football/prematch` from authorized Hetzner returned 728 fixtures,
717 with Match Odds and **three runners each**. The actual draw runner was
consistently sampled as `The Draw` (examples:
`Abha, The Draw, Al-Kholood Club` and `Sweden, The Draw, Bosnia`),
which the new strict mapping did not recognize.

The compatibility hotfix recognizes the provider's explicit label
`the draw` (casefolded) without positional guessing. All six permutations
of actual three-runner source labels were added as regression tests.

GitHub Actions source test suite after the correction: **26 passed**,
`pytest_exit_code=0`, commit
`ddb7937d066aabe182a792b6b98875ca278f58c9`.
A production release is successful only when fresh source
`moneyway_snapshots` again contains 1X2 rows and the mapper no longer
silently discards Match Odds.
