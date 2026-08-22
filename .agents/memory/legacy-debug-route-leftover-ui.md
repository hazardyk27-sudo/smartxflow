---
name: legacy debug route leftover UI
description: When a user reports an old/retired screen intermittently reappearing after a redesign, check for orphaned debug/test routes still serving the old markup, not just the current live route.
---

## Legacy debug routes can resurrect retired UI

A redesigned page (e.g. /login) can pass every direct test while the user still hits an old screen, because an unrelated leftover debug/test route (e.g. /lisans, robots.txt-disallowed but still publicly reachable) inline-renders the pre-redesign HTML verbatim. It is never linked from any nav/button, so grepping templates/JS for links finds nothing — the match only shows up when grepping app.py/backend source directly for literal old UI strings (exact button/label text from the old screen).

**Why:** SmartXFlow's Supabase-auth login migration replaced the old inline license-key HTML in the real `/login` route, but a copy of the identical HTML remained live at `/lisans` (docstring: "preview activation screen for testing"). The web app's actual served pages were always correct; the leftover route was the only place the old design could still be reached.

**How to apply:** When a user says an old design "keeps coming back" after a confirmed redesign, grep the backend source (not just templates) for exact literal strings from the old screen (e.g. old button labels) to find orphaned routes, and confirm via rapid repeated curl requests to the current route that the server is NOT non-deterministically alternating (rule out server bugs before suspecting client-side cache).
