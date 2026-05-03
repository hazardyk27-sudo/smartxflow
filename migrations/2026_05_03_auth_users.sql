-- Task #181: Google Play Faz 1 — Supabase Auth + Account Deletion
-- Risk-free additive migration: hiçbir mevcut tablo/kolon değiştirilmez,
-- sadece yeni tablo + yeni nullable kolon eklenir.
--
-- Bu migration manuel olarak Supabase SQL Editor'de çalıştırılmalıdır.
-- Çalıştırılmadan önce mevcut sistem değişmeden çalışmaya devam eder.

-- 1) users: app-level kullanıcı profil tablosu (Supabase auth.users ile id=auth.uid eşleşir)
CREATE TABLE IF NOT EXISTS public.users (
    id UUID PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    display_name TEXT,
    fcm_token TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ NULL,
    hard_delete_after TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS idx_users_email ON public.users (email);
CREATE INDEX IF NOT EXISTS idx_users_deleted_at ON public.users (deleted_at) WHERE deleted_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_users_hard_delete_after ON public.users (hard_delete_after) WHERE hard_delete_after IS NOT NULL;

-- 2) licenses tablosuna user_id ekle (NULLABLE — eski lisanslar etkilenmez)
ALTER TABLE public.licenses
    ADD COLUMN IF NOT EXISTS user_id UUID NULL;

CREATE INDEX IF NOT EXISTS idx_licenses_user_id ON public.licenses (user_id) WHERE user_id IS NOT NULL;

-- 3) account_deletion_queue: 30 gün sonra hard delete edilecek hesapların log'u
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

-- 4) RLS — service_role her şeyi okur/yazar (default), anon hiçbir şey görmez (default)
-- Frontend Supabase erişimi yok; tüm okuma/yazma backend üzerinden olacak.
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.account_deletion_queue ENABLE ROW LEVEL SECURITY;

-- Verification queries (manuel kontrol için):
-- SELECT count(*) FROM public.users;
-- SELECT count(*) FROM public.account_deletion_queue;
-- SELECT column_name, is_nullable FROM information_schema.columns WHERE table_name='licenses' AND column_name='user_id';
