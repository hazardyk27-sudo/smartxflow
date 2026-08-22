-- Task #301: Email/Password Auth via Supabase Auth + Resend
-- Replaces the key-based access system with Supabase Auth + a profile/membership table.
--
-- Additive & idempotent: safe to run even though 2026_05_03_auth_users.sql was written
-- earlier but never actually applied (public.users did not exist in this project).
-- Run this once, manually, in the Supabase SQL Editor.

-- 1) public.users: one row per Supabase Auth user (id = auth.uid()).
--    Authentication identity lives in auth.users (Supabase-managed); this table adds
--    the SmartXFlow-specific profile + membership fields on top of it.
CREATE TABLE IF NOT EXISTS public.users (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT UNIQUE NOT NULL,
    display_name TEXT,
    fcm_token TEXT,
    plan TEXT NOT NULL DEFAULT 'core',
    subscription_status TEXT NOT NULL DEFAULT 'inactive',
    subscription_started_at TIMESTAMPTZ NULL,
    subscription_expires_at TIMESTAMPTZ NULL,
    migrated_from_license TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ NULL,
    hard_delete_after TIMESTAMPTZ NULL
);

-- In case an earlier partial run created the table without these columns:
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS plan TEXT NOT NULL DEFAULT 'core';
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS subscription_status TEXT NOT NULL DEFAULT 'inactive';
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS subscription_started_at TIMESTAMPTZ NULL;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS subscription_expires_at TIMESTAMPTZ NULL;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS migrated_from_license TEXT NULL;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_users_email ON public.users (email);
CREATE INDEX IF NOT EXISTS idx_users_deleted_at ON public.users (deleted_at) WHERE deleted_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_users_hard_delete_after ON public.users (hard_delete_after) WHERE hard_delete_after IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_users_subscription_status ON public.users (subscription_status);

-- 2) licenses: track legacy-key -> account migration so a key can only migrate once.
ALTER TABLE public.licenses ADD COLUMN IF NOT EXISTS migrated_to_user_id UUID NULL;
ALTER TABLE public.licenses ADD COLUMN IF NOT EXISTS migrated_at TIMESTAMPTZ NULL;
CREATE INDEX IF NOT EXISTS idx_licenses_migrated_to_user_id ON public.licenses (migrated_to_user_id) WHERE migrated_to_user_id IS NOT NULL;

-- 3) account_deletion_queue (from Task #181 plan; unrelated to this task but never
--    actually created either, and auth_helpers.py already assumes it exists).
CREATE TABLE IF NOT EXISTS public.account_deletion_queue (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL,
    email TEXT NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    scheduled_hard_delete_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ NULL,
    cancelled_at TIMESTAMPTZ NULL,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_acct_del_pending ON public.account_deletion_queue (scheduled_hard_delete_at)
    WHERE completed_at IS NULL AND cancelled_at IS NULL;

-- 4) Auto-create a public.users profile row whenever a new Supabase Auth user is
--    created, so profile creation never depends solely on client/app-side code.
CREATE OR REPLACE FUNCTION public.handle_new_auth_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    INSERT INTO public.users (id, email, plan, subscription_status)
    VALUES (NEW.id, NEW.email, 'core', 'inactive')
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_auth_user();

-- 5) Block normal (non service-role) updates to membership fields. RLS alone can't
--    express "these specific columns are read-only for the owner", so a trigger
--    enforces it: only the service role (used exclusively by trusted backend code,
--    never exposed to the browser) may change plan/subscription_*.
CREATE OR REPLACE FUNCTION public.prevent_membership_self_edit()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF auth.role() IS DISTINCT FROM 'service_role' THEN
        IF NEW.plan IS DISTINCT FROM OLD.plan
           OR NEW.subscription_status IS DISTINCT FROM OLD.subscription_status
           OR NEW.subscription_started_at IS DISTINCT FROM OLD.subscription_started_at
           OR NEW.subscription_expires_at IS DISTINCT FROM OLD.subscription_expires_at THEN
            RAISE EXCEPTION 'Membership fields can only be changed by the backend';
        END IF;
    END IF;
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_prevent_membership_self_edit ON public.users;
CREATE TRIGGER trg_prevent_membership_self_edit
    BEFORE UPDATE ON public.users
    FOR EACH ROW EXECUTE FUNCTION public.prevent_membership_self_edit();

-- 6) Row Level Security: a user may only see/edit their own profile row.
--    The app's backend uses the service_role key for admin/membership writes, which
--    bypasses RLS entirely, so this only constrains direct client-side Supabase access.
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.account_deletion_queue ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "select own profile" ON public.users;
CREATE POLICY "select own profile" ON public.users
    FOR SELECT USING (auth.uid() = id);

DROP POLICY IF EXISTS "update own profile" ON public.users;
CREATE POLICY "update own profile" ON public.users
    FOR UPDATE USING (auth.uid() = id) WITH CHECK (auth.uid() = id);

-- Verification queries (run manually after applying):
-- SELECT column_name, is_nullable, data_type FROM information_schema.columns WHERE table_name='users' AND table_schema='public' ORDER BY ordinal_position;
-- SELECT tgname FROM pg_trigger WHERE tgrelid = 'public.users'::regclass;
-- SELECT tgname FROM pg_trigger WHERE tgrelid = 'auth.users'::regclass AND tgname = 'on_auth_user_created';

-- ============================================================================
-- MANUAL SUPABASE DASHBOARD CONFIGURATION REQUIRED (cannot be done via SQL/API):
-- ============================================================================
-- A) Authentication -> Emails -> SMTP Settings: enable "Custom SMTP", using Resend:
--      Host: smtp.resend.com   Port: 587 (or 465)   Username: resend
--      Password: <your Resend API key>
--      Sender email: no-reply@smartxflow.com (must be a domain verified in Resend)
--      Sender name: SmartXFlow
-- B) Authentication -> URL Configuration:
--      Site URL: https://smartxflow.com (production) — set to the current dev
--        domain temporarily while testing in this workspace.
--      Redirect URLs: add both the production and current dev domain's
--        "/auth/callback" path (e.g. https://smartxflow.com/auth/callback and
--        https://<dev-domain>/auth/callback).
-- C) Authentication -> Email Templates: customize "Confirm signup" and
--      "Reset password" templates (subject/body) to match SmartXFlow branding.
--      The confirmation link variable is {{ .ConfirmationURL }}.
-- D) Authentication -> Providers -> Email: keep "Confirm email" ON so unverified
--      users cannot log in before verifying.
