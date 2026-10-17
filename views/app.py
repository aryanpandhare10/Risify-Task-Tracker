"""
Entry point / router. Signs the user in, then shows only the pages their role
may use:
  admin      -> project pages + Compliance
  member     -> project pages
  compliance -> Compliance only
Page scripts live in views/ (not pages/, so Streamlit doesn't auto-list them).
"""
import streamlit as st

from auth import require_login, logout_button
from db import list_compliance_entities, list_compliance_items
import notify

st.set_page_config(page_title="Risify Portal", page_icon="🔷", layout="wide")

profile = require_login()
role = profile["role"]

st.sidebar.title("🔷 Risify Portal")
st.sidebar.write(f"Signed in as **{profile['full_name']}**")
st.sidebar.caption(role.title())
logout_button()

project_pages = [
    st.Page("views/Dashboard.py", title="Dashboard", icon="🏠", default=role != "compliance"),
    st.Page("views/Projects.py", title="Projects", icon="📁"),
    st.Page("views/Board.py", title="Board", icon="🗂️"),
    st.Page("views/My_Tasks.py", title="My Tasks", icon="✅"),
    st.Page("views/Reports.py", title="Reports", icon="📊"),
]
compliance_page = st.Page(
    "views/Compliance.py", title="Compliance", icon="🛡️", default=role == "compliance",
)

if role == "compliance":
    nav = st.navigation([compliance_page])
elif role == "admin":
    nav = st.navigation({"Projects": project_pages, "Compliance": [compliance_page]})
else:
    nav = st.navigation(project_pages)

# Compliance email digest: checked once per session for users who can see
# compliance data, whichever page they open first.
if role in ("admin", "compliance") and not st.session_state.get("compliance_reminders_checked"):
    st.session_state["compliance_reminders_checked"] = True
    try:
        notify.send_compliance_reminders(list_compliance_items(), list_compliance_entities())
    except Exception as e:  # never block the portal on a reminder problem
        st.toast(f"Compliance reminder check failed: {e}", icon="⚠️")

nav.run()
