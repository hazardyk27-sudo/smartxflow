---
name: Polymarket Gamma /events offset pagination cap
description: Gamma API's offset-based /events pagination has a hard ceiling (~2100) that silently truncates results as event counts grow; use /events/keyset instead, and don't trust its `limit` param.
---

Polymarket's Gamma API `/events` endpoint (offset+limit pagination) rejects any `offset` beyond roughly 2100 with a 400 "offset too large, use /events/keyset for deeper pagination" error. Code that paginates with a fixed page-count safety cap sized for a smaller total (e.g. ~2000 events) will silently miss real events that later fall past that cap as the total active-event count grows over time — no error, just missing rows.

**Fix:** use `/events/keyset` instead of `/events` for any full-listing pagination. It takes the same filter params (`tag_id`, `active`, `closed`, `order`, `ascending`, etc.) plus cursor params:
- `after_cursor` — opaque token from the previous response's `next_cursor` field
- `offset` is explicitly rejected (422) on this endpoint — don't send it
- `limit` is accepted but **silently capped at 100 per page regardless of the value requested** (verified: `limit=500` still returns exactly 100) — don't size a page budget assuming a larger effective page.

Response shape is `{"events": [...], "next_cursor": "..."}`. The only correct stop condition is `next_cursor` being empty/absent (or a page coming back empty, or the cursor repeating as an infinite-loop guard) — never a fixed page count, since that just recreates the same silent-truncation bug one level up. No known hard cap on total events reachable this way; a soccer-tag listing was observed at ~10,900 events with clean, non-duplicating pagination end-to-end.

**Why:** discovered when a same-day match (Sevilla vs Valencia, Sep 2026) was missing from the app because its position in the Gamma list (~2002) was just past an offset-pagination cap sized for a smaller total. The first fix attempt kept a fixed page-count budget under the wrong assumption that `limit` controlled page size, which just moved the same silent-truncation bug to a higher threshold.

**How to apply:** any Gamma `/events` listing logic in this project should paginate via keyset until `next_cursor` is exhausted, not via a page-count budget.
