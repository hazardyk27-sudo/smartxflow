-- Post-cutover UID reader performance repair.
-- These indexes match the runtime pattern:
--   WHERE fixture_uid = ? ORDER BY scraped_at DESC LIMIT 1
--
-- Deliberately separate from the authoritative-writer unblock so production can
-- apply/verify the identity fix first.
-- CONCURRENTLY avoids long write-blocking on large history tables.

create index concurrently if not exists moneyway_1x2_history_fixture_uid_scraped_at_idx
    on public.moneyway_1x2_history (fixture_uid, scraped_at desc);

create index concurrently if not exists moneyway_ou25_history_fixture_uid_scraped_at_idx
    on public.moneyway_ou25_history (fixture_uid, scraped_at desc);

create index concurrently if not exists moneyway_btts_history_fixture_uid_scraped_at_idx
    on public.moneyway_btts_history (fixture_uid, scraped_at desc);
