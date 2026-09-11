import streamlit as st

from auth import require_login, logout_button
from db import list_projects, list_tasks

st.set_page_config(page_title="Jira-lite", page_icon="🔷", layout="wide")

profile = require_login()

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
st.subheader("Recent projects")

if not projects:
    st.info("No projects yet. Open **Projects** in the sidebar to create one.")
else:
    for p in projects[:500]:
        with st.container(border=True):
            st.markdown(f"**{p['key']}** — {p['name']}")
            st.caption(p.get("description") or "No description")

st.caption(
    "Use the pages in the left sidebar: **Projects** to create work, "
    "**Board** for a kanban view, **My Tasks** for your own list, "
    "and **Reports** to see what anyone did over a date range."
)
