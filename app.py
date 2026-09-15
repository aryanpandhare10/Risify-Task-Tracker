import pandas as pd
import streamlit as st

from auth import require_login, logout_button
from db import list_projects, list_tasks, list_profiles, update_project
import utils

st.set_page_config(page_title="Mustard", page_icon="🔷", layout="wide")

profile = require_login()
is_admin = profile["role"] == "admin"

st.sidebar.title("🔷 Risify Task Tracker")
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

all_profiles = list_profiles()
id_to_name = {pr["id"]: pr["full_name"] for pr in all_profiles}
name_to_id = {v: k for k, v in id_to_name.items()}

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

        owner_options = ["Unassigned"] + list(name_to_id.keys())
        current_owner_name = id_to_name.get(p.get("lead_id"), "Unassigned")

        ocol1, ocol2, ocol3, ocol4 = st.columns([2, 2, 2, 1])
        new_owner_name = ocol1.selectbox(
            "Primary owner", owner_options,
            index=owner_options.index(current_owner_name)
            if current_owner_name in owner_options else 0,
            key=f"owner_{p['id']}",
        )
        new_completion = ocol2.text_input(
            "Completion date", value=p.get("completion_date") or "",
            key=f"completion_{p['id']}",
        )
        new_priority = ocol3.selectbox(
            "Priority", utils.PRIORITY_OPTIONS,
            index=utils.PRIORITY_OPTIONS.index(p.get("priority") or "medium"),
            format_func=lambda x: f"{utils.PRIORITY_ICONS.get(x, '')} {x.title()}",
            key=f"priority_{p['id']}",
        )
        ocol4.write("")
        ocol4.write("")
        if ocol4.button("💾", key=f"save_proj_{p['id']}", help="Save"):
            update_project(
                p["id"],
                lead_id=name_to_id.get(new_owner_name),
                completion_date=new_completion,
                priority=new_priority,
            )
            st.rerun()

# =====================================================================
# Admin analytics — project & people level view. Admins don't add tasks
# here; this is purely an oversight view of who's doing what and how
# much progress each project/person has made.
# =====================================================================
if is_admin:
    st.divider()
    st.header("📊 Admin analytics")

    st.subheader("Project overview")
    overview_rows = []
    for p in projects:
        prog = utils.project_progress(tasks_by_project[p["id"]])
        overview_rows.append({
            "Project": f"{p['key']} — {p['name']}",
            "Owner": id_to_name.get(p.get("lead_id"), "Unassigned"),
            "Priority": (p.get("priority") or "medium").title(),
            "Target completion": p.get("completion_date") or "—",
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

        root_tasks = [t for t in proj_tasks if not t.get("parent_id")]
        subtasks_by_parent: dict = {}
        for t in proj_tasks:
            pid = t.get("parent_id")
            if pid:
                subtasks_by_parent.setdefault(pid, []).append(t)

        with st.expander(f"{p['key']} — {p['name']} ({len(root_tasks)} task(s))"):
            person_rows = utils.per_assignee_progress(proj_tasks, id_to_name)
            person_df = pd.DataFrame([{
                "Person": r["name"],
                "Tasks assigned": r["total_tasks"],
                "Tasks done": r["done_tasks"],
                "Task completion %": round(r["task_pct"], 1),
                "Hours estimated": round(r["total_hours"], 1),
                "Hours logged": round(r["logged_hours"], 1),
                "Hours completion %": round(r["hours_pct"], 1),
            } for r in person_rows])
            st.dataframe(person_df, use_container_width=True, hide_index=True)

            st.caption("All tasks in this project")

            status_filter = utils.checkbox_filter(
                st, "Filter by status", utils.STATUS_OPTIONS,
                key_prefix=f"status_filter_{p['id']}",
                format_func=lambda s: utils.STATUS_LABELS.get(s, s),
            )
            assignee_choices = sorted({
                id_to_name.get(t.get("assignee_id"), "Unassigned") for t in root_tasks
            })
            assignee_filter = utils.checkbox_filter(
                st, "Filter by assigned to", assignee_choices,
                key_prefix=f"assignee_filter_{p['id']}",
            )

            st.caption("Filter by due date range")
            dcol1, dcol2 = st.columns(2)
            due_from = dcol1.date_input("From", value=None, key=f"due_from_{p['id']}")
            due_to = dcol2.date_input("To", value=None, key=f"due_to_{p['id']}")

            filtered_roots = [
                t for t in root_tasks
                if t["status"] in status_filter
                and id_to_name.get(t.get("assignee_id"), "Unassigned") in assignee_filter
            ]
            if due_from and due_to:
                filtered_roots = [
                    t for t in filtered_roots
                    if t.get("due_date") and due_from.isoformat() <= t["due_date"] <= due_to.isoformat()
                ]

            if not filtered_roots:
                st.caption("No tasks match the filters.")

            header = st.columns([2, 3, 2, 1.5, 1.5, 1.5])
            for col, label in zip(
                header, ["Title", "Description", "Assigned to", "Status", "Due date", "Hours (logged/est.)"]
            ):
                col.markdown(f"**{label}**")

            for t in filtered_roots:
                subtasks = subtasks_by_parent.get(t["id"], [])
                own_est = float(t.get("estimate_hours") or 0)
                own_logged = float(t.get("logged_hours") or 0)
                sub_est = sum(float(s.get("estimate_hours") or 0) for s in subtasks)
                sub_logged = sum(float(s.get("logged_hours") or 0) for s in subtasks)
                total_est = own_est + sub_est
                total_logged = own_logged + sub_logged

                full_desc = t.get("description") or "—"

                row = st.columns([2, 3, 2, 1.5, 1.5, 1.5])
                row[0].write(t["title"])
                with row[1]:
                    if len(full_desc) > 40:
                        with st.popover(full_desc[:37] + "..."):
                            st.write(full_desc)
                    else:
                        st.write(full_desc)
                row[2].write(id_to_name.get(t.get("assignee_id"), "Unassigned"))
                row[3].write(utils.STATUS_LABELS.get(t["status"], t["status"]))
                row[4].write(t.get("due_date") or "—")
                row[5].write(f"{total_logged:g}/{total_est:g}h")

                if subtasks:
                    with st.expander(f"▸ {len(subtasks)} sub-task(s)", expanded=False):
                        sub_df = pd.DataFrame([{
                            "Sub-task": s["title"],
                            "Assigned to": id_to_name.get(s.get("assignee_id"), "Unassigned"),
                            "Status": utils.STATUS_LABELS.get(s["status"], s["status"]),
                            "Due date": s.get("due_date") or "—",
                            "Est. hours": s.get("estimate_hours") or 0,
                            "Logged hours": s.get("logged_hours") or 0,
                        } for s in subtasks])
                        st.dataframe(sub_df, use_container_width=True, hide_index=True)

st.caption(
    "Use the pages in the left sidebar: **Projects** to create work, "
    "**Board** for a kanban view, **My Tasks** for your own list, "
    "and **Reports** to see what anyone did over a date range."
)
