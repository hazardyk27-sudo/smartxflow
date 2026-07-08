---
name: Polymarket CLOB market resolution lookup
description: How to get wallet-independent win/loss ground truth for a resolved market, and the perf pitfall when doing it per-wallet.
---

Gamma API's `/markets` endpoint does NOT support filtering by `conditionId` (it silently ignores the param and returns an unrelated default listing) — do not use it for looking up a specific market's resolution.

The public CLOB API (`https://clob.polymarket.com/markets/{condition_id}`, no auth) is the correct source: it returns `{closed: bool, tokens: [{token_id, outcome, winner}, ...]}`. `token_id` matches the `asset` field already used elsewhere for Polymarket wallet data. If `closed` is false, the market simply hasn't resolved yet — don't cache that as a permanent "unknown".

**Why:** a wallet's own activity/redeem data is sometimes ambiguous (batched "Redeem All" transactions carry an aggregate conditionId with no per-asset breakdown, or a position may not be redeemed yet), so wallet-local signals alone leave many trades stuck as "unknown" result. The CLOB market resolution is wallet-independent ground truth and resolves nearly all of those.

**How to apply:** when computing won/lost for a specific outcome token, try wallet-local signals first (already-known won/lost asset ids), then fall back to CLOB market resolution keyed by conditionId + asset before giving up and reporting "unknown". Cache resolved (closed=true) results forever in-process — a market's outcome never changes.

**Perf pitfall:** calling this API serially per trade row for a large wallet (hundreds of distinct markets) can take 30s+ even though each individual call is fast (~0.3-1.5s) — the CLOB API doesn't parallelize well from a single caller either, so batch all the *unique* conditionIds needing a lookup up front and fetch them concurrently (e.g. `ThreadPoolExecutor`, ~40 workers) before doing the per-row pass, rather than calling inline per row.
