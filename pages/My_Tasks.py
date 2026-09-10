import streamlit as st

from auth import require_login, logout_button
from db import (
    list_tasks,
    update_task,
    update_task_estimate,
    log_time,
    list_time_logs,
    get_total_logged_hours,
)
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
        cols = st.columns([4, 2, 2, 2])
        cols[0].markdown(
            f"**{t['task_key']}** {utils.ISSUE_TYPE_ICONS.get(t['issue_type'], '')} {t['title']}"
        )
        cols[1].write(f"{utils.PRIORITY_ICONS.get(t['priority'], '')} {t['priority']}")
        due = t.get("due_date")
        cols[2].write(f"Due {due}" if due else "No due date")

        logged = get_total_logged_hours(t["id"])
        est = t.get("estimated_hours")
        cols[3].write(f"{logged:g} / {est:g} hrs" if est else f"{logged:g} hrs logged")

        new_status = st.selectbox(
            "Status", utils.STATUS_OPTIONS,
            index=utils.STATUS_OPTIONS.index(t["status"]),
            key=f"mt_status_{t['id']}",
        )
        if new_status != t["status"]:
            update_task(t["id"], profile["id"], status=new_status)
            st.rerun()

        with st.expander("Log hours / update estimate"):
            log_col, est_col = st.columns(2)

            with log_col:
                st.markdown("**Log hours worked**")
                with st.form(f"log_hours_{t['id']}"):
                    hours = st.number_input("Hours", min_value=0.25, step=0.25, key=f"hrs_{t['id']}")
                    log_date = st.date_input("Date", key=f"logdate_{t['id']}")
                    note = st.text_input("Note (optional)", key=f"lognote_{t['id']}")
                    log_submitted = st.form_submit_button("Log hours")
                if log_submitted:
                    log_time(t["id"], profile["id"], hours, note=note, log_date=str(log_date))
                    st.success("Logged.")
                    st.rerun()

                logs = list_time_logs(t["id"])
                if logs:
                    st.caption("Recent entries:")
                    for l in logs[:5]:
                        who = (l.get("profiles") or {}).get("full_name", "")
                        extra = f" — {l['note']}" if l.get("note") else ""
                        st.caption(f"- {l['log_date']}: {l['hours']:g}h by {who}{extra}")

            with est_col:
                st.markdown("**Update hour estimate**")
                st.caption(f"Current estimate: {est:g} hrs" if est else "No estimate set yet")
                with st.form(f"update_estimate_{t['id']}"):
                    new_est = st.number_input(
                        "New estimate (hours)", min_value=0.0, step=0.5,
                        value=float(est) if est else 0.0, key=f"newest_{t['id']}",
                    )
                    justification = st.text_area(
                        "Justification for this change (required)", key=f"justify_{t['id']}"
                    )
                    est_submitted = st.form_submit_button("Update estimate")
                if est_submitted:
                    if not justification.strip():
                        st.error("A justification is required to change the estimate.")
                    elif new_est == est:
                        st.warning("That's the same as the current estimate.")
                    else:
                        update_task_estimate(t["id"], profile["id"], new_est, justification)
                        st.success("Estimate updated.")
                        st.rerun()
