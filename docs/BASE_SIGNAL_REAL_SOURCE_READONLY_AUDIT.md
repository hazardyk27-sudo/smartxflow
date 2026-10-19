# Base Signals — source read-only audit, 2026-10-19

This inspection made no source database changes and did not deploy or activate a service.

## Confirmed

- `fixtures`: approximately 3,961 rows (catalog estimate). `fixture_uid` and `kickoff_utc` are mandatory.
- `moneyway_snapshots`: approximately 5,875,509 rows (catalog estimate), around 1,580 MB total. Its `fixture_uid` column is nullable; PostgreSQL sampling statistics estimate 5.07% null values. This is an estimate, not a full-table audit.
- Snapshot indexes: `id` primary key, `match_id_hash`, and two timestamp-only `scraped_at_utc` indexes. No `(fixture_uid, scraped_at_utc, id)` composite index currently exists.
- A SELECT-only EXPLAIN for UID plus time range used the timestamp index and a separate residual UID filter; estimates cannot be interpreted as measured runtime.
- One real fixture sample had a complete 1X2 market group and an incomplete OU25 group (O side only) near T-1. Its T-6 30-minute source window contained zero rows; a later observation must not replace missing T-6 evidence.
- Earlier local shadow scheduling had an incomplete-data lifecycle flaw: jobs with no source rows could enter the local completed journal. The latest preview fix treats these as WAITING_DATA without changing frozen signal conditions.

## Actionable blockers

1. Review and authorize the separately proposed composite snapshot index and validate the actual query plan and writer impact before bulk scanning.
2. Use a one-fixture read-only smoke and then limited Preview operation. Postpone source trigger changes until separately justified.
3. Independently verify a real continuous 24-hour shadow after Preview permissions; synthetic tests are not a substitute.

No migrations, server sync or production rollout were performed in this audit.
