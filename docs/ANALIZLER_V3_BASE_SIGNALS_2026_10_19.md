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


## 2026-10-19 — V4 redesign after user screenshot review

- Removed the horizontal list of small engine tabs and the simultaneous,
  overwhelming mixed-engine signal-card feed.
- Replaced it with **one substantial click target per Base motor** in a
  graphite directory. V1/V2 are fully independent cards, as are all other
  known engines, including those with 0 signals on the selected day.
- Existing top date rail remains; it displays yellow activity dots for the
  selected scope. On the directory scope, it counts all engines; inside a
  motor it counts only that motor's signals. Selecting a day preserves the
  current motor.
- Clicking an engine opens **only its own fixtures**, grouped by physical
  UID + kickoff. Multiple signals on the same fixture are rendered inside
  one match card, not as visually duplicated matches. A Back button
  restores focus to the exact originating engine.
- Removed an unnecessary second horizontal scrollbar. Search is available
  only within a selected motor. Dates outside the server's bounded feed
  window fail gracefully before issuing an invalid API request.
- Uses application's existing shared palette: background `#141719`,
  cards `#1c1f23`, borders `#2e3238`, restrained green `#22c55e`;
  no separate blue/teal visual theme.
- Mobile: two-column compact engine directory on standard phones
  (one column on very narrow screens); a single-column match list.
- Historic preliminary T-8 rows stay visibly historical after a real T-6
  decision; all cards remain explicitly `SHADOW / TEST`.
- The protected server-side source and data-access contract did not change.
- New Node interaction tests exercise actual simulated tile clicks,
  strict V1/V2 separation, date switching, back navigation, grouping
  multiple signals per physical match, and unsafe HTML escaping.

**Deployment status:** V4 files are on GitHub `preview` only; production
`main` and Hetzner still carry the earlier V3 release. Do not confuse
a passing `preview` CI test with a published V4 browser experience.
Exact-SHA release authorization is required before promotion.
