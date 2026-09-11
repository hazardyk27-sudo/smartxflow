---
name: Polymarket Gamma /events offset pagination cap
description: Gamma API's offset-based /events pagination has a hard ceiling (~2100) that silently truncates results as event counts grow; use /events/keyset instead.
---

Polymarket's Gamma API `/events` endpoint (offset+limit pagination) rejects any `offset` beyond roughly 2100 with a 400 "offset too large, use /events/keyset for deeper pagination" error. Code that paginates with a fixed `max_pages` safety cap sized for a smaller total (e.g. 2000 events) will silently miss real events that later fall past that cap as the total active-event count grows over time — no error, just missing rows.

**Fix:** use `/events/keyset` instead of `/events` for any full-listing pagination. It takes the same filter params (`tag_id`, `active`, `closed`, `order`, `ascending`, etc.) plus cursor params:
- `limit` (max 500 per page, vs 100 for the offset endpoint)
- `after_cursor` — opaque token from the previous response's `next_cursor` field
- `offset` is explicitly rejected (422) on this endpoint — don't send it

Response shape is `{"events": [...], "next_cursor": "..."}`; stop when `next_cursor` is empty/absent or a page comes back empty. No known hard cap on total events reachable this way.

**Why:** discovered when a same-day match (Sevilla vs Valencia, Sep 2026) was missing from `/poly` — its Gamma list position (~2002) was just past the app's `max_pages=20` (~2000-event) offset-pagination cap, so the scraper's `get_all_active_matches()` never saw it and it was never upserted to Supabase.

**How to apply:** `services/polymarket_client.py`'s `_fetch_events_paginated()` helper now wraps this keyset pagination and is used by both `_fetch_soccer_events()` (active) and `_fetch_closed_soccer_events()` (closed). Any new Gamma `/events` listing logic should reuse it rather than reintroducing offset pagination with a hardcoded page cap.
