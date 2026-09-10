import streamlit as st

from auth import require_login, logout_button
from db import list_tasks, update_task
import utils

st.set_page_config(page_title="My Tasks", page_icon="✅", layout="wide")
profile = require_login()
st.sidebar.write(f"Signed in as **{profile['full_name']}**")
logout_button()

st.title("✅ My Tasks")

status_filter = st.multiselect(
    "Status",
    utils.STATUS_OPTIONS,
    default=[s for s in utils.STATUS_OPTIONS if s != "done"],
    format_func=lambda s: utils.STATUS_LABELS[s],
)

my_tasks = list_tasks(assignee_id=profile["id"], parent_id="any")
my_tasks = [t for t in my_tasks if t["status"] in status_filter]

if not my_tasks:
    st.info("Nothing here — enjoy the calm.")

for t in my_tasks:
    with st.container(border=True):
        cols = st.columns([5, 2, 2])
        cols[0].markdown(
            f"**{t['task_key']}** {utils.ISSUE_TYPE_ICONS.get(t['issue_type'], '')} {t['title']}"
        )
        cols[1].write(f"{utils.PRIORITY_ICONS.get(t['priority'], '')} {t['priority']}")
        due = t.get("due_date")
        cols[2].write(f"Due {due}" if due else "No due date")

        new_status = st.selectbox(
            "Status", utils.STATUS_OPTIONS,
            index=utils.STATUS_OPTIONS.index(t["status"]),
            key=f"mt_status_{t['id']}",
        )
        if new_status != t["status"]:
            update_task(t["id"], profile["id"], status=new_status)
            st.rerun()
