# SmartXFlow T-72 real-source capture: fix and upstream availability ceiling

Scope: GitHub `hazardyk27-sudo/smartxflow` only, Betwatch production single
master on Hetzner and the existing authoritative Supabase source tables.
No Replit, personal PC, synthetic prices, historical snapshot rewrites,
or changes to any of the 10 frozen signal rules.

## Upstream evidence (live read-only Betwatch GET)

At **2026-10-21T13:43:21Z** the authorized Hetzner host fetched one live
`GET /api/v1/football/prematch`. HTTP 200; **839 fixtures**. The provider
already lists matches more than 96 hours before kickoff: this disproves the
assumption that the provider only exposes near-term fixtures.

Of **196** fixtures T+72–96h, **194** advertised Match Odds. All 194 had
three runners (582 total), but only **220** runners carried **both a valid
numeric odd and positive volume**; **362** runners had **both fields NULL**.
This was checked on raw provider payload, before writing Supabase. There were
**zero** provider-explicit zero-volume runners in this audit. Other cohorts:
T+60–72h: 117 fixtures, 108 Match Odds, 86 priced of 324 runners; T+96h+:
216 fixtures, 216 Match Odds, 209 priced of 648 runners.

Hence a T-72 signal for every provider-listed match is **not achievable from
the current Betwatch observations**. A fixture can be discovered and the
checkpoint queued before T-72 while its needed odds/amounts remain unavailable.
The system must not interpolate missing sides, import late quotes backwards
or treat the fixture list as priced market coverage.

Sanitized provider evidence is in
`docs/BASE_T72_PROVIDER_FIELD_AUDIT_20261021.txt`.

## Safe improvements

1. `core/moneyway_quote_fidelity.py` preserves an **explicit source 0**
   for a priced runner (volume=0, share=0), but never invents 0 when a volume
   key is absent/NULL. A complete market still requires the entire set of
   priced outcomes and positive aggregate volume. This is a future robustness
   fix, not a claim that existing NULL upstream prices are resolved.
2. Production Hetzner **single atomic-leased** prematch scraper cadence is
   set to 180s instead of 300s. This increases the number of actual source
   observations in the frozen T-72 [-30m,0m] window from about six to up to
   ten when scrapes succeed; stays above the Betwatch prematch 40s API limit
   and does not add a second scraper or replay historical data.
3. Every existing scrape reports **T72_96, T60_72, T40_60, T24_40, T0_24,
   T96_PLUS** source readiness: fixture count, actual fully-priced 1X2,
   partial 1X2, no priced sides and missing market. This differentiates
   upstream unavailable odds from parsing/ingestion failures, with no
   additional Betwatch API request.

## Release acceptance

- Targeted source tests PASS on `preview`.
- Existing `main` -> exact tested GitHub fast-forward; Hetzner deploy and
  the active provider-authoritative scraper service confirm exact SHA.
- Runtime `scheduled_scraper_legacy.PREMATCH_INTERVAL_SECONDS=180` and
  source `EARLY_SOURCE T72_96` log evidence, and new Snapshots are recorded.
- Source 1X2/OU25/BTTS latest timestamps remain fresh.
- Clearly report T-72 provider availability ceiling; NEVER claim all 10
  motors have complete historical source coverage merely because
  11 checkpoint job identities exist.
