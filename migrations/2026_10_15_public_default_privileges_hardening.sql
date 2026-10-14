-- Prevent future project migrations from silently re-opening public client access.
--
-- Existing public tables/functions have already been hardened individually. The
-- project migration/SQL executor runs as postgres, whose legacy default ACL still
-- grants newly created public tables/sequences/functions broad privileges to
-- anon and authenticated unless each migration remembers to revoke them.
--
-- Keep service_role defaults intact: production server workers intentionally use
-- the server-only service-role credential. Public client roles must be granted
-- access explicitly by the migration that creates an app-facing object.
--
-- Supabase also has platform-owned supabase_admin default ACL entries. Project
-- SQL executes as postgres and is not permitted to alter that role's defaults,
-- so this migration deliberately hardens only the project-owned postgres ACL.

BEGIN;

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    REVOKE ALL PRIVILEGES ON TABLES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    REVOKE ALL PRIVILEGES ON SEQUENCES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    REVOKE ALL PRIVILEGES ON FUNCTIONS FROM PUBLIC, anon, authenticated;

COMMIT;
