# SmartXFlow i18n coverage audit — 2026-10-20

## Scope, baseline and method

Repository: `hazardyk27-sudo/smartxflow`. Baseline: production main `b78c604ce12d2a4ad7178eb5b893df80bc0c7de4`. Changes are only on `preview`; no production deploy, Replit changes or database writes.

Supported app languages (from `static/js/i18n.js`): `tr`, `en`, `de`, `fr`, `nl`, `it`, `es`. The app uses the `sxf_lang` local-storage selection; its `SXFI18n.apply()` translates elements with `data-i18n`, `data-i18n-html` and `data-i18n-attr`. JavaScript-injected HTML requires explicit translation bindings and rerendering.

Baseline dictionary parity: all 7 `static/i18n/*.json` files contain exactly **1,022 leaf keys**, with no missing or empty keys. **This proves key parity, not full application translation coverage.**

This audit uses source/static-code inspection and representative browser tests. The counts below are **candidate** strings found by heuristic scanning for Turkish characters in rendered-looking HTML/text; they are *not* guaranteed untranslated strings (some are correctly keyed, proper names or runtime examples), and ASCII-only Turkish text will be missed.

## Confirmed affected application surfaces

| Priority | Surface/source | Evidence / why untranslated |
|---|---|---|
| P0 | Analizler V4, `static/js/base-signals.js` and `templates/index.html` modal | Before fix: 0 direct dictionary lookups, Turkish engine descriptions/categories, date formatter forced to `tr-TR`, pick/result/score labels, errors, buttons and aria/placeholder all hardcoded. Lazy-created nodes not translated on switch |
| P0 | Live matches, `static/js/live-tab.js` (and `.src`) | Literal labels such as `Canlı Maçlar`, `LİG`, `MAÇ`, `HACİM`, `Şu an canlı maç bulunamadı`, PRO gate; no direct `SXFI18n.t` calls or locale-change listener |
| P0 | Alarms, `static/js/alarm-sidebar.js`, `static/js/modal-alarms.js` | Dynamic labels `ORAN DÜŞÜŞÜ`, `LİDER DEĞİŞTİ`, `HACİM ŞOKU`, `Büyük Para Girişi`, levels and explanatory text hardcoded; no direct dictionary lookups |
| P0 | Match modal/chart, `static/js/modal-info.js`, `static/js/modal-chart.js`, `static/js/modal-entry.js` | Literal `TOPLAM HACİM`, `Üst`, `Hayır`, `Tüm veri`, `1 gün`, export labels, missing-data and error messages; no direct dictionary lookups |
| P1 | App global runtime, `static/js/app.js`, `static/js/ui.js` / `static/js/inline.js` | Partial use of `SXFI18n.t` and `window._t`, but visible dynamic Turkish remnants remain (license/session warnings, analyst descriptions, tooltips, empty states); language-change lifecycle needs review |
| P1 | Polymarket page, `templates/poly.html` | **0 `data-i18n` bindings**, roughly **63 Turkish-bearing visible text candidates** (search, tabs, buy/sell, wallet stats and dialogs). A separate translation integration is required |
| P1 | Site status page, `templates/status.html` | 30 existing i18n bindings; around 21 Turkish-bearing visible candidates, including service explanations and snapshot counts; confirm which are bound |
| P1 | Legacy `templates/analysis.html` page | 33 existing bindings; dynamic analyst/signal descriptions and PRO messages remain in embedded JS. Check actual route/visibility before changing old pages |
| P2 | Back-office `templates/admin.html`, `static/js/admin-panel.js` | 0 template bindings and roughly 201 Turkish-bearing visible candidates in admin template; complete translation is a separate major scope |
| P2 | Public content pages `landing.html`, `pricing.html`, `nedir.html`, `rehber*.html`, `legal.html` | Existing translation bindings are partial. Candidate textual regions remain; verify per-locale against the DOM, including SEO text and footer |
| P2 | `match_detail.html`, authentication/account templates | Some use few/no bindings, and embedded scripts contain untranslated state/error messages; route-specific QA needed |

### Source-audit candidates by template

Source-scanned candidate counts (NOT untranslated-item counts): `admin.html` ~201, `landing.html` ~86, `rehber_canli_oran_takibi.html` ~68, `poly.html` ~63, `rehber_para_hareketi.html` ~62, `pricing.html` ~59, `rehber_oran_analizi.html` ~50, `index.html` ~46, `nedir.html` ~36, `rehber.html` ~33, `status.html` ~21, `analysis.html` ~17, `legal.html` ~8, `match_detail.html` ~3. Other templates may have ASCII-only untranslated strings and must not be assumed covered.

## Root causes and remediations

1. **Dictionary parity is not UI coverage:** adding strings to JSON does not localize DOM nodes or JavaScript strings unless all visible surfaces use their keys.
2. **Post-render and lazy modules:** `SXFI18n.apply()` handles existing annotated DOM only. Modules that construct `innerHTML` must translate at render time; an `i18n:change` subscriber must regenerate the view without changing server data, selected engine or filters.
3. **Non-localized dates:** date and weekday formatters must use the active locale, while timezone stays explicitly `Europe/Istanbul` as required.
4. **Dynamic text / variables:** teams, selections, odds, and outcomes must use localized templates with placeholders; escape untrusted match/team strings at the final HTML boundary.
5. **Asynchronous language loads:** two overlapping locale fetches can resolve out of order. Guard with a monotonically increasing request id; the latest user selection wins. The initial language fallback must not override newer selections.
6. **Separate apps:** Polymarket and admin are not fully wired into `SXFI18n`. They require explicit owner/scope review and must not be called “fully translated” based only on `/app`.
7. **Immutable data:** team, league and proper names from source APIs do not need arbitrary machine translation; user-visible interface labels and messages do.

## Implemented in this preview batch

- Analizler V4: **84 semantic keys × seven languages = 588 translated strings** under `app.v4`.
- Localized all V4 static controls, accessibility labels, engine descriptions, cards, market names, outcomes, errors, load-failure toasts and placeholders.
- Changed weekday / date rendering to the chosen language without changing the TR clock timezone.
- Added language-change rerender that preserves the engine/day and avoids re-fetching the Base feed.
- Added Chromium regression for 7 locales on desktop/phone plus existing five-viewport smoke, dictionary parity and template accessibility assertions.
- Guarded async i18n loads against locale fetch races.

## Remaining work to declare the whole application fully translated

A. Live tab and live/mobile cards: key every title, row, state, tooltip and empty/loading/error message; unit + seven-locale screenshot coverage.

B. Alarm sidebar, alarm details and filters: localize all engine names, descriptions and dynamic value text; preserve source data and alarm logic; regression test on desktop and mobile.

C. Match details, charts, graph exports, guide/analyst screens and global runtime: use shared translation helpers rather than ad hoc string replacement; guarantee reactive updates on `i18n:change`.

D. Polymarket: first integrate the shared locale loader, then convert wallet/bet stats, forms, selection filters and all messages in `templates/poly.html`; verify account isolation and transaction logic.

E. Admin and public/legal/help pages: translate visible copy and attributes, then check each route (SEO tags, login forms, email/password validation, errors and tooltips) for all seven languages.

F. CI acceptance: missing-key check across all locale JSON; no untranslated dynamic labels for the audited surfaces; 7× desktop/mobile DOM screenshots plus refresh/re-login/locale persistence; long-text overflow and screen-reader names.

**Production readiness:** this batch fixes the Analizler V4 language gap and loader race; **it is not a claim of complete application-wide translation**. Promote only after specific user approval and release gates.
