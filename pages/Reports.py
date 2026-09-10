



import datetime as dt

import pandas as pd
import streamlit as st

from auth import require_login, logout_button
from db import list_profiles, get_user_activity, get_tasks_completed_in_range
import utils

st.set_page_config(page_title="Reports", page_icon="📊", layout="wide")
profile = require_login()
st.sidebar.write(f"Signed in as **{profile['full_name']}**")
logout_button()

st.title("📊 What did a user do?")
st.caption("Pick a person and a date range to see everything they did in that window.")

all_profiles = list_profiles()
name_by_id = utils.name_to_id_map(all_profiles)
names = list(name_by_id.keys())

col1, col2, col3 = st.columns([2, 1, 1])
default_index = names.index(profile["full_name"]) if profile["full_name"] in names else 0
person_name = col1.selectbox("User", names, index=default_index)
start_date = col2.date_input("From", value=dt.date.today() - dt.timedelta(days=7))
end_date = col3.date_input("To", value=dt.date.today())

if start_date > end_date:
    st.error("'From' date must be on or before 'To' date.")
    st.stop()

user_id = name_by_id[person_name]
activity = get_user_activity(user_id, start_date, end_date)
completed = get_tasks_completed_in_range(user_id, start_date, end_date)
created_count = len([a for a in activity if a["action"] == "created"])

m1, m2, m3 = st.columns(3)
m1.metric("Activity events", len(activity))
m2.metric("Tasks completed", len(completed))
m3.metric("Tasks created", created_count)

if not activity:
    st.info(f"No activity for {person_name} between {start_date} and {end_date}.")
    st.stop()

df = pd.DataFrame(
    [
        {
            "When": a["created_at"],
            "Task": f"{a['tasks']['task_key']} — {a['tasks']['title']}" if a.get("tasks") else "",
            "Project": a["projects"]["key"] if a.get("projects") else "",
            "Action": a["action"].replace("_", " ").title(),
            "Change": (
                f"{a.get('old_value') or ''} → {a.get('new_value') or ''}"
                if a.get("old_value") or a.get("new_value")
                else ""
            ),
        }
        for a in activity
    ]
)
df["When"] = pd.to_datetime(df["When"]).dt.strftime("%Y-%m-%d %H:%M")

st.subheader("Activity log")
st.dataframe(df, use_container_width=True, hide_index=True)

st.subheader("Activity per day")
daily = pd.to_datetime([a["created_at"] for a in activity]).date
daily_counts = pd.Series(daily).value_counts().sort_index()
st.bar_chart(daily_counts)

st.subheader("Breakdown by action type")
action_counts = df["Action"].value_counts()
st.bar_chart(action_counts)
