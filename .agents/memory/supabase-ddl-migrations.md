---
name: Supabase DDL migrations require manual execution
description: No exec_sql RPC exists in this project's Supabase instance; ALTER TABLE / CREATE TABLE changes cannot be run from app code.
---

New columns/tables cannot be added to Supabase programmatically from this codebase — PostgREST does not expose DDL, and there is no `exec_sql` RPC function defined in this Supabase project (confirmed by testing: `POST .../rest/v1/rpc/exec_sql` returns `PGRST202 - function not found`).

**Why:** All schema changes in this project follow a convention of writing a `.sql` file under `migrations/` and asking the user to run it manually in the Supabase SQL Editor. Code that depends on a not-yet-added column must fail open (e.g. treat HTTP 400 "column not found" as empty/no-op) so the app keeps working until the migration is applied.

**How to apply:** When a task requires a new column/table, write the migration SQL to `migrations/<date>_<description>.sql` (see existing files for the `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` pattern), tell the user it must be run manually, and make any code reading/writing that column tolerant of it not existing yet.
