# Mustard

A lightweight, Jira-inspired project & task tracker: **Streamlit** frontend,
**Supabase** (Postgres + Auth) backend.

Honest framing up front: this covers the core of Jira — projects, tasks with
sub-tasks, a kanban board, a personal task list, and per-user activity
reporting — in about a dozen files. It isn't a pixel-for-pixel or
feature-for-feature clone (no epics/sprints, drag-and-drop, or granular
permissions), but it's a real, working app you can extend.

## What it does

- **Projects** — create projects with a short key (e.g. `ENG`), add members.
- **Tasks & sub-tasks** — each task gets an auto-numbered key like `ENG-14`;
  sub-tasks nest under a parent task and get their own key.
- **Board** — kanban view per project (To Do / In Progress / In Review / Done),
  filterable by assignee.
- **My Tasks** — each person's own task list with quick status updates.
- **Reports** — pick any user and a date range, and see everything they did:
  tasks created, status changes, reassignments, priority changes, comments,
  and tasks completed — backed by a database trigger that logs every change,
  not just current state.

## Architecture

```
Streamlit pages  --->  db.py (all Supabase calls)  --->  Supabase (Postgres + Auth)
                                                              |
                                                     triggers write to
                                                     task_activity on every
                                                     insert/update, which is
                                                     what the Reports page reads
```

## File structure

```
jira-lite/
├── app.py                        # dashboard / entry point
├── auth.py                       # login & sign-up (Supabase Auth)
├── db.py                         # every database read/write lives here
├── utils.py                      # shared constants (statuses, priorities, icons)
├── requirements.txt
├── .gitignore
├── .streamlit/
│   ├── config.toml               # light theme
│   └── secrets.toml.example      # copy to secrets.toml and fill in
├── pages/
│   ├── 1_📁_Projects.py          # create/browse projects, tasks, sub-tasks, comments
│   ├── 2_🗂️_Board.py             # kanban board
│   ├── 3_✅_My_Tasks.py          # signed-in user's own tasks
│   └── 4_📊_Reports.py           # per-user activity for a date range
└── supabase/
    └── schema.sql                # tables, triggers, RLS — run once in Supabase
```

## 1. Set up Supabase

1. Create a free project at [supabase.com](https://supabase.com).
2. Open **SQL Editor** → New query → paste the entire contents of
   `supabase/schema.sql` → **Run**. This creates all tables, the task-key
   trigger, the activity-logging trigger, and RLS policies.
3. (Recommended for internal testing) Go to **Authentication → Providers →
   Email** and turn off "Confirm email" so people can sign up and use the app
   immediately without clicking an email link.
4. Go to **Settings → API** and copy the **Project URL** and the **anon
   public key** — you'll need both next.

## 2. Run it locally

```bash
git clone <your-repo-url>
cd jira-lite

python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt

cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# now edit .streamlit/secrets.toml and paste in your SUPABASE_URL and SUPABASE_KEY

streamlit run app.py
```

Sign up for an account in the app, then create your first project.

## 3. Make yourself an admin (optional)

The `role` column on `profiles` isn't heavily enforced in this MVP (everyone
can create projects and tasks — it's an internal tool), but it's there for
you to build on. To set someone as admin: Supabase → **Table Editor** →
`profiles` → edit their row → set `role` to `admin`.

## 4. Deploy to Streamlit Community Cloud

1. Push this repo to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app** →
   pick your repo, branch, and set the main file to `app.py`.
3. In the app's **Settings → Secrets**, paste the same two keys:
   ```toml
   SUPABASE_URL = "https://YOUR-PROJECT-REF.supabase.co"
   SUPABASE_KEY = "YOUR-ANON-PUBLIC-KEY"
   ```
4. Deploy. Share the URL with your team.

## Notes on the activity log (the "what did a user do" feature)

Every insert/update on `tasks` fires a Postgres trigger that writes a row to
`task_activity` (created, status change, reassignment, priority change, edits)
and comments fire a similar trigger. The Reports page just queries
`task_activity` for a user_id between two timestamps — so the report reflects
everything that actually happened, not just the task's current state.

## Extending it

- Restrict project/task creation to `role = 'admin'` in the RLS policies or in
  the page code.
- Add epics/sprints as another table with a `sprint_id` on `tasks`.
- Swap Streamlit's built-in bar charts for Plotly if you want richer report
  visuals.
