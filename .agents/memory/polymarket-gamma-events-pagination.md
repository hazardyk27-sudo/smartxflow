---
name: Polymarket Gamma /events pagination
description: Gamma API's offset-based /events pagination has a hard ceiling (~2100) that silently truncates growing lists; use /events/keyset by cursor exhaustion instead, and don't trust its `limit` param.
---

Polymarket's Gamma API `/events` endpoint (offset+limit pagination) rejects any `offset` beyond roughly 2100 with a 400 "offset too large, use /events/keyset for deeper pagination" error. Any fixed page-count budget sized for a smaller total silently drops rows once the true count grows past it — no error, just missing results.

**Fix:** use `/events/keyset` for any full-listing pagination instead of `/events`. Same filter params (`tag_id`, `active`, `closed`, `order`, `ascending`, etc.) plus:
- `after_cursor` — opaque token from the previous response's `next_cursor` field.
- `offset` is rejected (422) on this endpoint.
- `limit` is accepted but silently capped at 100 per page regardless of the value requested (verified: `limit=500` still returns exactly 100).

Response shape is `{"events": [...], "next_cursor": "..."}`. The only correct stop conditions are: an empty page, an absent `next_cursor`, or a cursor seen before (cycle guard against both immediate repeats and longer cycles) — never a fixed page-count cap, since that just recreates the same silent-truncation failure at a higher threshold.

**Why:** a fixed page-count budget is growth-dependent and eventually reproduces the exact failure mode `/events/keyset` was adopted to avoid.

**How to apply:** any Gamma `/events` listing logic in this project should paginate via keyset until cursor exhaustion, not via a page-count budget.
