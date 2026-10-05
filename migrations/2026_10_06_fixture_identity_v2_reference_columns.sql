-- Fixture Identity V2 Part 4A: additive reference columns only.
--
-- Safety contract:
-- * metadata-only nullable UUID columns;
-- * no DEFAULT, NOT NULL, FK, index, backfill, delete, rewrite or reader switch;
-- * existing match_id_hash / match_key contracts remain authoritative;
-- * Learning Archive tables are intentionally excluded from this migration.

-- Current prematch tables.
alter table public.moneyway_1x2 add column if not exists fixture_uid uuid;
alter table public.moneyway_ou25 add column if not exists fixture_uid uuid;
alter table public.moneyway_btts add column if not exists fixture_uid uuid;
alter table public.dropping_1x2 add column if not exists fixture_uid uuid;
alter table public.dropping_ou25 add column if not exists fixture_uid uuid;
alter table public.dropping_btts add column if not exists fixture_uid uuid;

-- Prematch history / snapshot tables.
alter table public.moneyway_1x2_history add column if not exists fixture_uid uuid;
alter table public.moneyway_ou25_history add column if not exists fixture_uid uuid;
alter table public.moneyway_btts_history add column if not exists fixture_uid uuid;
alter table public.dropping_1x2_history add column if not exists fixture_uid uuid;
alter table public.dropping_ou25_history add column if not exists fixture_uid uuid;
alter table public.dropping_btts_history add column if not exists fixture_uid uuid;
alter table public.moneyway_snapshots add column if not exists fixture_uid uuid;

-- Alarm outputs.
alter table public.bigmoney_alarms add column if not exists fixture_uid uuid;
alter table public.dropping_alarms add column if not exists fixture_uid uuid;
alter table public.insider_alarms add column if not exists fixture_uid uuid;
alter table public.mim_alarms add column if not exists fixture_uid uuid;
alter table public.publicmove_alarms add column if not exists fixture_uid uuid;
alter table public.sharp_alarms add column if not exists fixture_uid uuid;
alter table public.volume_leader_alarms add column if not exists fixture_uid uuid;
alter table public.volumeshock_alarms add column if not exists fixture_uid uuid;

-- Sinyal outputs.
alter table public.underdog_signals add column if not exists fixture_uid uuid;
alter table public.confirmed_money_signals add column if not exists fixture_uid uuid;
alter table public.confirmed_money_v2_signals add column if not exists fixture_uid uuid;
alter table public.fake_sharp_signals add column if not exists fixture_uid uuid;
alter table public.early_money_lock_signals add column if not exists fixture_uid uuid;

-- Live and Matchbook data paths.
alter table public.live_fixtures add column if not exists fixture_uid uuid;
alter table public.live_snapshots add column if not exists fixture_uid uuid;
alter table public.matchbook_fixtures add column if not exists fixture_uid uuid;
alter table public.matchbook_1x2_history add column if not exists fixture_uid uuid;
alter table public.matchbook_ou25_history add column if not exists fixture_uid uuid;
alter table public.matchbook_btts_history add column if not exists fixture_uid uuid;

-- Other runtime consumers that currently carry match_id_hash / match_key.
alter table public.analyses add column if not exists fixture_uid uuid;
alter table public.free_matches add column if not exists fixture_uid uuid;
alter table public.telegram_sent_log add column if not exists fixture_uid uuid;
alter table public.license_favorites add column if not exists fixture_uid uuid;

-- Intentionally excluded in Part 4A:
-- * public.learning_archive_capture_outbox
-- * public.learning_archive_retention_holds
-- * public.match_favorites (legacy table)
-- These require their own contract-aware migration/review.
