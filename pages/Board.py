import streamlit as st

from auth import require_login, logout_button
from db import list_projects, list_tasks, update_task, list_profiles
import utils

st.set_page_config(page_title="Board", page_icon="🗂️", layout="wide")
profile = require_login()
st.sidebar.write(f"Signed in as **{profile['full_name']}**")
logout_button()

st.title("🗂️ Board")

projects = list_projects()
if not projects:
    st.info("Create a project first, on the Projects page.")
    st.stop()

project_labels = {f"{p['key']} — {p['name']}": p["id"] for p in projects}
selected_label = st.selectbox("Project", list(project_labels.keys()))
project_id = project_labels[selected_label]

all_profiles = list_profiles()
name_by_id = {p["id"]: p["full_name"] for p in all_profiles}
filter_names = ["Everyone"] + list(name_by_id.values())
filter_choice = st.selectbox("Filter by assignee", filter_names)
assignee_filter = None
if filter_choice != "Everyone":
    assignee_filter = next(pid for pid, n in name_by_id.items() if n == filter_choice)

tasks = list_tasks(project_id=project_id, assignee_id=assignee_filter, parent_id="any")

cols = st.columns(len(utils.STATUS_OPTIONS))
for col, status in zip(cols, utils.STATUS_OPTIONS):
    with col:
        st.markdown(f"#### {utils.STATUS_LABELS[status]}")
        col_tasks = [t for t in tasks if t["status"] == status]
        st.caption(f"{len(col_tasks)} item(s)")
        for t in col_tasks:
            with st.container(border=True):
                st.markdown(f"**{t['task_key']}**")
                st.write(t["title"])
                assignee = t.get("profiles") or {}
                st.caption(assignee.get("full_name") or "Unassigned")
                new_status = st.selectbox(
                    "Move to", utils.STATUS_OPTIONS,
                    index=utils.STATUS_OPTIONS.index(status),
                    key=f"move_{t['id']}",
                    label_visibility="collapsed",
                )
                if new_status != status:
                    update_task(t["id"], profile["id"], status=new_status)
                    st.rerun()
