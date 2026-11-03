-- ============================================================
-- Compliance documents: files attached to compliance items or entities.
-- Run AFTER compliance.sql, in Supabase: SQL Editor -> New query -> paste
-- -> Run. Safe to re-run.
--
-- Files live in a PRIVATE Storage bucket ("compliance-docs"); this table
-- holds one row per file (original name, size, who uploaded it). Both are
-- locked to admin + compliance users, same as the tracker itself.
-- ============================================================

-- ---------------------------------------------------------------
-- 1) Table
-- ---------------------------------------------------------------
create table if not exists compliance_documents (
  id            uuid primary key default gen_random_uuid(),
  item_id       uuid references compliance_items(id) on delete cascade,
  entity_id     uuid references compliance_entities(id) on delete cascade,
  file_name     text not null,                 -- original name, shown to users
  storage_path  text not null unique,          -- key inside the compliance-docs bucket
  content_type  text,
  size_bytes    bigint,
  uploaded_by   uuid references profiles(id),
  created_at    timestamptz not null default now(),
  -- attached to exactly one of: an item, or an entity
  constraint compliance_documents_one_owner check ((item_id is null) <> (entity_id is null))
);

create index if not exists idx_compliance_documents_item on compliance_documents(item_id);
create index if not exists idx_compliance_documents_entity on compliance_documents(entity_id);

alter table compliance_documents enable row level security;

drop policy if exists "compliance_documents_all" on compliance_documents;
create policy "compliance_documents_all" on compliance_documents for all to authenticated
  using (is_compliance_user()) with check (is_compliance_user());

-- ---------------------------------------------------------------
-- 2) Private storage bucket (50 MB per file = the Free plan maximum)
-- ---------------------------------------------------------------
insert into storage.buckets (id, name, public, file_size_limit)
values ('compliance-docs', 'compliance-docs', false, 52428800)
on conflict (id) do update set public = false;

drop policy if exists "compliance_docs_select" on storage.objects;
create policy "compliance_docs_select" on storage.objects for select to authenticated
  using (bucket_id = 'compliance-docs' and public.is_compliance_user());

drop policy if exists "compliance_docs_insert" on storage.objects;
create policy "compliance_docs_insert" on storage.objects for insert to authenticated
  with check (bucket_id = 'compliance-docs' and public.is_compliance_user());

drop policy if exists "compliance_docs_delete" on storage.objects;
create policy "compliance_docs_delete" on storage.objects for delete to authenticated
  using (bucket_id = 'compliance-docs' and public.is_compliance_user());

-- Make the API see the new table right away.
notify pgrst, 'reload schema';
