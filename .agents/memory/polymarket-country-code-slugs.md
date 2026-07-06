---
name: Polymarket country-code slug mapping
description: Which 3-letter country codes Polymarket event slugs actually use (vs. official ISO-3166-1 alpha-3), and where to source verified examples.
---

Polymarket's football event slugs (e.g. `fifwc-prt-esp-2026-07-06-...`,
`bkfibaqeu-ser-bos-2026-07-06`) embed 3-letter country codes that are
**mostly but not strictly** ISO-3166-1 alpha-3 — some competitions use
alternate/legacy variants for the same country (e.g. Switzerland
appears as both `che` and `swi`/`sui`; Netherlands as `nld`, `ned`, and
`net`; Uruguay as `uru` and `ury`; Croatia as `hrv` and `cro`).

**Why:** A hardcoded code->name map (`_FIFA_COUNTRY_CODES` in
`services/polymarket_client.py`) will silently show raw uppercased
codes for any variant it doesn't know, which reads as a bug to users
even though the underlying match data is fine.

**How to apply:** When extending/debugging this map, don't guess codes
from the ISO standard alone — pull real slug/title pairs from live
tracked-wallet activity (`/api/poly/tracked/<wallet>/profile`, fields
`activity[].slug` + `activity[].title`) across several wallets, since
different tournaments/competitions on Polymarket use different code
variants for the same country. Club-team codes are a separate, much
larger problem (no clean lookup exists) — keep those out of scope and
let them fall back to the raw code rather than guessing.
