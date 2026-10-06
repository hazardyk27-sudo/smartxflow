-- Fixture Identity V2 temporary safety restore.
--
-- Purpose:
-- * keep the currently-running legacy fixture writer functional while the
--   provider-authoritative runtime cutover is completed;
-- * restore UNIQUE(match_id_hash) only when no duplicate legacy hashes exist;
-- * keep fixture_uid, provider registry, provider RPC, and non-unique hash index.
--
-- IMPORTANT: SMARTXFLOW_FIXTURE_UID_AUTHORITATIVE_WRITE must remain disabled
-- while this temporary guard is present. The final controlled cutover will
-- remove this UNIQUE constraint again after the legacy writer is retired.

do $$
begin
    if exists (
        select match_id_hash
        from public.fixtures
        group by match_id_hash
        having count(*) > 1
    ) then
        raise exception 'fixture_identity_v2_safety_restore: duplicate match_id_hash groups exist';
    end if;

    if not exists (
        select 1
        from pg_constraint c
        join pg_class t on t.oid = c.conrelid
        join pg_namespace n on n.oid = t.relnamespace
        where n.nspname = 'public'
          and t.relname = 'fixtures'
          and c.conname = 'fixtures_match_id_hash_key'
          and c.contype = 'u'
    ) then
        alter table public.fixtures
            add constraint fixtures_match_id_hash_key unique (match_id_hash);
    end if;
end;
$$;
