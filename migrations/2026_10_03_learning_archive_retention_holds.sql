-- Learning Archive retention holds
-- Keeps selected-match SXF source history protected until verified archive finalization.

create table if not exists public.learning_archive_retention_holds (
    case_id text primary key,
    match_id_hash varchar(64) not null,
    prediction_at timestamptz not null,
    status text not null default 'PENDING' check (status in ('PENDING', 'FINALIZED', 'CANCELLED')),
    created_at timestamptz not null default now(),
    finalized_at timestamptz,
    archive_reference text,
    checksum_summary text
);

create index if not exists idx_learning_archive_retention_holds_pending
    on public.learning_archive_retention_holds (status, created_at)
    where status = 'PENDING';

create index if not exists idx_learning_archive_retention_holds_match
    on public.learning_archive_retention_holds (match_id_hash);

alter table public.learning_archive_retention_holds enable row level security;

-- Internal server-side pipeline only. Never expose archive-control rows to end users.
revoke all on table public.learning_archive_retention_holds from anon, authenticated;
grant select, insert, update, delete on table public.learning_archive_retention_holds to service_role;
