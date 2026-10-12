import datetime as dt

import pandas as pd
import streamlit as st

from auth import require_login, logout_button
from db import (
    list_projects, list_tasks, list_profiles, update_project,
    list_licenses, create_license, update_license, delete_license,
)
import notify
import utils

st.set_page_config(page_title="Jira-lite", page_icon="🔷", layout="wide")

profile = require_login()
is_admin = profile["role"] == "admin"

st.sidebar.title("🔷 Risify Task Tracker")
st.sidebar.write(f"Signed in as **{profile['full_name']}**")
st.sidebar.caption(profile["role"].title())
logout_button()

st.title("Dashboard")

# License reminders — anything expired or expiring within a week is flagged
# here on every dashboard load, and emailed once (if SMTP is configured).
licenses = list_licenses()
for lic in licenses:
    cat = utils.license_category(lic)
    if cat == "active":
        continue
    days = utils.license_days_left(lic)
    label = lic["name"] + (f" ({lic['vendor']})" if lic.get("vendor") else "")
    if cat == "expired":
        st.error(f"🔑 License **{label}** expired on {lic['expiry_date']} ({-days} day(s) ago).")
    else:
        when = "today" if days == 0 else f"in {days} day(s)"
        st.warning(f"🔑 License **{label}** expires {when} ({lic['expiry_date']}).")
notify.send_license_reminders(licenses)

projects = list_projects()

if not projects:
    st.info("No projects yet. Open **Projects** in the sidebar to create one.")
    st.stop()

all_profiles = list_profiles()
id_to_name = {pr["id"]: pr["full_name"] for pr in all_profiles}
name_to_id = {v: k for k, v in id_to_name.items()}

# Fetch every project's tasks once and reuse below (overview, progress cards + admin analytics).
tasks_by_project = {p["id"]: list_tasks(project_id=p["id"]) for p in projects}

# =====================================================================
# Project overview — shown first. Click a project row to list its main
# tasks below (sub-tasks excluded), with the date and status coloured by
# category: default = In Progress, green = Completed, red = Overdue.
# =====================================================================
st.subheader("📋 Project overview")
today = dt.date.today()

overview_rows = []
for p in projects:
    prog = utils.project_progress(tasks_by_project[p["id"]], rollup=True)
    overview_rows.append({
        "Project": f"{p['key']} — {p['name']}",
        "Owner": id_to_name.get(p.get("lead_id"), "Unassigned"),
        "Priority": (p.get("priority") or "medium").title(),
        "Next task completion": p.get("completion_date") or "—",
        "Project completion": p.get("project_completion_date") or "—",
        "Tasks done": f"{prog['done_tasks']}/{prog['total_tasks']}",
        "Task completion %": round(prog["task_pct"], 1),
        "Hours logged": f"{prog['logged_hours']:.1f}/{prog['total_hours']:.1f}",
        "Hours completion %": round(prog["hours_pct"], 1),
    })

overview_event = st.dataframe(
    pd.DataFrame(overview_rows), use_container_width=True, hide_index=True,
    on_select="rerun", selection_mode="single-row", key="project_overview",
)
selected_rows = overview_event.selection.rows

if not selected_rows:
    st.caption("Click a project row to see its main tasks.")
else:
    sel = projects[selected_rows[0]]
    main_tasks = sorted(
        [t for t in tasks_by_project[sel["id"]] if not t.get("parent_id")],
        key=lambda t: (t.get("due_date") is None, t.get("due_date") or ""),
    )
    st.markdown(f"**Main tasks — {sel['key']} — {sel['name']}**")
    if not main_tasks:
        st.caption("No tasks in this project yet.")
    else:
        categories = [utils.task_category(t, today) for t in main_tasks]
        tasks_df = pd.DataFrame([{
            "Task": t["title"],
            "Due / Completed": utils.task_date_label(t),
            "Status": utils.STATUS_LABELS.get(t["status"], t["status"]),
        } for t in main_tasks])

        def _category_colors(col: pd.Series) -> list:
            return [
                f"color: {utils.TASK_CATEGORY_COLORS[c]}" if utils.TASK_CATEGORY_COLORS[c] else ""
                for c in categories
            ]

        st.dataframe(
            tasks_df.style.apply(_category_colors, subset=["Due / Completed", "Status"]),
            use_container_width=True, hide_index=True,
        )

# =====================================================================
# License expiry — manually maintained list of licenses and their next
# expiry date. Orange = expiring within a week, red = expired.
# =====================================================================
st.subheader("🔑 License Expiry")

if not licenses:
    st.caption("No licenses tracked yet. Add one below.")
else:
    license_categories = [utils.license_category(lic, today) for lic in licenses]
    licenses_df = pd.DataFrame([{
        "License": lic["name"],
        "Vendor": lic.get("vendor") or "—",
        "Expiry date": lic["expiry_date"],
        "Days left": utils.license_days_left(lic, today),
        "Notes": lic.get("notes") or "",
    } for lic in licenses])

    def _license_colors(col: pd.Series) -> list:
        return [
            f"color: {utils.LICENSE_CATEGORY_COLORS[c]}" if utils.LICENSE_CATEGORY_COLORS[c] else ""
            for c in license_categories
        ]

    st.dataframe(
        licenses_df.style.apply(_license_colors, subset=["Expiry date", "Days left"]),
        use_container_width=True, hide_index=True,
    )

with st.expander("➕ Add / edit licenses"):
    with st.form("new_license", clear_on_submit=True):
        lcol1, lcol2, lcol3 = st.columns(3)
        lic_name = lcol1.text_input("License name")
        lic_vendor = lcol2.text_input("Vendor (optional)")
        lic_expiry = lcol3.date_input("Next expiry date", value=None)
        lic_notes = st.text_input("Notes (optional)")
        lic_submitted = st.form_submit_button("Add license")
    if lic_submitted:
        if not lic_name or not lic_expiry:
            st.error("License name and expiry date are required.")
        else:
            create_license(lic_name, lic_vendor, lic_expiry.isoformat(), lic_notes, profile["id"])
            st.rerun()

    if licenses:
        st.divider()
        lic_by_label = {
            f"{lic['name']} — {lic['expiry_date']}": lic for lic in licenses
        }
        edit_label = st.selectbox("Edit an existing license", list(lic_by_label.keys()))
        edit_lic = lic_by_label[edit_label]
        k = edit_lic["id"]
        ecol1, ecol2, ecol3 = st.columns(3)
        edit_name = ecol1.text_input("License name", value=edit_lic["name"], key=f"lic_name_{k}")
        edit_vendor = ecol2.text_input("Vendor", value=edit_lic.get("vendor") or "", key=f"lic_vendor_{k}")
        edit_expiry = ecol3.date_input(
            "Next expiry date", value=dt.date.fromisoformat(edit_lic["expiry_date"]),
            key=f"lic_expiry_{k}",
        )
        edit_notes = st.text_input("Notes", value=edit_lic.get("notes") or "", key=f"lic_notes_{k}")

        bcol1, bcol2, bcol3 = st.columns([1, 2, 1])
        if bcol1.button("💾 Save license", key=f"lic_save_{k}"):
            if not edit_name or not edit_expiry:
                st.error("License name and expiry date are required.")
            else:
                update_license(
                    k, name=edit_name.strip(), vendor=edit_vendor.strip() or None,
                    expiry_date=edit_expiry.isoformat(), notes=edit_notes.strip() or None,
                )
                st.rerun()
        confirm_lic_delete = bcol2.checkbox("Confirm delete this license", key=f"lic_confirm_del_{k}")
        if bcol3.button("🗑️ Delete", key=f"lic_del_{k}", disabled=not confirm_lic_delete):
            delete_license(k)
            st.rerun()

    if not notify.email_enabled():
        st.caption(
            "Email reminders are off — add the SMTP_* settings to secrets.toml to "
            f"email {notify.DEFAULT_REMINDER_TO} when a license is within a week of expiry."
        )

st.divider()

my_tasks = list_tasks(assignee_id=profile["id"])

col1, col2, col3 = st.columns(3)
col1.metric("Projects", len(projects))
col2.metric("My open tasks", len([t for t in my_tasks if t["status"] != "done"]))
col3.metric("My completed tasks", len([t for t in my_tasks if t["status"] == "done"]))

st.divider()
st.subheader("All projects")

for p in projects:
    prog = utils.project_progress(tasks_by_project[p["id"]], rollup=True)
    with st.container(border=True):
        title_col, proj_completion_col = st.columns([3, 1])
        title_col.markdown(f"**{p['key']}** — {p['name']}")
        proj_completion_col.markdown(
            f"<div style='text-align:right'>Project Completion Date<br>"
            f"<b>{p.get('project_completion_date') or '—'}</b></div>",
            unsafe_allow_html=True,
        )
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

        current_owner_name = id_to_name.get(p.get("lead_id"), "Unassigned")
        current_priority = p.get("priority") or "medium"
        current_completion = p.get("completion_date") or "—"

        if is_admin:
            owner_options = ["Unassigned"] + list(name_to_id.keys())

            ocol1, ocol2, ocol3, ocol4, ocol5 = st.columns([2, 2, 2, 2, 1])
            new_owner_name = ocol1.selectbox(
                "Primary owner", owner_options,
                index=owner_options.index(current_owner_name)
                if current_owner_name in owner_options else 0,
                key=f"owner_{p['id']}",
            )
            new_completion = ocol2.text_input(
                "Next task completion", value=p.get("completion_date") or "",
                key=f"completion_{p['id']}",
            )
            new_priority = ocol3.selectbox(
                "Priority", utils.PRIORITY_OPTIONS,
                index=utils.PRIORITY_OPTIONS.index(current_priority),
                format_func=lambda x: f"{utils.PRIORITY_ICONS.get(x, '')} {x.title()}",
                key=f"priority_{p['id']}",
            )
            new_project_completion = ocol4.text_input(
                "Project completion date", value=p.get("project_completion_date") or "",
                key=f"proj_completion_{p['id']}",
            )
            ocol5.write("")
            ocol5.write("")
            if ocol5.button("💾", key=f"save_proj_{p['id']}", help="Save"):
                update_project(
                    p["id"],
                    lead_id=name_to_id.get(new_owner_name),
                    completion_date=new_completion,
                    priority=new_priority,
                    project_completion_date=new_project_completion,
                )
                st.rerun()
        else:
            st.caption(
                f"Owner: {current_owner_name} · "
                f"Priority: {utils.PRIORITY_ICONS.get(current_priority, '')} {current_priority.title()} · "
                f"Next task completion: {current_completion}"
            )

# =====================================================================
# Admin analytics — project & people level view. Admins don't add tasks
# here; this is purely an oversight view of who's doing what and how
# much progress each project/person has made.
# =====================================================================
if is_admin:
    st.divider()
    st.header("📊 Admin analytics")

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
                total_est = max(own_est, sub_est)
                total_logged = max(own_logged, sub_logged)

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
