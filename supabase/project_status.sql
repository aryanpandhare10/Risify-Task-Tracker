-- ============================================================
-- Project status: admins can mark a project Completed (and reopen it)
-- from the Dashboard's Project overview. Run in Supabase: SQL Editor ->
-- New query -> paste -> Run. Safe to re-run.
-- ============================================================
alter table projects add column if not exists status text not null default 'active';
alter table projects drop constraint if exists projects_status_check;
alter table projects add constraint projects_status_check check (status in ('active', 'completed'));
alter table projects add column if not exists completed_on date;   -- set when marked completed

-- Make the API see the new columns right away.
notify pgrst, 'reload schema';
