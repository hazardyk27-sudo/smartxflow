-- Defense-in-depth for Learning Archive source-history retention.
-- Any row belonging to a PENDING archive case is protected even if an old
-- application cleanup path runs before the new runtime guard is deployed.

create or replace function public.protect_learning_archive_pending_delete()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    if old.match_id_hash is not null and exists (
        select 1
        from public.learning_archive_retention_holds h
        where h.match_id_hash = old.match_id_hash
          and h.status = 'PENDING'
    ) then
        return null;
    end if;
    return old;
end;
$$;

revoke all on function public.protect_learning_archive_pending_delete() from public, anon, authenticated;
grant execute on function public.protect_learning_archive_pending_delete() to service_role;

do $$
declare
    table_name text;
    trigger_name text;
begin
    foreach table_name in array array[
        'fixtures',
        'moneyway_1x2_history',
        'moneyway_ou25_history',
        'moneyway_btts_history',
        'moneyway_draw_no_bet_history',
        'dropping_1x2_history',
        'dropping_ou25_history',
        'dropping_btts_history',
        'moneyway_snapshots'
    ] loop
        if to_regclass('public.' || table_name) is null then
            continue;
        end if;
        trigger_name := 'protect_learning_archive_delete_' || table_name;
        execute format('drop trigger if exists %I on public.%I', trigger_name, table_name);
        execute format(
            'create trigger %I before delete on public.%I for each row execute function public.protect_learning_archive_pending_delete()',
            trigger_name,
            table_name
        );
    end loop;
end
$$;
