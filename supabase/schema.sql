-- ============================================================
-- Jira-lite schema for Supabase (Postgres)
-- Run this once in Supabase: Dashboard -> SQL Editor -> New query -> paste -> Run
-- ============================================================

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------
-- PROFILES (mirrors auth.users, holds app-level fields)
-- ---------------------------------------------------------------
create table if not exists profiles (
  id          uuid primary key references auth.users(id) on delete cascade,
  email       text unique not null,
  full_name   text not null,
  role        text not null default 'member' check (role in ('admin', 'member')),
  created_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------
-- PROJECTS
-- ---------------------------------------------------------------
create table if not exists projects (
  id                 uuid primary key default gen_random_uuid(),
  key                text unique not null,          -- e.g. "ENG"
  name               text not null,
  description        text,
  lead_id            uuid references profiles(id),
  created_by         uuid references profiles(id),
  next_task_number   int not null default 1,        -- used to mint task_key values
  created_at         timestamptz not null default now()
);

create table if not exists project_members (
  project_id  uuid references projects(id) on delete cascade,
  user_id     uuid references profiles(id) on delete cascade,
  role        text not null default 'member',
  primary key (project_id, user_id)
);

-- ---------------------------------------------------------------
-- TASKS (also holds sub-tasks via parent_id self-reference)
-- ---------------------------------------------------------------
create table if not exists tasks (
  id            uuid primary key default gen_random_uuid(),
  project_id    uuid not null references projects(id) on delete cascade,
  parent_id     uuid references tasks(id) on delete cascade,
  task_key      text unique,                        -- e.g. "ENG-14", set by trigger
  title         text not null,
  description   text,
  issue_type    text not null default 'task' check (issue_type in ('task','subtask','bug','story')),
  status        text not null default 'todo' check (status in ('todo','in_progress','in_review','done')),
  priority      text not null default 'medium' check (priority in ('lowest','low','medium','high','highest')),
  assignee_id   uuid references profiles(id),
  reporter_id   uuid not null references profiles(id),
  updated_by    uuid references profiles(id),        -- app sets this on every write; triggers use it as "actor"
  due_date      date,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  completed_at  timestamptz
);

create index if not exists idx_tasks_project on tasks(project_id);
create index if not exists idx_tasks_assignee on tasks(assignee_id);
create index if not exists idx_tasks_parent on tasks(parent_id);

-- ---------------------------------------------------------------
-- TASK_ACTIVITY - audit log that powers the "what did a user do" report
-- ---------------------------------------------------------------
create table if not exists task_activity (
  id          uuid primary key default gen_random_uuid(),
  task_id     uuid references tasks(id) on delete cascade,
  project_id  uuid references projects(id) on delete cascade,
  user_id     uuid not null references profiles(id),
  action      text not null,   -- created | status_changed | assigned | priority_changed | updated | completed | commented
  field_name  text,
  old_value   text,
  new_value   text,
  created_at  timestamptz not null default now()
);

create index if not exists idx_activity_user_time on task_activity(user_id, created_at);

-- ---------------------------------------------------------------
-- COMMENTS
-- ---------------------------------------------------------------
create table if not exists comments (
  id          uuid primary key default gen_random_uuid(),
  task_id     uuid not null references tasks(id) on delete cascade,
  user_id     uuid not null references profiles(id),
  body        text not null,
  created_at  timestamptz not null default now()
);

-- ============================================================
-- TRIGGERS
-- ============================================================

-- 1) Auto-generate a per-project task key like "ENG-1", "ENG-2", ...
create or replace function generate_task_key() returns trigger as $$
declare
  proj_key text;
  next_num int;
begin
  select key, next_task_number into proj_key, next_num
  from projects where id = new.project_id
  for update;

  new.task_key := proj_key || '-' || next_num;

  update projects set next_task_number = next_num + 1 where id = new.project_id;
  return new;
end;
$$ language plpgsql;

drop trigger if exists trg_1_generate_task_key on tasks;
create trigger trg_1_generate_task_key
before insert on tasks
for each row execute function generate_task_key();

-- 2) Log every create / status / assignee / priority / content change to task_activity,
--    and stamp completed_at automatically when status becomes 'done'.
create or replace function log_task_activity() returns trigger as $$
declare
  actor uuid;
begin
  actor := coalesce(new.updated_by, new.reporter_id);
  new.updated_at := now();

  if tg_op = 'INSERT' then
    insert into task_activity (task_id, project_id, user_id, action, new_value)
    values (new.id, new.project_id, actor, 'created', new.title);
    return new;
  end if;

  if tg_op = 'UPDATE' then
    if old.status is distinct from new.status then
      insert into task_activity (task_id, project_id, user_id, action, field_name, old_value, new_value)
      values (new.id, new.project_id, actor, 'status_changed', 'status', old.status, new.status);
      if new.status = 'done' and new.completed_at is null then
        new.completed_at := now();
      elsif new.status <> 'done' then
        new.completed_at := null;
      end if;
    end if;

    if old.assignee_id is distinct from new.assignee_id then
      insert into task_activity (task_id, project_id, user_id, action, field_name, old_value, new_value)
      values (new.id, new.project_id, actor, 'assigned', 'assignee_id',
              old.assignee_id::text, new.assignee_id::text);
    end if;

    if old.priority is distinct from new.priority then
      insert into task_activity (task_id, project_id, user_id, action, field_name, old_value, new_value)
      values (new.id, new.project_id, actor, 'priority_changed', 'priority', old.priority, new.priority);
    end if;

    if old.title is distinct from new.title or old.description is distinct from new.description then
      insert into task_activity (task_id, project_id, user_id, action, field_name)
      values (new.id, new.project_id, actor, 'updated', 'title/description');
    end if;

    return new;
  end if;
end;
$$ language plpgsql;

drop trigger if exists trg_2_log_task_activity on tasks;
create trigger trg_2_log_task_activity
before insert or update on tasks
for each row execute function log_task_activity();

-- 3) Log comments as activity too
create or replace function log_comment_activity() returns trigger as $$
begin
  insert into task_activity (task_id, project_id, user_id, action, new_value)
  select new.task_id, t.project_id, new.user_id, 'commented', new.body
  from tasks t where t.id = new.task_id;
  return new;
end;
$$ language plpgsql;

drop trigger if exists trg_log_comment_activity on comments;
create trigger trg_log_comment_activity
after insert on comments
for each row execute function log_comment_activity();

-- ============================================================
-- ROW LEVEL SECURITY
-- This is an internal tool used by a trusted, logged-in team, so policies are
-- intentionally permissive: any authenticated user can read/write. Tighten
-- later (e.g. restrict project creation to admins) if needed.
-- ============================================================

alter table profiles       enable row level security;
alter table projects       enable row level security;
alter table project_members enable row level security;
alter table tasks          enable row level security;
alter table task_activity  enable row level security;
alter table comments       enable row level security;

create policy "profiles_select" on profiles for select to authenticated using (true);
create policy "profiles_insert_self" on profiles for insert to authenticated with check (auth.uid() = id);
create policy "profiles_update_self" on profiles for update to authenticated using (auth.uid() = id);

create policy "projects_all" on projects for all to authenticated using (true) with check (true);
create policy "project_members_all" on project_members for all to authenticated using (true) with check (true);
create policy "tasks_all" on tasks for all to authenticated using (true) with check (true);
create policy "task_activity_select" on task_activity for select to authenticated using (true);
create policy "task_activity_insert" on task_activity for insert to authenticated with check (true);
create policy "comments_all" on comments for all to authenticated using (true) with check (true);
