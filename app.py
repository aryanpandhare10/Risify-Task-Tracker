import datetime as dt

import pandas as pd
import streamlit as st

from auth import require_login, logout_button
from db import (
    list_projects, list_tasks, list_profiles, update_project,
    list_digital_assets, create_digital_asset, update_digital_asset, delete_digital_asset,
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

# Payment reminders — any digital-asset invoice overdue or due within a week
# is flagged here on every dashboard load, and emailed once (if SMTP is configured).
assets = list_digital_assets()
for a in assets:
    status = utils.asset_status(a)
    if status == "upcoming":
        continue
    msg = (
        f"💳 Invoice for **{utils.asset_label(a)}** "
        f"({float(a.get('invoice_amount') or 0):,.2f}) is "
        f"{utils.due_when(utils.asset_days_left(a))} — {a['due_date']}."
    )
    if status == "overdue":
        st.error(msg)
    else:
        st.warning(msg)
notify.send_payment_reminders(assets)

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
# Digital assets payment tracker — manually maintained list of recurring
# invoices (servers, domains, email, vendors, ...). S.No. is numbered after
# filtering so it always gives the count of what's shown.
# Orange = due within a week, red = overdue.
# =====================================================================
st.subheader("💳 Digital Assets Payment Tracker")

if "da_flash" in st.session_state:
    st.success(st.session_state.pop("da_flash"))

if not assets:
    st.caption("No payments tracked yet. Add one below.")
else:
    with st.expander("🔎 Filters"):
        entity_choices = sorted({a["entity"] for a in assets})
        f_entity = st.selectbox("Entity", ["All entities"] + entity_choices, key="da_f_entity")
        f_service = utils.checkbox_filter(
            st, "Service type", utils.SERVICE_TYPE_OPTIONS, key_prefix="da_f_service",
            format_func=lambda s: utils.SERVICE_TYPE_LABELS[s], per_row=5,
        )
        f_cycle = utils.checkbox_filter(
            st, "Billing cycle", utils.BILLING_CYCLE_OPTIONS, key_prefix="da_f_cycle",
            format_func=lambda c: utils.BILLING_CYCLE_LABELS[c],
        )
        f_status = utils.checkbox_filter(
            st, "Status", list(utils.ASSET_STATUS_LABELS), key_prefix="da_f_status",
            format_func=lambda s: utils.ASSET_STATUS_LABELS[s],
        )

    shown_assets = [
        a for a in assets
        if (f_entity == "All entities" or a["entity"] == f_entity)
        and a["service_type"] in f_service
        and a["billing_cycle"] in f_cycle
        and utils.asset_status(a, today) in f_status
    ]

    if not shown_assets:
        st.caption(f"No payments match the filters (0 of {len(assets)}).")
    else:
        asset_statuses = [utils.asset_status(a, today) for a in shown_assets]
        assets_df = pd.DataFrame([{
            "S.No.": i,
            "Entity": a["entity"],
            "Service type": utils.service_type_label(a),
            "Billing cycle": utils.BILLING_CYCLE_LABELS.get(a["billing_cycle"], a["billing_cycle"]),
            "Invoice amount": float(a.get("invoice_amount") or 0),
            "Invoice due date": a["due_date"],
            "Days left": utils.asset_days_left(a, today),
            "Status": utils.ASSET_STATUS_LABELS[s],
        } for i, (a, s) in enumerate(zip(shown_assets, asset_statuses), start=1)])

        def _asset_colors(col: pd.Series) -> list:
            return [
                f"color: {utils.ASSET_STATUS_COLORS[s]}" if utils.ASSET_STATUS_COLORS[s] else ""
                for s in asset_statuses
            ]

        st.dataframe(
            assets_df.style
            .apply(_asset_colors, subset=["Invoice due date", "Days left", "Status"])
            .format({"Invoice amount": "{:,.2f}"}),
            use_container_width=True, hide_index=True,
        )
        st.caption(
            f"Showing {len(shown_assets)} of {len(assets)} · "
            f"Total invoice amount: {assets_df['Invoice amount'].sum():,.2f}"
        )


def _add_asset() -> None:
    """Button callback: validate, insert, then clear the add fields."""
    ss = st.session_state
    entity = ss["da_new_entity"].strip()
    service = ss["da_new_service"]
    other = ss.get("da_new_other", "").strip()
    due = ss["da_new_due"]
    if not entity or not due or (service == "others" and not other):
        ss["da_add_error"] = (
            "Entity and invoice due date are required"
            + (", and enter the service type for Others." if service == "others" else ".")
        )
        return
    create_digital_asset(
        entity, service, other if service == "others" else None,
        ss["da_new_cycle"], ss["da_new_amount"], due.isoformat(), profile["id"],
    )
    ss["da_new_entity"] = ""
    ss["da_new_other"] = ""
    ss["da_new_amount"] = 0.0
    ss["da_new_due"] = None
    ss["da_flash"] = f"Added {entity}."


def _mark_paid(asset: dict) -> None:
    """Button callback: roll the due date forward by one billing cycle."""
    nxt = utils.next_due_date(dt.date.fromisoformat(asset["due_date"]), asset["billing_cycle"])
    update_digital_asset(asset["id"], due_date=nxt.isoformat())
    st.session_state.pop(f"da_due_{asset['id']}", None)  # show the new date in the edit field
    st.session_state["da_flash"] = f"Marked {utils.asset_label(asset)} paid — next due {nxt}."


with st.expander("➕ Add / edit payments"):
    acol1, acol2, acol3 = st.columns(3)
    acol1.text_input("Entity", key="da_new_entity")
    new_service = acol2.selectbox(
        "Service type", utils.SERVICE_TYPE_OPTIONS, key="da_new_service",
        format_func=lambda s: utils.SERVICE_TYPE_LABELS[s],
    )
    if new_service == "others":
        acol3.text_input("Specify service type", key="da_new_other")
    bcol1, bcol2, bcol3 = st.columns(3)
    bcol1.selectbox(
        "Billing cycle", utils.BILLING_CYCLE_OPTIONS, key="da_new_cycle",
        format_func=lambda c: utils.BILLING_CYCLE_LABELS[c],
    )
    bcol2.number_input("Invoice amount", min_value=0.0, step=100.0, format="%.2f", key="da_new_amount")
    bcol3.date_input("Invoice due date", value=None, key="da_new_due")
    st.button("Add payment", on_click=_add_asset)
    if "da_add_error" in st.session_state:
        st.error(st.session_state.pop("da_add_error"))

    if assets:
        st.divider()
        asset_by_id = {a["id"]: a for a in assets}
        edit_id = st.selectbox(
            "Edit an existing payment", list(asset_by_id),
            format_func=lambda i: f"{utils.asset_label(asset_by_id[i])} — due {asset_by_id[i]['due_date']}",
        )
        ea = asset_by_id[edit_id]
        k = ea["id"]

        ecol1, ecol2, ecol3 = st.columns(3)
        edit_entity = ecol1.text_input("Entity", value=ea["entity"], key=f"da_entity_{k}")
        edit_service = ecol2.selectbox(
            "Service type", utils.SERVICE_TYPE_OPTIONS,
            index=utils.SERVICE_TYPE_OPTIONS.index(ea["service_type"]),
            format_func=lambda s: utils.SERVICE_TYPE_LABELS[s], key=f"da_service_{k}",
        )
        edit_other = ""
        if edit_service == "others":
            edit_other = ecol3.text_input(
                "Specify service type", value=ea.get("service_type_other") or "", key=f"da_other_{k}",
            )
        fcol1, fcol2, fcol3 = st.columns(3)
        edit_cycle = fcol1.selectbox(
            "Billing cycle", utils.BILLING_CYCLE_OPTIONS,
            index=utils.BILLING_CYCLE_OPTIONS.index(ea["billing_cycle"]),
            format_func=lambda c: utils.BILLING_CYCLE_LABELS[c], key=f"da_cycle_{k}",
        )
        edit_amount = fcol2.number_input(
            "Invoice amount", min_value=0.0, step=100.0, format="%.2f",
            value=float(ea.get("invoice_amount") or 0), key=f"da_amount_{k}",
        )
        edit_due = fcol3.date_input(
            "Invoice due date", value=dt.date.fromisoformat(ea["due_date"]), key=f"da_due_{k}",
        )

        gcol1, gcol2, gcol3, gcol4 = st.columns([1, 1.6, 1.6, 1])
        if gcol1.button("💾 Save", key=f"da_save_{k}"):
            if not edit_entity.strip() or not edit_due or (edit_service == "others" and not edit_other.strip()):
                st.error("Entity and invoice due date are required (and the service type for Others).")
            else:
                update_digital_asset(
                    k, entity=edit_entity.strip(), service_type=edit_service,
                    service_type_other=edit_other.strip() if edit_service == "others" else None,
                    billing_cycle=edit_cycle, invoice_amount=edit_amount,
                    due_date=edit_due.isoformat(),
                )
                st.rerun()
        gcol2.button(
            "✅ Mark paid → next due date", key=f"da_paid_{k}", on_click=_mark_paid, args=(ea,),
            help=f"Moves the due date forward one {utils.BILLING_CYCLE_LABELS[ea['billing_cycle']].lower()} "
                 f"cycle, to {utils.next_due_date(dt.date.fromisoformat(ea['due_date']), ea['billing_cycle'])}.",
        )
        confirm_da_delete = gcol3.checkbox("Confirm delete this payment", key=f"da_confirm_del_{k}")
        if gcol4.button("🗑️ Delete", key=f"da_del_{k}", disabled=not confirm_da_delete):
            delete_digital_asset(k)
            st.rerun()

    if not notify.email_enabled():
        st.caption(
            "Email reminders are off — add the SMTP_* settings to secrets.toml to "
            f"email {notify.DEFAULT_REMINDER_TO} when an invoice is due within a week."
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
