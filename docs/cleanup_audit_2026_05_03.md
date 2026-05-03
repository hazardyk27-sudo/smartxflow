# Repo Cleanup Audit — 2026-05-03

## Scope
Move legacy data dumps, unused SQL files, old scripts, and `attached_assets/` log/exe files into `archive/` (NEVER delete). Preserve build pipeline and i18n. Verify no production breakage.

## Rollback point
- Pre-cleanup HEAD commit: `5f3107629de4d0712e1d51fdfc776c3ec1563310` (branch `main`)
- Branch/tag creation was blocked by platform (destructive git ops disabled in main agent). Use `git reset --hard 5f3107629de4d0712e1d51fdfc776c3ec1563310` to roll back if needed.

## Out of scope (NOT touched)
- `minify.py` — active build pipeline (kept at root)
- `static/js/inline.js.src` — source for ui.js minification (kept)
- `static/js/inline.js` — minified build artifact (kept; templates may dynamically reference)
- i18n Phase 3 cleanup (`tag_templates_phase3.py`, `static/i18n/_master.csv`, `scripts/i18n_master.py` — untouched)
- `.replit` userenv secrets (already in repo, separate concern)

## Usage verification
| File | Verified by | Result |
|---|---|---|
| `minify.py` | `rg -l "minify\.py"` | only `replit.md` → KEPT |
| `inline.js.src` | `rg -l "inline\.js\.src"` | `replit.md`, `minify.py` → KEPT |
| Templates | `rg "inline\.js" templates/` | only loads `app.js`, `ui.js` |
| `run_services.sh` | direct read | uses `scheduled_scraper.py`, `alarm_engine.py`, `live_scraper.py`, `sinyal_engine.py` only |
| `.replit` deploy | direct read | runs `python app.py & bash run_services.sh & wait` |
| `scheduled_alarm_engine.py` | `rg --type py` | not imported anywhere |
| `underdog_engine.py` | `rg --type py` | only self-reference |
| Root `*.sql` (12 files) | `rg` across `.py/.sh/.js/.html/.md/.toml/.yaml` | 10 unused; `create_alarm_tables_v3.sql` & `supabase_cleanup.sql` only mentioned in `SUPABASE_SCHEMA_FINAL.md` (doc reference) |
| `setup_matchbook_tables.py`, `test_active_keys_filtering.py`, `export_march9*.py` | `rg --type py` | self-reference only |
| `static/smartxflow_signals.zip`, `instagram_post_1.png`, `smartxflow_logo_original.png` | `rg` across templates/code | no references |

## Token / secret scan
Pattern: `supabase|service_role|sk_…|api_key|apikey|bearer |authorization:|cookie:|secret|password|matchbook|telegram|eyJhbGc`

| Group | Result |
|---|---|
| 12 root SQL files | Hits = 0–2 each, all benign comments (e.g. `-- SmartXFlow Supabase Schema`). No secrets. |
| 6 legacy Python scripts | Hits all `os.environ.get('SUPABASE_*')` style references — code reading env vars, no embedded secrets. |
| `march9_all_data.json` | 0 bytes (empty file). |
| `march9_all_data.txt` (15 MB), `march10_all_data.txt` (10 MB) | 0 strict-pattern hits. |
| `attached_assets/*.log` (13 files, ~80 MB total) | High hit counts (86–13522). Likely contain bearer tokens / supabase keys in HTTP debug headers → all routed to `manual_review/` for human inspection. |
| `attached_assets/SmartXFlowAlarmV1.01_…exe` (13 MB) | 0 strict-pattern hits via `strings`. Per plan, still routed to `manual_review/`. |

## Files moved (38 total: 3 + 12 + 6 + 3 + 14)

### `archive/data_dumps/` (3 files)
- `march9_all_data.json`
- `march9_all_data.txt`
- `march10_all_data.txt`

### `archive/sql_legacy/` (12 files)
All root-level `.sql` files: `add_performance_indexes`, `add_unique_constraints`, `create_alarm_settings_table`, `create_alarm_tables_INITIAL_SETUP`, `create_alarm_tables_v3`, `create_all_tables`, `create_phase2_tables`, `fix_insider_config`, `health_check`, `migrate_sharp_alarms_v5`, `supabase_cleanup`, `supabase_schema`.

### `archive/scripts_legacy/` (6 files)
- `setup_matchbook_tables.py`
- `test_active_keys_filtering.py`
- `export_march9.py`
- `export_march9_txt.py`
- `underdog_engine.py`
- `scheduled_alarm_engine.py`

### `archive/static_unused/` (3 files)
- `static/smartxflow_signals.zip`
- `static/images/instagram_post_1.png`
- `static/images/smartxflow_logo_original.png`

### `archive/manual_review/` (14 files — REQUIRES HUMAN REVIEW)
- 13 `attached_assets/smartxflow_*.log` files (~80 MB total)
- 1 `attached_assets/SmartXFlowAlarmV1.01_1764179311466.exe` (13 MB)

## Validation after move
1. Workflow `SmartXFlow Web` restarted cleanly.
2. Gunicorn boot OK, 2 workers up, cleanup scheduler active.
3. `GET /` → HTTP 200 (19,939 bytes).
4. Alarm cache loaded: Sharp(4), BigMoney(13), VolumeLeader(28).
5. Frontend rendered 269 matches; alarms cache fetched 623 records.
6. `[Supabase] analyses table exists`, `[Cleanup] Old matches cleanup completed`.
7. No new errors in logs related to moved files.

Pre-existing minor warning (unrelated): `[Fav] Error loading past favorites` — endpoint returning HTML for `/api/...` request; predates this task.

## Out-of-scope security finding (flagged by code review)
`.replit` `[userenv.shared]` contains a live-looking Supabase **service_role** JWT in `SUPABASE_KEY`, plus 3 site cookies (`ARBWORLD_COOKIES`, `COOKIE_STRING`, `BETWATCH_COOKIE`). This is pre-existing and unrelated to this cleanup, but recommend rotating the Supabase key and migrating these to Replit Secrets (not committed to repo).

## Notes for future
- `SUPABASE_SCHEMA_FINAL.md` references `create_alarm_tables_v3.sql` and `supabase_cleanup.sql` (now in `archive/sql_legacy/`). Doc references are stale but don't break runtime; update when next editing the doc.
- `archive/manual_review/` is ~93 MB. Recommend reviewing logs for tokens, then deciding whether to git-history-purge (separate operation, not done here).
- ~~Consider adding `archive/` to `.dockerignore` / build excludes so 90+ MB doesn't ship to deploy.~~ **DONE (Task #179, 2026-05-03):** `build.sh` now removes `archive/` during deploy build (Replit VM deployment). Dev workspace unaffected (doesn't run build.sh).

## Rollback procedure if regression found later
```
git reset --hard 5f3107629de4d0712e1d51fdfc776c3ec1563310
```
(Then restart `SmartXFlow Web` workflow.)
