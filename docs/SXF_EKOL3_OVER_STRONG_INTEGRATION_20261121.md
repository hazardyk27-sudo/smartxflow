# SXF EKOL 3 + OVER_STRONG — prospective motor integration

Target: SmartXFlow's existing Hetzner-owned BASE T-6 checkpoint worker and authenticated signal feed.

Status: DEVELOPMENT PREVIEW ONLY. No production activation, database migration, Replit source edit, Hetzner deployment, or backfill is authorized by this commit.

Frozen V3 core engine thresholds, scheduler identities, event ledger, corrections, and historical T-6/T-8 decisions are unchanged. New outputs are explicitly tagged EXPERIMENTAL and not calibrated winning probabilities.

## Calculation semantics

- EKOL_3 needs an authentic T-6 1X2_CONCENTRATION_V1 signal. T-8, T-7 and T-6 1/X/2 groups must be complete, with separate timestamps at/before each exact checkpoint and at most 10min old. First-hour and two-hour nonnegative per-selection new money share must strictly exceed T-8 baseline; normalized chosen-side de-vig implied probability at T-6 may not decrease versus T-8. Missing or contradictory data means no tag.
- OVER_STRONG needs an authentic T-6 STABLE_OVER_2_5 or PREMIUM_OVER_2_5 signal, with selected money at least GBP 2500, complete T-8 OU25 pair, same-source-time T-6 OU25 and BTTS full market pairs, T-6 BTTS YES odds strictly above 1.60, and T-6 Over share minus T-8 Over share strictly greater than -2pp. Any missing or stale evidence means no tag.
- Both tags are T-6-only; never appear as T-8 preliminary signals. They attach to existing selections and do not create duplicate independent betting picks.

## Controlled activation — separate user approval required

1. On preview, run unit/feed/runtime tests and inspect the exact SHA diff. Main and Hetzner remain untouched.
2. Obtain explicit approval for exact preview SHA after verified ancestry and CI checks.
3. Apply and verify the new versioned database registry migration (migrations/2026_11_21_experimental_signal_registry.sql) only with separately approved migration authorization and preflight; engine events fail closed until the registry is installed.
4. Set SXF_EXPERIMENTAL_ENGINES=1 and SXF_EXPERIMENTAL_ACTIVATED_AT_UTC to an approved future T-6 UTC timestamp using existing production config, never as a committed secret. Without both, experimental output is OFF.
5. After separately approved exact-SHA Hetzner deployment, verify T-6 job completion, event identity, source freshness, zero duplicate event keys, feed output, and missing-data behavior.
6. Never backfill or relabel historic checkpoint events. To roll back, disable feature flag first.

This does not write CAPITALE admin /admin/software records or other departments' scores.
