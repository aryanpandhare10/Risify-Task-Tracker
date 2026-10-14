"""
Supabase client + all data-access helpers used across the app.
Every read/write in the app goes through a function in this file.
"""
import datetime as dt
from typing import Optional

import streamlit as st
from supabase import create_client, Client


@st.cache_resource
def get_client() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)


# ---------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------
def get_profile(user_id: str) -> Optional[dict]:
    sb = get_client()
    res = sb.table("profiles").select("*").eq("id", user_id).execute()
    return res.data[0] if res.data else None


def upsert_profile(user_id: str, email: str, full_name: str, role: str = "member") -> None:
    sb = get_client()
    sb.table("profiles").upsert(
        {"id": user_id, "email": email, "full_name": full_name, "role": role}
    ).execute()


def list_profiles() -> list:
    sb = get_client()
    return sb.table("profiles").select("*").order("full_name").execute().data


# ---------------------------------------------------------------
# Projects
# ---------------------------------------------------------------
def list_projects() -> list:
    sb = get_client()
    return sb.table("projects").select("*").order("created_at", desc=True).execute().data


def get_project(project_id: str) -> Optional[dict]:
    sb = get_client()
    res = sb.table("projects").select("*").eq("id", project_id).execute()
    return res.data[0] if res.data else None


def create_project(key: str, name: str, description: str, lead_id: str, created_by: str) -> dict:
    sb = get_client()
    res = sb.table("projects").insert(
        {
            "key": key.strip().upper(),
            "name": name.strip(),
            "description": description,
            "lead_id": lead_id,
            "created_by": created_by,
        }
    ).execute()
    return res.data[0]


def update_project(project_id: str, **fields) -> dict:
    sb = get_client()
    res = sb.table("projects").update(fields).eq("id", project_id).execute()
    return res.data[0]


def add_project_member(project_id: str, user_id: str, role: str = "member") -> None:
    sb = get_client()
    sb.table("project_members").upsert(
        {"project_id": project_id, "user_id": user_id, "role": role}
    ).execute()


def list_project_members(project_id: str) -> list:
    sb = get_client()
    res = (
        sb.table("project_members")
        .select("*, profiles(id, full_name, email)")
        .eq("project_id", project_id)
        .execute()
    )
    return res.data


# ---------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------
def list_tasks(
    project_id: Optional[str] = None,
    assignee_id: Optional[str] = None,
    status: Optional[str] = None,
    parent_id: Optional[str] = "any",
) -> list:
    """parent_id: 'any' (default, no filter), 'root_only' (top-level tasks only),
    or a specific task id to fetch its sub-tasks."""
    sb = get_client()
    q = sb.table("tasks").select("*, profiles!tasks_assignee_id_fkey(id, full_name)")
    if project_id:
        q = q.eq("project_id", project_id)
    if assignee_id:
        q = q.eq("assignee_id", assignee_id)
    if status:
        q = q.eq("status", status)
    if parent_id == "root_only":
        q = q.is_("parent_id", "null")
    elif parent_id not in ("any", None):
        q = q.eq("parent_id", parent_id)
    return q.order("created_at", desc=True).execute().data


def get_task(task_id: str) -> Optional[dict]:
    sb = get_client()
    res = sb.table("tasks").select("*").eq("id", task_id).execute()
    return res.data[0] if res.data else None


def list_subtasks(parent_id: str) -> list:
    sb = get_client()
    return (
        sb.table("tasks")
        .select("*, profiles!tasks_assignee_id_fkey(id, full_name)")
        .eq("parent_id", parent_id)
        .order("created_at")
        .execute()
        .data
    )


def create_task(
    project_id: str,
    title: str,
    description: str,
    issue_type: str,
    priority: str,
    assignee_id: Optional[str],
    reporter_id: str,
    due_date: Optional[str] = None,
    parent_id: Optional[str] = None,
    estimate_hours: float = 0,
) -> dict:
    sb = get_client()
    payload = {
        "project_id": project_id,
        "title": title.strip(),
        "description": description,
        "issue_type": issue_type,
        "priority": priority,
        "assignee_id": assignee_id,
        "reporter_id": reporter_id,
        "updated_by": reporter_id,
        "due_date": due_date,
        "parent_id": parent_id,
        "estimate_hours": estimate_hours or 0,
    }
    res = sb.table("tasks").insert(payload).execute()
    return res.data[0]


def update_task(task_id: str, updated_by: str, **fields) -> dict:
    sb = get_client()
    fields["updated_by"] = updated_by
    res = sb.table("tasks").update(fields).eq("id", task_id).execute()
    return res.data[0]


def update_task_estimate(task_id: str, updated_by: str, estimate_hours: float) -> dict:
    return update_task(task_id, updated_by, estimate_hours=estimate_hours)


def log_hours(task_id: str, updated_by: str, logged_hours: float) -> dict:
    """Set a task's running total of hours actually worked so far."""
    return update_task(task_id, updated_by, logged_hours=logged_hours)


def delete_task(task_id: str) -> None:
    """Delete a task. Sub-tasks, comments and activity log rows cascade via FK."""
    sb = get_client()
    sb.table("tasks").delete().eq("id", task_id).execute()


# ---------------------------------------------------------------
# Comments
# ---------------------------------------------------------------
def list_comments(task_id: str) -> list:
    sb = get_client()
    return (
        sb.table("comments")
        .select("*, profiles(full_name)")
        .eq("task_id", task_id)
        .order("created_at")
        .execute()
        .data
    )


def create_comment(task_id: str, user_id: str, body: str) -> dict:
    sb = get_client()
    res = sb.table("comments").insert(
        {"task_id": task_id, "user_id": user_id, "body": body.strip()}
    ).execute()
    return res.data[0]


# ---------------------------------------------------------------
# Digital assets payment tracker
# ---------------------------------------------------------------
def list_digital_assets() -> list:
    sb = get_client()
    return (
        sb.table("digital_assets")
        .select("*, owner:profiles!digital_assets_owner_id_fkey(full_name)")
        .order("due_date")
        .execute()
        .data
    )


def create_digital_asset(
    service_type: str,
    service_type_other: Optional[str],
    entity: str,
    owner_id: Optional[str],
    billing_cycle: str,
    invoice_amount: float,
    due_date: str,
    created_by: str,
) -> dict:
    sb = get_client()
    res = sb.table("digital_assets").insert(
        {
            "service_type": service_type,
            "service_type_other": service_type_other,
            "entity": entity.strip(),
            "owner_id": owner_id,
            "billing_cycle": billing_cycle,
            "invoice_amount": invoice_amount,
            "due_date": due_date,
            "created_by": created_by,
        }
    ).execute()
    return res.data[0]


def update_digital_asset(asset_id: str, **fields) -> dict:
    sb = get_client()
    res = sb.table("digital_assets").update(fields).eq("id", asset_id).execute()
    return res.data[0]


def delete_digital_asset(asset_id: str) -> None:
    sb = get_client()
    sb.table("digital_assets").delete().eq("id", asset_id).execute()


def claim_asset_reminder(asset_id: str, due_date: str) -> bool:
    """Atomically mark an asset's reminder as sent for this due date.
    Returns True only for the one caller that flipped it, so concurrent
    sessions don't send duplicate emails."""
    sb = get_client()
    res = (
        sb.table("digital_assets")
        .update({"reminder_sent_for": due_date})
        .eq("id", asset_id)
        .or_(f"reminder_sent_for.is.null,reminder_sent_for.neq.{due_date}")
        .execute()
    )
    return bool(res.data)


def release_asset_reminder(asset_id: str) -> None:
    """Undo a claim when the email failed to send, so it is retried later."""
    update_digital_asset(asset_id, reminder_sent_for=None)


# ---------------------------------------------------------------
# Activity / Reports -- "what did a user do in period X"
# ---------------------------------------------------------------
def get_user_activity(user_id: str, start: dt.date, end: dt.date) -> list:
    sb = get_client()
    start_iso = dt.datetime.combine(start, dt.time.min).isoformat()
    end_iso = dt.datetime.combine(end, dt.time.max).isoformat()
    res = (
        sb.table("task_activity")
        .select("*, tasks(task_key, title), projects(key, name)")
        .eq("user_id", user_id)
        .gte("created_at", start_iso)
        .lte("created_at", end_iso)
        .order("created_at", desc=True)
        .execute()
    )
    return res.data


def get_tasks_completed_in_range(user_id: str, start: dt.date, end: dt.date) -> list:
    sb = get_client()
    start_iso = dt.datetime.combine(start, dt.time.min).isoformat()
    end_iso = dt.datetime.combine(end, dt.time.max).isoformat()
    res = (
        sb.table("tasks")
        .select("*")
        .eq("assignee_id", user_id)
        .gte("completed_at", start_iso)
        .lte("completed_at", end_iso)
        .execute()
    )
    return res.data
