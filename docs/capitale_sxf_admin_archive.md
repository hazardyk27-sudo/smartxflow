# SmartXFlow Admin → CAPİTALE GitHub SXF Arşivi

**Development status:** implemented and offline-tested on SmartXFlow `preview`. **Not deployed to production. No live bulk Release migration has been performed.** CAPİTALE workflow and exporter are committed on `hazardyk27-sudo/capitale:main`.

## Admin screen
After an approved deployment, open `/admin` → **GitHub Arşiv** (or `/admin/sxf-archive`).

1. Authorize archive actions using the separate admin PIN.
2. Select the fixture kickoff day in **Europe/Istanbul**, beginning 2026-10-09.
3. Check **Tüm Snapshotlar** and/or **Konsantre Arşiv**.
4. Click **Seçili arşivleri başlat**. Each selected kind dispatches a separate GitHub Actions run.
5. Monitor the GitHub Actions history shown on the page. `QUEUED_NOT_ARCHIVED` means only that GitHub accepted the job request. A verified archive requires a **successful** Action with download, gzip, SHA-256, JSONL restore, verification receipt, and a readback-verified per-day index file.

**Data policy:** Supabase `research_archive` is SELECT-only; GitHub is the only destination. No source deletes/updates/schema changes. All captures, including no-signal, after-kickoff, unresolved fixture/alias, and null IDs remain in the full raw archive. Only checkpoints filter by historical cutoff. Nine-point grid: T-72, T-60, T-40, T-24, T-12, T-8, T-6, T-3, T-1, per 1X2/OU2.5/BTTS and fixture, recording actual cutoff MISSING where necessary.

## One-time configuration (owner-operated; NEVER put credentials into chat, code or logs)

### SmartXFlow admin server environment
- `SXF_ARCHIVE_ADMIN_PIN`: strong, private, random PIN/passphrase (at least 16 characters) **separate from** the existing, weak admin login. Archive-unlock sessions expire after 30 minutes and are revoked on admin login/logout. Client submits the PIN only to the same-origin server.
- `CAPITALE_GITHUB_ACTIONS_TOKEN`: restricted GitHub fine-grained token scoped only to `hazardyk27-sudo/capitale`, with the minimal **Actions read/write** permission needed to dispatch `sxf-admin-archive.yml` and read runs. It never appears in the browser or a saved report.

### CAPİTALE GitHub Actions repository secret
- `SXF_ARCHIVE_DATABASE_URL`: connection string for a **genuinely SELECT-only Postgres role** with only the needed `research_archive` tables, SSL required. A privileged `postgres` role or Supabase service-role/API key is unacceptable. Configure privately through GitHub repository Settings → Secrets and variables → Actions.
- The source `research_archive` schema is not exposed through the Supabase Data REST API. Do **not** change its API exposure, RLS, grants, or data as part of this archival implementation.
- If SELECT-only credentials do not already exist, their secure DBA provisioning is a **separate**, explicitly authorized task; do not improvise write privileges during archive migration.

### Deploy
- Follow the existing SmartXFlow reviewed release/deployment procedure. **Do not replace production `main` with the `preview` branch wholesale:** the branches differ in many unrelated files.
- Changed SmartXFlow files: `sxf_capitale_archive_admin.py`, `templates/admin_sxf_archive.html`, small integration edits to `app.py` and `templates/admin.html`.
- CAPİTALE artifacts: `scripts/export_sxf_daily_archive.py`, `.github/workflows/sxf-admin-archive.yml`, `tests/test_sxf_daily_archive.py`, `.github/workflows/sxf-daily-archive-tests.yml`.
- Verify server-side secrets configured, authenticate in the admin screen, and **start with one historical concentrated pilot**, not the biggest all-tables raw day. Examine Actions job and resulting draft Release before beginning large full-raw transfers.

## GitHub Release and status rules
- Full raw: `sxf-raw-YYYY-MM-DD-v1` (DRAFT).
- Concentrated: `sxf-concentrated-YYYY-MM-DD-v1` (DRAFT).
- Large raw exports use **25,000-row bounded gzip JSONL chunks** per safe source table. The exporter preserves original full source rows (`row_to_json`). Archive-run source counts are compared to actual SQL SELECT counts and transfer rows. Any source PARTIAL/mismatched counts are explicitly flagged.
- Concentrated uses 25-fixture materialized source batches, all nine T points per fixture and all three markets; never selects observations after the checkpoint.
- Each run refuses to overwrite an existing Release/tag or an existing `admin_release_receipt_v1.json`. If a run fails with a partial DRAFT asset set, **do not delete it automatically**. Audit before any correction or versioned retry.
- After successful upload, every asset is downloaded and byte-compared, decompressed, row/hash-checked, then a verification receipt is uploaded and read back. An append-only per-day GitHub index is created in the corresponding `03_full_snapshots/` or `04_concentrated/` directory.
- Existing `01_scan_results`, `02_outcome_performance` and daily `manifest.json` histories are **not automatically rewritten**, and neither `migration_complete` nor source `COMPLETE` is inferred from a GitHub Action success.
- Repo is PUBLIC. Draft Release protects unpublished raw assets from immediate public publication; publication/redistribution still needs explicit rights and sensitive-content review.

## Validation already performed
- Source-only SQL confirmed a nine-T checkpoint lookup for a 2026-10-09 fixture without future observations.
- Exporter compiled and five standalone gzip/JSONL/grid integrity tests passed.
- Isolated Flask app tests passed for admin gate, PIN, CSRF, date/type validation, Actions dispatch mock, 2-minute same-job repeat prevention, and 30-minute unlock expiration.
- GitHub Actions YAML parsed successfully. A real read-only DB export and GitHub Release upload remain untested until the private credentials are configured.
