---
name: SmartXFlow Supabase read path
description: Which configured connection contains SmartXFlow fixture and current-market data.
---

The Supabase MCP currently exposes BOKGAME, which does not contain SmartXFlow's `fixtures` or `moneyway_1x2` tables. The user explicitly directed that SmartXFlow match data must not be queried through that MCP project. Use the application's existing Supabase client for authorized read-only requests; suppress client initialization output because it can log credential fragments.

**Why:** BOKGAME is a different project; the app's configured client reaches the actual SmartXFlow match tables.

**How to apply:** For SmartXFlow match investigations, use only the app connection with GET/SELECT operations, never emit credential values, and verify target tables before querying.