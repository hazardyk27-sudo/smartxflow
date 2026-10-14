-- Prevent future public-schema objects from silently re-opening client access.
--
-- Existing public tables/functions have already been hardened individually. On
-- this project, however, the legacy Supabase default ACL still grants new
-- objects created by postgres/supabase_admin broad privileges to anon and
-- authenticated. That can re-introduce exposure with a later migration even
-- when today's schema is locked down.
--
-- Keep service_role defaults intact: production server workers intentionally
-- use the server-only service-role credential. Public client roles must be
-- granted access explicitly by the migration that creates an app-facing object.

BEGIN;

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    REVOKE ALL PRIVILEGES ON TABLES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    REVOKE ALL PRIVILEGES ON SEQUENCES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    REVOKE ALL PRIVILEGES ON FUNCTIONS FROM PUBLIC, anon, authenticated;

ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public
    REVOKE ALL PRIVILEGES ON TABLES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public
    REVOKE ALL PRIVILEGES ON SEQUENCES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public
    REVOKE ALL PRIVILEGES ON FUNCTIONS FROM PUBLIC, anon, authenticated;

COMMIT;
