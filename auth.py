"""
Login / sign-up screens and session helpers, backed by Supabase Auth.
"""
import streamlit as st
from db import get_client, get_profile, upsert_profile


def _set_session(session, user) -> None:
    st.session_state["session"] = session
    st.session_state["user"] = user
    st.session_state["profile"] = get_profile(user.id)


def login_form() -> None:
    st.title("🔷 Jira-lite")
    st.caption("Sign in to continue")
    tab_login, tab_signup = st.tabs(["Sign in", "Create account"])

    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign in", use_container_width=True)
        if submitted:
            sb = get_client()
            try:
                result = sb.auth.sign_in_with_password(
                    {"email": email, "password": password}
                )
                _set_session(result.session, result.user)
                st.rerun()
            except Exception as e:
                st.error(f"Sign in failed: {e}")

    with tab_signup:
        with st.form("signup_form"):
            full_name = st.text_input("Full name")
            email2 = st.text_input("Email", key="signup_email")
            password2 = st.text_input("Password", type="password", key="signup_pw")
            submitted2 = st.form_submit_button("Create account", use_container_width=True)
        if submitted2:
            if not full_name or not email2 or not password2:
                st.error("All fields are required.")
            else:
                sb = get_client()
                try:
                    result = sb.auth.sign_up({"email": email2, "password": password2})
                    if result.user:
                        upsert_profile(result.user.id, email2, full_name)
                        st.success(
                            "Account created. If email confirmation is enabled on your "
                            "Supabase project, check your inbox, then sign in above."
                        )
                    else:
                        st.error("Sign up failed. Please try again.")
                except Exception as e:
                    st.error(f"Sign up failed: {e}")


def require_login() -> dict:
    """Call at the top of every page. Blocks the page with a login form
    until the user is signed in, then returns their profile dict."""
    if "user" not in st.session_state:
        login_form()
        st.stop()
    return st.session_state["profile"]


def logout_button() -> None:
    if st.sidebar.button("Log out", use_container_width=True):
        sb = get_client()
        try:
            sb.auth.sign_out()
        except Exception:
            pass
        for k in ("session", "user", "profile"):
            st.session_state.pop(k, None)
        st.rerun()
