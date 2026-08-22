---
name: Supabase email/password auth migration
description: Architecture decisions for replacing key-based license login with Supabase Auth (email+password) + membership profile table.
---

- Identity lives in Supabase Auth (`auth.users`); app-specific profile/membership lives in `public.users` (one row per user, PK = `auth.uid()`), not a separate `profiles` table — avoids duplicating what Supabase already manages.
- Resend is used only as an SMTP relay configured manually in the Supabase Dashboard (Authentication → Emails → SMTP Settings). No Resend API key or package is needed in app code — Supabase Auth sends the confirmation/reset emails itself.
- Column-level write protection (users must not set their own `plan`/`subscription_*`) is enforced with a Postgres trigger (`prevent_membership_self_edit`), not RLS alone — RLS can't restrict specific columns, only rows.
- Supabase returns auth tokens via a URL fragment (`#access_token=...`) on email confirm/reset links, which the server never sees. Pattern: a client-side JS shim on the callback route reads the hash and POSTs tokens to a backend endpoint to establish the session (or forwards them to a password-reset page).
- No `exec_sql` RPC exists for this Supabase project and no direct Postgres connection string is available as a secret — DDL must ship as a `migrations/*.sql` file that the user runs manually in the Supabase SQL Editor; this is a hard blocker for end-to-end testing until they do.
- When migrating off a header-based auth scheme (e.g. `X-License-Key`), grep the whole codebase for the header name before declaring the migration done — secondary gating logic (e.g. PRO-tier feature checks) can live outside the main auth decorator and silently stop working once the client stops sending the header.
- During the transition, legacy license sessions must remain an explicit compatibility path alongside account sessions; do not deploy the account-only gate until active license users have been notified or migrated.
