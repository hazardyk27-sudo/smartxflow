# SXF Early Money / Retention 55 research backfill — 14–20 October 2026

Status: **RESEARCH-ONLY / HISTORICAL RECONSTRUCTION**, append-only. Not a new production prediction; no motor parameters, live app, Supabase ACLs or existing daily checkpoint observations were changed.

## Authoritative frozen definitions

Sources: `preview:docs/SXF_SIGNAL_ENGINE_REGISTRY.md`, `preview:base_signal_engine/rules.py`, `preview:docs/BASE_SIGNAL_RULES_PHASE1.md`.
- Core: earliest qualifying HOME/AWAY money leader among **T-72, T-60, T-40, T-24**; at T-72/T-60 require >=£5,000 and share>=50%, at T-40/T-24 require >=£10,000 and share>=50%.
- T-12: independent signal, money-leading HOME/AWAY side, >=£1,000 and share>=80%; **never pool T-12 as Early Core**.
- Full-market validation: odds, amount and money share on HOME/DRAW/AWAY, 1X2 share total within +/-0.5 percentage points of 100, and latest snapshot within **30 minutes before its checkpoint**.
- Global odds floor: candidate side with odds <1.30 is `PRICE_FILTER_REJECT`; preserve source signal for audit but **exclude from eligible win rates**.
- Retention 55: on the ORIGINAL Core side, evaluate T-6,T-5,T-4,T-3 in order. Any share below 55% causes irreversible `RETENTION_BREAK`. If no break and any checkpoint is missing or incomplete: `INSUFFICIENT_DATA`. Only all-present/all-passing cases are `RETAINED`. This is a validity guard, **not** a second independent bet.

## 14–20 October source extraction

Daily immutable `YYYY-MM-DD_early_money_checkpoint_sources.json` files were created and individually checked with GitHub readback.

| Date | Source checkpoint snapshots found | First Core matches | T-12 candidates |
|---|---:|---:|---:|
| 14 Oct | 177 | 8 | 6 |
| 15 Oct | 315 | 7 | 26 |
| 16 Oct | 265 | 0 | 5 |
| 17 Oct | 777 | 11 | 25 |
| 18 Oct | 643 | 9 | 19 |
| 19 Oct | 179 | 3 | 6 |
| 20 Oct | 212 | 7 | 15 |
| **Total** | **2,568** | **45** | **102** |

Source snapshots are **not** separate betting signals; repeated checkpoint observations do not equal independent matches. Extraction used the indexed `public.moneyway_1x2_history` table and only samples observed no later than each T-72/T-60/T-40/T-24/T-12 cutoff. No postmatch labels were used to qualify signals.

From the 2,568 available source snapshots, 1,494 passed the complete-and-fresh <=30-minute filter when independently audited against fixture kickoff times. The remainder must not be assumed operationally valid. The single latest eligible-odds source record per checkpoint was evaluated for completeness; individual source-history resampling that would recover any earlier complete record hidden behind a later incomplete one is not yet exhaustively proved equivalent for every day. The 14 Oct direct-complete lookup matched exactly (86 fresh-complete snapshots). Thus these research counts are a **conservative backfill**, not a certified 100% reproduction of all original live signals.

Daily `YYYY-MM-DD_early_money_first_signals_v1.csv` records include frozen prematch features, first qualifying Core cohort, independent T-12 observations, and POST-only FT result/win labels. No original 9–13 Oct CSV was overwritten.

## Provisional outcome summary

| Cohort | Raw candidates | Price-eligible | Price-eligible settled | Wins | Losses | Hit rate |
|---|---:|---:|---:|---:|---:|---:|
| Early Money Core (first per fixture) | 45 | 40 | 40 | 29 | 11 | **72.5%** |
| Early Money T-12 (separate) | 102 | 85 | 85 | 53 | 32 | **62.4%** |

One T-12 observation from 17 October has no verified FT label in the source; it remains unlabelled. The above price-eligible cohort counts have FT for every included candidate. These observed percentages are in-sample descriptive research results, **not** a claim of forward expected success or profitability.

## Retention 55

All 45 first-Core fixtures were preserved as `2026-10-14_20_early_money_retention_core_manifest_v1.json`. 180 scheduled retention checkpoints were extracted using indexed 1X2 source history, with 178 valid complete/fresh and 2 insufficient.

`2026-10-14_20_early_money_retention55_results_v1.csv` stores all 45 per-fixture retention outcomes and each of the four checkpoint states.

| Retention status | All raw Core | Price-eligible Core | Wins among price-eligible |
|---|---:|---:|---:|
| RETAINED | 40 | 35 | 26/35 |
| RETENTION_BREAK | 3 | 3 | 2/3 |
| INSUFFICIENT_DATA | 2 | 2 | 1/2 |

**Caution:** In this small period two of three broken but price-eligible Early Core candidates still won. Do not infer a robust retention improvement or change the frozen 55% threshold on these tiny subgroups. Core/T-12 may overlap for a fixture and should never be treated as independent outcomes without deduplication.

## Raw archive is NOT yet complete

- 18 Oct `research_archive.archive_runs` = PARTIAL. Research archive O/U2.5 has **212** UIDs / **157,278** rows, while indexed primary source shows O/U history within the 8-day prematch window for **400/400** archived fixture hashes. Thus 188 archived fixture identities lack O/U2.5 raw archive coverage. The missing history should be recovered carefully; no raw archive mutation has been made.
- `research_archive.moneyway_ou25_history` has **no index/unique constraint** and is ~416 MB, so blind bulk insertion would risk duplicates and live-database load. No dangerous append was attempted.
- 20 Oct `research_archive.archive_runs` has no row; primary Moneyway history and 139 fixture rows survive, as do 135 joined FT results. Derived daily CSV does **not** substitute for raw history.
- The official Supabase `research_archive.queue_export('2026-10-20','fixtures')` submitted request ID 6, but `net.http_request_queue` still held it with no response/object; the synchronous `run_export` attempt failed with `HTTP request cancelled` after ~122 seconds. **Do not claim a cold backup was written or automatically retry unbounded exports.**
- Commander device `smartxflow` was offline; authorized Hetzner shell remediation wasn't available.

## 21 Oct open-day safeguard

At 03:40 local, PRE-only checkpoint snapshots were frozen in `2026-10-21_0340_prematch_checkpoint_staging.json` and eight pre-only qualifying engine rows from four fixtures were saved to `2026-10-21_0340_prematch_engine_candidates.csv`. One observation was stale; no FT result labels or future checkpoints were added. Finalize the day only after the date closes.

## Next safe work

1. Resolve Supabase archival export transport and idempotency/uniqueness plan without loading production during peak use.
2. Recover 18 Oct O/U2.5 missing raw history and complete 20 Oct raw day, preserving existing append-only records.
3. Audit exact historical snapshot completeness and 1X2 V2 frozen anchor equivalence before pooling 9–20 Oct performance results.
4. Settle 21 Oct only after all eligible matches finish and results are verified.
