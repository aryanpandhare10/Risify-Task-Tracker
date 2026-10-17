-- ============================================================
-- Compliance tracker: tables, access rules, and the starting data from
-- "Dubai Entities-Calender.xls". Run in Supabase: SQL Editor -> New query
-- -> paste -> Run. Safe to re-run: tables/policies are recreated only if
-- missing, and the seed data is inserted only while the tracker is empty.
-- ============================================================

-- ---------------------------------------------------------------
-- 1) New 'compliance' role (sees only the Compliance page)
-- ---------------------------------------------------------------
alter table profiles drop constraint if exists profiles_role_check;
alter table profiles add constraint profiles_role_check
  check (role in ('admin', 'member', 'compliance'));

-- Users may update their own profile row, but not their own role.
create or replace function prevent_self_role_change() returns trigger as $$
begin
  if new.role is distinct from old.role and auth.uid() = old.id then
    raise exception 'You cannot change your own role';
  end if;
  return new;
end;
$$ language plpgsql;

drop trigger if exists trg_prevent_self_role_change on profiles;
create trigger trg_prevent_self_role_change
before update on profiles
for each row execute function prevent_self_role_change();

-- True when the signed-in user is an admin or compliance user.
create or replace function is_compliance_user() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from profiles where id = auth.uid() and role in ('admin', 'compliance')
  );
$$;

-- ---------------------------------------------------------------
-- 2) Tables
-- ---------------------------------------------------------------
create table if not exists compliance_entities (
  id          uuid primary key default gen_random_uuid(),
  kind        text not null default 'company' check (kind in ('company', 'individual')),
  name        text not null,
  details     jsonb not null default '[]'::jsonb,   -- [{"field": "...", "value": "..."}]
  sort_order  int not null default 0,
  created_by  uuid references profiles(id),
  created_at  timestamptz not null default now()
);

create table if not exists compliance_items (
  id                 uuid primary key default gen_random_uuid(),
  entity_id          uuid not null references compliance_entities(id) on delete cascade,
  parent_id          uuid references compliance_items(id) on delete cascade,  -- set for sub-tasks
  category           text,
  particulars        text not null,
  frequency          text check (frequency in ('one_time','monthly','quarterly','half_yearly','annually',
                                               'every_2_years','every_3_years','every_5_years','every_10_years')),
  start_date         date,
  due_date           date,
  status             text not null default 'pending'
                     check (status in ('pending','in_progress','done','not_applicable')),
  reminder_days      int not null default 30 check (reminder_days >= 0),
  remarks            text,
  extra              jsonb not null default '[]'::jsonb,   -- [{"field": "...", "value": "..."}]
  last_done_on       date,
  reminder_sent_for  date,   -- due_date an email reminder was already sent for
  sort_order         int not null default 0,
  created_by         uuid references profiles(id),
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now()
);

create index if not exists idx_compliance_items_entity on compliance_items(entity_id);
create index if not exists idx_compliance_items_parent on compliance_items(parent_id);
create index if not exists idx_compliance_items_due on compliance_items(due_date);

-- ---------------------------------------------------------------
-- 3) Access: only admin + compliance users
-- ---------------------------------------------------------------
alter table compliance_entities enable row level security;
alter table compliance_items    enable row level security;

drop policy if exists "compliance_entities_all" on compliance_entities;
create policy "compliance_entities_all" on compliance_entities for all to authenticated
  using (is_compliance_user()) with check (is_compliance_user());

drop policy if exists "compliance_items_all" on compliance_items;
create policy "compliance_items_all" on compliance_items for all to authenticated
  using (is_compliance_user()) with check (is_compliance_user());

-- ---------------------------------------------------------------
-- 4) Starting data from "Dubai Entities-Calender.xls"
-- ---------------------------------------------------------------
do $$
declare
  difc uuid; a21 uuid; rcf uuid;
  p uuid;
begin
  if exists (select 1 from compliance_entities) then
    raise notice 'Compliance data already present - seed skipped.';
    return;
  end if;

  -- Companies (details from "Sheet3")
  insert into compliance_entities (kind, name, sort_order, details) values
    ('company', 'Analah (DIFC) Limited', 1, '[
      {"field":"Directors","value":"Hitesh Dhankani"},
      {"field":"Shareholders","value":"Hitesh Dhankani"},
      {"field":"% Holding","value":"100"},
      {"field":"Rate per share","value":"USD 1"},
      {"field":"Quantity","value":"710000"},
      {"field":"Incorporation date","value":"31.10.2021"},
      {"field":"License No.","value":""}]')
    returning id into difc;
  insert into compliance_entities (kind, name, sort_order, details) values
    ('company', 'Analah21 Real Estate Brokerage', 2, '[
      {"field":"Directors","value":"Shaifali Jain"},
      {"field":"Shareholders","value":"Shaifali Jain"},
      {"field":"% Holding","value":"100"},
      {"field":"Rate per share","value":"AED 1000"},
      {"field":"Quantity","value":"100000"},
      {"field":"Incorporation date","value":"23.12.2024"},
      {"field":"License No.","value":""}]')
    returning id into a21;
  insert into compliance_entities (kind, name, sort_order, details) values
    ('company', 'Risify Capital LLC FZ', 3, '[
      {"field":"Directors","value":"Shaifali Jain"},
      {"field":"Shareholders","value":"Shaifali Jain"},
      {"field":"% Holding","value":"100"},
      {"field":"Rate per share","value":"AED 1000"},
      {"field":"Quantity","value":"100000"},
      {"field":"Incorporation date","value":"07.03.2025"},
      {"field":"License No.","value":""}]')
    returning id into rcf;

  -- Company items ("Company Due Dates", gaps filled from "Sheet3")
  insert into compliance_items (entity_id, category, particulars, start_date, due_date, status, remarks, sort_order) values
    -- A. Documents
    (difc, 'Documents', 'PI Indemnity', null, '2027-02-25', 'pending', null, 1),
    (a21,  'Documents', 'PI Indemnity', null, null, 'not_applicable', 'Marked "-" in the source sheet', 1),
    (difc, 'Documents', 'Business License / Membership Certificate', null, '2026-10-30', 'pending', null, 2),
    (a21,  'Documents', 'Business License / Membership Certificate', null, '2025-12-22', 'pending', null, 2),
    (rcf,  'Documents', 'Business License / Membership Certificate', null, '2027-03-06', 'pending', null, 2),
    (difc, 'Documents', 'E-Establishment', null, '2026-10-30', 'pending', null, 3),
    (a21,  'Documents', 'E-Establishment', null, '2025-12-22', 'pending', null, 3),
    (a21,  'Documents', 'Rera Certificate / Real Estate office', '2024-12-16', '2025-12-15', 'pending', null, 4),
    (difc, 'Documents', 'Office Agreement', '2025-08-31', '2026-08-30', 'pending', null, 5),
    (rcf,  'Documents', 'Office Agreement', '2025-03-07', null, 'pending',
           'Check expiry: source sheet listed 06.03.2025, which is before the start date', 5),
    (a21,  'Documents', 'Tenancy Contract', '2024-12-16', '2025-12-15', 'pending', null, 6),
    (difc, 'Documents', 'Rent Due to DIFC investments - instalment 2', null, '2026-11-30', 'pending', null, 7),
    (difc, 'Documents', 'Rent Due to DIFC investments - instalment 3', null, '2027-02-28', 'pending', null, 8),
    (difc, 'Documents', 'Rent Due to DIFC investments - instalment 4', null, '2027-05-31', 'pending', null, 9),
    -- B. Compliances
    (difc, 'Compliances', 'Corporate tax Filing date', null, '2026-09-30', 'done', null, 20),
    (a21,  'Compliances', 'Corporate tax Filing date', null, '2026-09-30', 'done', null, 20),
    (rcf,  'Compliances', 'Corporate tax Filing date', null, '2026-09-30', 'done', null, 20),
    (difc, 'Compliances', 'FATCA & CRS', null, '2027-01-30', 'pending', null, 21),
    (difc, 'Compliances', 'DIFC Annual Financial Data', null, '2026-09-30', 'done', null, 22),
    (rcf,  'Compliances', 'VAT Mar to May', null, '2027-06-28', 'done', null, 23),
    (rcf,  'Compliances', 'VAT Jun to Aug', null, '2026-09-28', 'done', null, 24),
    (rcf,  'Compliances', 'VAT Sept to Nov', null, '2026-12-28', 'pending', null, 25),
    (rcf,  'Compliances', 'VAT Dec to Feb', null, '2027-03-28', 'pending', null, 26),
    (difc, 'Compliances', 'FATCA & CRS MOF', null, null, 'pending', null, 27),
    (a21,  'Compliances', 'FATCA & CRS MOF', null, null, 'pending', null, 27),
    (rcf,  'Compliances', 'FATCA & CRS MOF', null, null, 'pending', null, 27),
    (difc, 'Compliances', 'PIB - Q1 Jan to Mar', null, '2026-04-30', 'pending', null, 28),
    (difc, 'Compliances', 'PIB - Q2 Apr to June', null, '2026-07-31', 'pending', null, 29),
    (difc, 'Compliances', 'PIB - Q3 July to Sept', null, '2026-10-31', 'pending', null, 30),
    (difc, 'Compliances', 'PIB - Q4 Oct to Dec', null, '2027-03-31', 'pending', null, 31);

  -- Individuals ("Individual" sheet): 4 personal documents each
  insert into compliance_entities (kind, name, sort_order, details)
    values ('individual', 'Hitesh Dhankani', 1, '[{"field":"Employee of","value":""}]') returning id into p;
  insert into compliance_items (entity_id, category, particulars, start_date, due_date, sort_order) values
    (p, 'Personal documents', 'Insurance Card',   '2026-09-03', '2027-09-02', 1),
    (p, 'Personal documents', 'Visa',             '2024-12-22', '2026-12-21', 2),
    (p, 'Personal documents', 'Emirates ID',      null, null, 3),
    (p, 'Personal documents', 'Tenancy Contract', null, null, 4);

  insert into compliance_entities (kind, name, sort_order, details)
    values ('individual', 'Vaishali Dhankani', 2, '[{"field":"Employee of","value":""}]') returning id into p;
  insert into compliance_items (entity_id, category, particulars, start_date, due_date, sort_order) values
    (p, 'Personal documents', 'Insurance Card',   '2026-09-03', '2027-09-02', 1),
    (p, 'Personal documents', 'Visa',             '2025-01-31', '2035-01-30', 2),
    (p, 'Personal documents', 'Emirates ID',      null, null, 3),
    (p, 'Personal documents', 'Tenancy Contract', null, null, 4);

  insert into compliance_entities (kind, name, sort_order, details)
    values ('individual', 'Mihir Dhankani', 3, '[{"field":"Employee of","value":""}]') returning id into p;
  insert into compliance_items (entity_id, category, particulars, start_date, due_date, sort_order) values
    (p, 'Personal documents', 'Insurance Card',   '2026-09-03', '2027-09-02', 1),
    (p, 'Personal documents', 'Visa',             null, null, 2),
    (p, 'Personal documents', 'Emirates ID',      null, null, 3),
    (p, 'Personal documents', 'Tenancy Contract', null, null, 4);

  insert into compliance_entities (kind, name, sort_order, details)
    values ('individual', 'Dakshayani Dhankani', 4, '[{"field":"Employee of","value":""}]') returning id into p;
  insert into compliance_items (entity_id, category, particulars, start_date, due_date, sort_order) values
    (p, 'Personal documents', 'Insurance Card',   '2026-09-03', '2027-09-02', 1),
    (p, 'Personal documents', 'Visa',             '2025-04-23', '2035-04-22', 2),
    (p, 'Personal documents', 'Emirates ID',      null, null, 3),
    (p, 'Personal documents', 'Tenancy Contract', null, null, 4);

  insert into compliance_entities (kind, name, sort_order, details)
    values ('individual', 'Shefali Pradeep Jain', 5, '[{"field":"Employee of","value":"Risify Capital LLP"}]') returning id into p;
  insert into compliance_items (entity_id, category, particulars, start_date, due_date, remarks, sort_order) values
    (p, 'Personal documents', 'Insurance Card',   '2025-06-05', '2026-06-04', null, 1),
    (p, 'Personal documents', 'Visa',             '2025-01-24', '2035-01-23', null, 2),
    (p, 'Personal documents', 'Emirates ID',      '2025-01-24', '2035-01-23', null, 3),
    (p, 'Personal documents', 'Tenancy Contract', '2025-11-06', '2026-11-05',
        'Analah Prime Tower agreement expiry 05.11.2026', 4);

  insert into compliance_entities (kind, name, sort_order, details)
    values ('individual', 'Roshen', 6, '[{"field":"Employee of","value":"Analah DIFC"}]') returning id into p;
  insert into compliance_items (entity_id, category, particulars, start_date, due_date, sort_order) values
    (p, 'Personal documents', 'Insurance Card',   '2026-09-03', '2027-09-02', 1),
    (p, 'Personal documents', 'Visa',             null, null, 2),
    (p, 'Personal documents', 'Emirates ID',      null, null, 3),
    (p, 'Personal documents', 'Tenancy Contract', null, null, 4);
end $$;

-- ---------------------------------------------------------------
-- 5) Varsha's profile. FIRST create her login in Supabase:
--    Authentication -> Users -> Add user -> Create new user
--    (email varsha@analahcapital.com, her password, tick "Auto Confirm User").
--    Then run this. (If her login doesn't exist yet, this does nothing.)
-- ---------------------------------------------------------------
insert into profiles (id, email, full_name, role)
select id, email, 'Varsha', 'compliance'
from auth.users
where email = 'varsha@analahcapital.com'
on conflict (id) do update set role = 'compliance', full_name = 'Varsha';
