import streamlit as st

from auth import require_login, logout_button
from db import (
    list_projects,
    create_project,
    get_project,
    list_profiles,
    add_project_member,
    list_project_members,
    list_tasks,
    list_subtasks,
    create_task,
    update_task,
    list_comments,
    create_comment,
)
import utils

st.set_page_config(page_title="Projects", page_icon="📁", layout="wide")
profile = require_login()
st.sidebar.write(f"Signed in as **{profile['full_name']}**")
logout_button()

st.title("📁 Projects")

# ---------------------------------------------------------------
# Create project
# ---------------------------------------------------------------
with st.expander("➕ Create new project"):
    with st.form("new_project"):
        key = st.text_input("Project key (short code, e.g. ENG)", max_chars=10)
        name = st.text_input("Project name")
        description = st.text_area("Description")
        submitted = st.form_submit_button("Create project")
    if submitted:
        if not key or not name:
            st.error("Key and name are required.")
        else:
            proj = create_project(key, name, description, profile["id"], profile["id"])
            add_project_member(proj["id"], profile["id"], "lead")
            st.success(f"Created project {proj['key']}")
            st.rerun()

projects = list_projects()
if not projects:
    st.info("No projects yet — create one above.")
    st.stop()

project_labels = {f"{p['key']} — {p['name']}": p["id"] for p in projects}
selected_label = st.selectbox("Select a project", list(project_labels.keys()))
project_id = project_labels[selected_label]
project = get_project(project_id)

st.subheader(f"{project['key']} — {project['name']}")
st.write(project.get("description") or "_No description_")

all_profiles = list_profiles()
profile_map = utils.name_to_id_map(all_profiles)
id_to_name = {v: k for k, v in profile_map.items()}

tab_tasks, tab_members = st.tabs(["Tasks", "Members"])

# ---------------------------------------------------------------
# Tasks tab
# ---------------------------------------------------------------
with tab_tasks:
    with st.expander("➕ Add a task"):
        with st.form("new_task"):
            title = st.text_input("Title")
            desc = st.text_area("Description")
            c1, c2, c3 = st.columns(3)
            issue_type = c1.selectbox("Type", utils.ISSUE_TYPE_ROOT_OPTIONS)
            priority = c2.selectbox("Priority", utils.PRIORITY_OPTIONS, index=2)
            assignee_name = c3.selectbox("Assignee", ["Unassigned"] + list(profile_map.keys()))
            due = st.date_input("Due date", value=None)
            submitted_task = st.form_submit_button("Create task")
        if submitted_task:
            if not title:
                st.error("Title is required.")
            else:
                assignee_id = profile_map.get(assignee_name)
                create_task(
                    project_id, title, desc, issue_type, priority, assignee_id,
                    profile["id"], due_date=str(due) if due else None,
                )
                st.success("Task created.")
                st.rerun()

    root_tasks = list_tasks(project_id=project_id, parent_id="root_only")
    st.write(f"**{len(root_tasks)} task(s)**")

    for t in root_tasks:
        with st.container(border=True):
            top = st.columns([5, 2, 2, 2])
            top[0].markdown(
                f"**{t['task_key']}** {utils.ISSUE_TYPE_ICONS.get(t['issue_type'], '')} {t['title']}"
            )
            top[1].write(utils.STATUS_LABELS.get(t["status"], t["status"]))
            top[2].write(f"{utils.PRIORITY_ICONS.get(t['priority'], '')} {t['priority']}")
            assignee = t.get("profiles") or {}
            top[3].write(assignee.get("full_name") or "Unassigned")

            with st.expander("Details, sub-tasks & comments"):
                st.write(t.get("description") or "_No description_")

                cols = st.columns([2, 2, 1])
                new_status = cols[0].selectbox(
                    "Status", utils.STATUS_OPTIONS,
                    index=utils.STATUS_OPTIONS.index(t["status"]),
                    key=f"status_{t['id']}",
                )
                assignee_options = ["Unassigned"] + list(profile_map.keys())
                current_assignee_name = assignee.get("full_name") or "Unassigned"
                new_assignee_name = cols[1].selectbox(
                    "Assignee", assignee_options,
                    index=assignee_options.index(current_assignee_name)
                    if current_assignee_name in assignee_options else 0,
                    key=f"assignee_{t['id']}",
                )
                if cols[2].button("Save", key=f"save_{t['id']}"):
                    update_task(
                        t["id"], profile["id"],
                        status=new_status,
                        assignee_id=profile_map.get(new_assignee_name),
                    )
                    st.rerun()

                st.markdown("##### Sub-tasks")
                subtasks = list_subtasks(t["id"])
                if not subtasks:
                    st.caption("No sub-tasks yet.")
                for st_ in subtasks:
                    sub_assignee = st_.get("profiles") or {}
                    st.write(
                        f"- **{st_['task_key']}** {st_['title']} — "
                        f"{utils.STATUS_LABELS.get(st_['status'])} "
                        f"({sub_assignee.get('full_name') or 'Unassigned'})"
                    )

                with st.form(f"subtask_form_{t['id']}"):
                    sub_title = st.text_input("New sub-task title", key=f"sub_title_{t['id']}")
                    sub_assignee_name = st.selectbox(
                        "Assignee", ["Unassigned"] + list(profile_map.keys()),
                        key=f"sub_assignee_{t['id']}",
                    )
                    sub_submitted = st.form_submit_button("Add sub-task")
                if sub_submitted and sub_title:
                    create_task(
                        project_id, sub_title, "", "subtask", "medium",
                        profile_map.get(sub_assignee_name), profile["id"], parent_id=t["id"],
                    )
                    st.rerun()

                st.markdown("##### Comments")
                for c in list_comments(t["id"]):
                    author = (c.get("profiles") or {}).get("full_name", "Someone")
                    st.markdown(f"**{author}:** {c['body']}")
                with st.form(f"comment_form_{t['id']}"):
                    comment_body = st.text_input("Add a comment", key=f"comment_{t['id']}")
                    comment_submitted = st.form_submit_button("Post")
                if comment_submitted and comment_body:
                    create_comment(t["id"], profile["id"], comment_body)
                    st.rerun()

# ---------------------------------------------------------------
# Members tab
# ---------------------------------------------------------------
with tab_members:
    members = list_project_members(project_id)
    for m in members:
        person = m.get("profiles") or {}
        st.write(f"- {person.get('full_name', 'Unknown')} ({m['role']})")

    if all_profiles:
        with st.form("add_member"):
            pick = st.selectbox("Add a member", list(profile_map.keys()))
            add_sub = st.form_submit_button("Add")
        if add_sub:
            add_project_member(project_id, profile_map[pick])
            st.rerun()
