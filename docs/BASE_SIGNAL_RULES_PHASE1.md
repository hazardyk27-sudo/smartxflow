# Base Signal Motors — Phase 1 pure rules (2026-10-18)

Source: user-provided `MAÇ. MOTOR V1.1(2).txt`. These rules are a **new isolated calculation package**, not a change to the existing `sinyal_engine.py` production signals. `preview` only, no migration or production release.

## Canonical input

- One provider-verified, nonempty `fixture_uid`, and an offset-aware kickoff UTC timestamp.
- Every Moneyway snapshot is timestamped UTC, includes decimal odds, money amount, share and market (`1X2`, `OU25`, `BTTS`).
- Use the latest fully populated market snapshot **observed at or before** the checkpoint, within the historical <=30-minute validity window. Completeness: `1/X/2`, `O/U`, `Y/N`; share totals within +/-0.5 percentage point of 100.
- Missing or partially populated markets fail closed (`INSUFFICIENT_DATA`); never treat missing sides as zero.
- Raw signals are retained when selected price is under 1.30 but marked `PRICE_FILTER_REJECT` for the selection layer. This package does **not** decide `BET/WATCH/PASS`.

## Base checkpoint override requested by user

For Concentration V1/V2, Heavy, Stable/Premium Over, Premium MIN1.70, BTTS YES and Surprise Team:
- T-8 is the first/preliminary scan.
- Once valid T-6 market data exists, T-6 is authoritative even if it does **not** qualify. Never fall back to T-8 merely because the T-6 engine rejected the selection.
- If T-6 market data is absent after the configured ingestion grace, use a valid T-8 snapshot with explicit `FALLBACK_T8` status. The calculation API has an illustrative/configurable 10-minute default; this **must be confirmed before production**.
- No new Base checkpoint at T-5/T-4/T-3.

### Money and odds rules

| Name | Selection | Absolute amount | Share | Odds |
|---|---|---:|---:|---:|
| 1X2 Concentration V1 | top-money HOME/AWAY | >=£1,000 | >=80% | 1.40–2.50 |
| 1X2 Concentration V2 | V1 selection + 3h history | same as V1 | no observation <70% in prior 3h | adverse rise <=3% in prior 3h |
| Heavy Concentration | top-money HOME/AWAY, **tag only** | >=£10,000 | >=80% | No additional odds band |
| Stable Over 2.5 | O | >=£1,500 | >=65% | 1.40–1.80 |
| Premium Over 2.5 | O, **tag** | >=£2,500 | >=75% | 1.40–1.80 |
| Premium Over MIN1.70 | O, **tag** | >=£2,500 | >=75% | 1.70–1.80 |
| BTTS YES | Y | >=£750 | >=60% | 1.60–1.90 |
| Surprise Team | HOME or AWAY | no amount floor | >=50% | 2.90–4.49 |

V2 calculation verifies full 1X2 snapshots at hourly anchors over the preceding three-hour window, checks **all** complete observations in that window for a share break, and rejects peak odds >1.03x the first anchor's odds. This is an explicit fail-closed operational interpretation to be compared against the intended research implementation before production promotion.

## Early-only exception

- `EARLY_MONEY_CORE`: T-72/T-60 >=£5,000, >=50% share; T-40/T-24 >=£10,000, >=50% share; top-money HOME/AWAY. Use the **first** qualifying Early checkpoint as the core signal.
- `EARLY_T24_COHORT` is a **label on the Early Core signal**, not a new stand-alone engine. There is no independent "Early -24" definition in the supplied file.
- Retention is tracked at T-6/T-5/T-4/T-3 for the **original selected side**. Any <55% share creates irreversible `RETENTION_BREAK`; missing checkpoints are `INSUFFICIENT_DATA`, never silently assumed good.
- `EARLY_MONEY_T12`: independent checkpoint T-12, top-money HOME/AWAY amount >=£1,000, share >=80%, never pooled into Early Core.

## Intentionally not in Phase 1

- No scheduled 24/7 worker, no Supabase writes or schema changes, no web UI, no old motor changes.
- No Surprise Hold, Surprise Growth, Draw Trap or 5x volume filters; these are separate research work.
- No production activation or promotion. Runtime adapter, idempotent audit tables, replay, service health, and live integration must be implemented/tested in later phases.

## Run isolated tests

`python -m pytest tests/test_base_signal_rules.py -q`