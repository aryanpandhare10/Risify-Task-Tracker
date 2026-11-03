# Jira-lite

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
├── app.py                        # entry point: login + role-based page navigation
├── auth.py                       # login & sign-up (Supabase Auth)
├── db.py                         # every database read/write lives here
├── utils.py                      # shared constants (statuses, priorities, icons)
├── notify.py                     # optional SMTP email reminders
├── requirements.txt
├── .gitignore
├── .streamlit/
│   ├── config.toml               # light theme
│   └── secrets.toml.example      # copy to secrets.toml and fill in
├── views/
│   ├── Dashboard.py              # overview, payment tracker, admin analytics
│   ├── Projects.py               # create/browse projects, tasks, sub-tasks, comments
│   ├── Board.py                  # kanban board
│   ├── My_Tasks.py               # signed-in user's own tasks
│   ├── Reports.py                # per-user activity for a date range
│   └── Compliance.py             # compliance tracker (admin + compliance roles)
└── supabase/
    ├── schema.sql                # tables, triggers, RLS — run once in Supabase
    ├── compliance.sql            # compliance tables, role, seed data — run after schema.sql
    ├── compliance_documents.sql  # file attachments for compliance items/entities — run after compliance.sql
    └── compliance_entity_fields.sql # company register fields (country, type, shareholders…) — run after compliance.sql
```

## Roles

| Role | Sees |
|---|---|
| `admin` | All project pages + Compliance + Audit |
| `member` | All project pages |
| `compliance` | Compliance page only |

Set a role in Supabase → Table Editor → `profiles` → `role`. Compliance data is
also locked to `admin`/`compliance` users in the database (RLS), not just hidden
in the UI.

### Compliance documents

Any compliance item or entity can have files attached (any type, up to 50 MB
each): open it from the Tracker or Entities tab → **📎 Documents**. Files are
stored in a **private** Supabase Storage bucket, `compliance-docs`, readable
only by `admin`/`compliance` users; download links expire after an hour. To
enable it, run `supabase/compliance_documents.sql` once (after `compliance.sql`).

### Audit documents (admin only)

The **Audit** page is a document repository: Insurance (from FY 22-23),
Mutual Funds and PMS (from FY 24-25), one folder per financial year (April to
March), with a new year added automatically every 1 April. Admins can add more
categories. Files are stored in **Google Drive**, not Supabase, under
`Risify Audit / <Category> / <FY>`, so storage is limited only by the Google
account, and Google Drive for desktop can sync everything to a PC.

One-time setup (about 10 minutes):

1. Go to [console.cloud.google.com](https://console.cloud.google.com), create
   a project (e.g. "Risify Portal").
2. **APIs & Services → Library** → enable **Google Drive API**.
3. **OAuth consent screen**: choose **Internal** if the account is on Google
   Workspace (e.g. @risify.ai). If you must choose External, set the
   publishing status to **In production** — in "Testing" Google expires the
   connection after 7 days.
4. **Credentials → Create credentials → OAuth client ID → Desktop app** →
   download the JSON file.
5. On your PC, run once and sign in with the Google account whose Drive
   should hold the documents:
   ```bash
   pip install google-auth-oauthlib
   python scripts/drive_auth.py path/to/client_secret.json
   ```
6. Paste the printed `[google_drive]` block at the **end** of the app's
   secrets (Streamlit Cloud: Manage app → Settings → Secrets).
7. Optional: install Google Drive for desktop on the PC; the **Risify Audit**
   folder then syncs there (choose "Mirror files" to keep local copies).

The app can only see files it created itself (`drive.file` permission), so
files dropped into the Drive folder by hand won't appear in the app — upload
through the Audit page. "Open in Drive" works for whoever has access to the
folder; the Download button works for every admin.

### Entity register

The Entities tab lists companies in register format (country, type, business
activity, incorporation date, years since incorporation, directors,
shareholders with paid-up capital and % holding), one row per director /
shareholder. **⬇️ Download Excel** exports it as an .xlsx whose Years column is
a formula, so it stays current. Run `supabase/compliance_entity_fields.sql`
once (after `compliance.sql`) to add these fields.

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
