-- Durable prematch capture outbox.
-- GitHub Actions scheduling is not part of the correctness boundary: Hetzner
-- persists immutable prematch requests here with service-role credentials.

create table if not exists public.learning_archive_capture_outbox (
    event_id text primary key,
    case_id text not null,
    match_id_hash varchar(64) not null,
    observed_at timestamptz not null,
    kickoff_at timestamptz not null,
    prediction_at timestamptz not null,
    status text not null default 'PENDING' check (status in ('PENDING','MIRRORED')),
    created_at timestamptz not null default now(),
    mirrored_at timestamptz,
    last_error text,
    unique (case_id, observed_at)
);

create index if not exists learning_archive_capture_outbox_pending_idx
    on public.learning_archive_capture_outbox (status, observed_at);
create index if not exists learning_archive_capture_outbox_match_pending_idx
    on public.learning_archive_capture_outbox (match_id_hash, status);

alter table public.learning_archive_capture_outbox enable row level security;
revoke all on table public.learning_archive_capture_outbox from anon, authenticated;
grant select, insert, update on table public.learning_archive_capture_outbox to service_role;

create or replace function public.protect_learning_archive_pending_delete()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    if old.match_id_hash is not null and (
        exists (
            select 1
            from public.learning_archive_retention_holds h
            where h.match_id_hash = old.match_id_hash
              and h.status = 'PENDING'
        )
        or exists (
            select 1
            from public.learning_archive_capture_outbox o
            where o.match_id_hash = old.match_id_hash
              and o.status = 'PENDING'
        )
    ) then
        return null;
    end if;
    return old;
end;
$$;

revoke all on function public.protect_learning_archive_pending_delete() from public, anon, authenticated;
grant execute on function public.protect_learning_archive_pending_delete() to service_role;
