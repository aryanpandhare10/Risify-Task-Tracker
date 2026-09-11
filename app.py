import pandas as pd
import streamlit as st

from auth import require_login, logout_button
from db import list_projects, list_tasks, list_profiles
import utils

st.set_page_config(page_title="Jira-lite", page_icon="🔷", layout="wide")

profile = require_login()
is_admin = profile["role"] == "admin"

st.sidebar.title("🔷 Jira-lite")
st.sidebar.write(f"Signed in as **{profile['full_name']}**")
st.sidebar.caption(profile["role"].title())
logout_button()

st.title("Dashboard")

projects = list_projects()
my_tasks = list_tasks(assignee_id=profile["id"])

col1, col2, col3 = st.columns(3)
col1.metric("Projects", len(projects))
col2.metric("My open tasks", len([t for t in my_tasks if t["status"] != "done"]))
col3.metric("My completed tasks", len([t for t in my_tasks if t["status"] == "done"]))

st.divider()
st.subheader("All projects")

if not projects:
    st.info("No projects yet. Open **Projects** in the sidebar to create one.")
    st.stop()

# Fetch every project's tasks once and reuse below (progress cards + admin analytics).
tasks_by_project = {p["id"]: list_tasks(project_id=p["id"]) for p in projects}

for p in projects:
    prog = utils.project_progress(tasks_by_project[p["id"]])
    with st.container(border=True):
        st.markdown(f"**{p['key']}** — {p['name']}")
        st.caption(p.get("description") or "No description")

        pcol1, pcol2 = st.columns(2)
        with pcol1:
            st.progress(
                min(int(prog["task_pct"]), 100),
                text=f"Tasks: {prog['done_tasks']}/{prog['total_tasks']} done "
                f"({prog['task_pct']:.0f}%)",
            )
        with pcol2:
            st.progress(
                min(int(prog["hours_pct"]), 100),
                text=f"Hours: {prog['logged_hours']:.1f}/{prog['total_hours']:.1f} logged "
                f"({prog['hours_pct']:.0f}%)",
            )

# =====================================================================
# Admin analytics — project & people level view. Admins don't add tasks
# here; this is purely an oversight view of who's doing what and how
# much progress each project/person has made.
# =====================================================================
if is_admin:
    st.divider()
    st.header("📊 Admin analytics")

    all_profiles = list_profiles()
    id_to_name = {pr["id"]: pr["full_name"] for pr in all_profiles}

    st.subheader("Project overview")
    overview_rows = []
    for p in projects:
        prog = utils.project_progress(tasks_by_project[p["id"]])
        overview_rows.append({
            "Project": f"{p['key']} — {p['name']}",
            "Tasks done": f"{prog['done_tasks']}/{prog['total_tasks']}",
            "Task completion %": round(prog["task_pct"], 1),
            "Hours logged": f"{prog['logged_hours']:.1f}/{prog['total_hours']:.1f}",
            "Hours completion %": round(prog["hours_pct"], 1),
        })
    st.dataframe(pd.DataFrame(overview_rows), use_container_width=True, hide_index=True)

    st.subheader("Team overview (across all projects)")
    all_tasks = [t for ts in tasks_by_project.values() for t in ts]
    team_rows = utils.per_assignee_progress(all_tasks, id_to_name)
    team_df = pd.DataFrame([{
        "Person": r["name"],
        "Tasks assigned": r["total_tasks"],
        "Tasks done": r["done_tasks"],
        "Task completion %": round(r["task_pct"], 1),
        "Hours estimated": round(r["total_hours"], 1),
        "Hours logged": round(r["logged_hours"], 1),
        "Hours completion %": round(r["hours_pct"], 1),
    } for r in team_rows])
    st.dataframe(team_df, use_container_width=True, hide_index=True)

    st.subheader("Per-project breakdown")
    for p in projects:
        proj_tasks = tasks_by_project[p["id"]]
        if not proj_tasks:
            continue
        with st.expander(f"{p['key']} — {p['name']} ({len(proj_tasks)} task(s))"):
            person_rows = utils.per_assignee_progress(proj_tasks, id_to_name)
            person_df = pd.DataFrame([{
                "Person": r["name"],
                "Tasks assigned": r["total_tasks"],
                "Tasks done": r["done_tasks"],
                "Task completion %": round(r["task_pct"], 1),
                "Hours estimated": round(r["total_hours"], 1),
                "Hours completed": round(r["done_hours"], 1),
                "Hours completion %": round(r["hours_pct"], 1),
            } for r in person_rows])
            st.dataframe(person_df, use_container_width=True, hide_index=True)

            st.caption("All tasks in this project")
            task_df = pd.DataFrame([{
                "Key": t["task_key"],
                "Title": t["title"],
                "Assignee": id_to_name.get(t.get("assignee_id"), "Unassigned"),
                "Status": utils.STATUS_LABELS.get(t["status"], t["status"]),
                "Est. hours": t.get("estimate_hours") or 0,
                "Logged hours": t.get("logged_hours") or 0,
            } for t in sorted(proj_tasks, key=lambda t: id_to_name.get(t.get("assignee_id"), "Unassigned"))])
            st.dataframe(task_df, use_container_width=True, hide_index=True)

st.caption(
    "Use the pages in the left sidebar: **Projects** to create work, "
    "**Board** for a kanban view, **My Tasks** for your own list, "
    "and **Reports** to see what anyone did over a date range."
)
