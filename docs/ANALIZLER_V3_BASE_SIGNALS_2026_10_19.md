# SmartXFlow Analizler V3 — new Base signal centre

**Status (2026-10-19):** GitHub `preview` implementation tested.
**Not promoted to `main`, not deployed to production or Replit Preview.**
Motors continue running exclusively on Hetzner, independent of this UI.

## User request implemented

- Reuse the existing **Analizler** entry button on desktop and mobile in
  `templates/index.html`; open a **new** full-size Sinyal Merkezi panel.
- Remove old analyst/motor cards and obsolete legacy star indicators from the
  `/app` Analizler flow. The legacy `/api/analyses` write/admin endpoints
  and external `/analysis` page are intentionally not deleted because they
  are separate consumers; historical records are never purged.
- Keep **Kılavuz** working through the existing lazy-loaded `ui.js`
  `moves` branch; do not load obsolete analysis content when Analizler is
  pressed.
- Dark premium responsive modal, horizontally scrollable **daily calendar**
  centered on Europe/Istanbul today, yellow day activity dots, previous/next
  10-day windows, direct Today jump. Calendar dots are recalculated for the
  selected engine. Date switching never requests a different account's data.
- **Tüm motorlar** view groups cards by engine. Engine tabs allow a direct
  per-engine per-day view, with per-day signal counts. Date, engine, team and
  league search are all functional.
- Each card shows physical fixture teams/league, TR kickoff, explicit market
  and selection, snapshot odds only if recorded, engine, checkpoint and T-8
  or T-6 stage. Preliminary T-8 events with completed authoritative T-6
  market decisions are marked **historical** and visually de-emphasized.
- `SHADOW / TEST` label is persistent. No false betting performance,
  confidence, outcomes or imaginary fixture cards.

## Data contract and access

`GET /api/base-signals/feed?start=YYYY-MM-DD&days=21`

- Requires verified **PRO** account membership or a valid PRO legacy license,
  with a blocked expired account token; TEST and anonymous access fail closed.
- Supabase service-role credentials remain server-side. Only bounded PostgREST
  GET calls are made to
  `sxf_base_signal_events`, `sxf_base_checkpoint_jobs`, and `fixtures`.
- Joins on **canonical physical fixture_uid**, job_id and exact kickoff_utc,
  and requires `sxf_base_checkpoint_jobs.state=COMPLETED`.
- Rejects unknown/inconsistent events, fake/incomplete pick identity and
  partial pagination. T-6 `MARKET_DECISION` / NO_HIT is not a user signal;
  it can only qualify a T-8 event as historical.
- `Europe/Istanbul` local fixture **kickoff day**, not UTC event write day,
  controls calendar grouping.
- Capped 21-day window, 8 pages × 250 events and 75-id lookup batches.
  No client secrets, offline fallback data or fake counts.

## Changed source

- `templates/index.html` — original button routes to new lazy modal.
- `static/js/base-signals.js` — date/motor/search interactions and cards.
- `static/css/base-signals.css` — responsive dark theme with scoped styles.
- `app.py` — PRO-gated read-only route.
- `base_signal_engine/feed.py` — isolated feed, with no legacy services
  import side effects.
- `static/js/app.js(.src)` — legacy analysis star/analyses API request
  retired. Old Kılavuz lazy loader remains separately operational.

## Verification

- GitHub V3 contract/action checks passed:
  [Analizler V3 UI Contracts](https://github.com/hazardyk27-sudo/smartxflow/actions/runs/39322634278)
  (unit/static security/UI/JS checks).
- [Frontend Performance Tests](https://github.com/hazardyk27-sudo/smartxflow/actions/runs/39322849779)
  passed after removal of legacy analysis stars.
- **Actual Hetzner → Supabase read-only V3 feed smoke** passed at exact
  GitHub `preview` SHA `cbb4e25c29fac5696a647f609d31c681400357ed`:
  **17 real event cards across 7 motors and 2 fixture days**, 440ms,
  23.6MB peak RAM, 0 database writes. Run
  [39323034633](https://github.com/hazardyk27-sudo/smartxflow/actions/runs/39323034633).
- The actual Flask button click and modal layout have **not** yet been
  browser-preview validated in deployed Replit/production. Do not claim
  otherwise. An exact-SHA Preview sync/user review is the next UI step.

## Release gate

User must explicitly approve the exact `preview` SHA for Preview sync
under `.agents/contracts/RELEASE_FLOW.md`. Before promotion to `main`,
validate the responsive UI/browser, account permissions and product wording
against real PRO and CORE sessions. No Hetzner web deploy until the separate
production release approval. Base motors remain in limited Hetzner shadow
pending their own source health and 24h review.
