"""
Supabase client + all data-access helpers used across the app.
Every read/write in the app goes through a function in this file.
"""
import datetime as dt
import os
import re
import uuid
from typing import Optional

import streamlit as st
from supabase import create_client, Client


def get_client() -> Client:
    """One Supabase client per browser session. The client holds the signed-in
    user's auth token, so it must not be shared across sessions (that would make
    every visitor act as whoever signed in last)."""
    if "sb_client" not in st.session_state:
        st.session_state["sb_client"] = create_client(
            st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"]
        )
    return st.session_state["sb_client"]


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
# Compliance tracker (entities -> items -> sub-items). Only admin and
# compliance users can read/write these tables (enforced by RLS).
# ---------------------------------------------------------------
def list_compliance_entities() -> list:
    sb = get_client()
    return (
        sb.table("compliance_entities").select("*")
        .order("kind").order("sort_order").order("name")
        .execute().data
    )


def create_compliance_entity(kind: str, name: str, details: list, created_by: str) -> dict:
    sb = get_client()
    res = sb.table("compliance_entities").insert(
        {"kind": kind, "name": name.strip(), "details": details, "created_by": created_by}
    ).execute()
    return res.data[0]


def update_compliance_entity(entity_id: str, **fields) -> dict:
    sb = get_client()
    res = sb.table("compliance_entities").update(fields).eq("id", entity_id).execute()
    return res.data[0]


def delete_compliance_entity(entity_id: str) -> None:
    """Deletes the entity and, via FK cascade, all its items, sub-items and
    document rows; then removes those documents' files from storage."""
    sb = get_client()
    item_ids = [
        r["id"] for r in
        sb.table("compliance_items").select("id").eq("entity_id", entity_id).execute().data
    ]
    paths = [
        r["storage_path"] for r in
        sb.table("compliance_documents").select("storage_path").eq("entity_id", entity_id).execute().data
    ] + _document_paths_for_items(item_ids)
    sb.table("compliance_entities").delete().eq("id", entity_id).execute()
    _remove_document_files(paths)


def list_compliance_items() -> list:
    """Every item and sub-item (flat; sub-items have parent_id set)."""
    sb = get_client()
    return (
        sb.table("compliance_items").select("*")
        .order("sort_order").order("created_at")
        .execute().data
    )


def create_compliance_item(created_by: str, **fields) -> dict:
    sb = get_client()
    fields["created_by"] = created_by
    res = sb.table("compliance_items").insert(fields).execute()
    return res.data[0]


def update_compliance_item(item_id: str, **fields) -> dict:
    sb = get_client()
    fields["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    res = sb.table("compliance_items").update(fields).eq("id", item_id).execute()
    return res.data[0]


def delete_compliance_item(item_id: str) -> None:
    """Deletes the item and, via FK cascade, its sub-items and document rows;
    then removes those documents' files from storage."""
    sb = get_client()
    sub_ids = [
        r["id"] for r in
        sb.table("compliance_items").select("id").eq("parent_id", item_id).execute().data
    ]
    paths = _document_paths_for_items([item_id] + sub_ids)
    sb.table("compliance_items").delete().eq("id", item_id).execute()
    _remove_document_files(paths)


# ---------------------------------------------------------------
# Compliance documents: files in the private "compliance-docs" Storage
# bucket, one compliance_documents row per file. Attached to either an
# item or an entity.
# ---------------------------------------------------------------
COMPLIANCE_DOCS_BUCKET = "compliance-docs"
COMPLIANCE_DOC_MAX_BYTES = 50 * 1024 * 1024  # Supabase Free plan per-file limit


def list_compliance_documents() -> list:
    sb = get_client()
    return sb.table("compliance_documents").select("*").order("created_at").execute().data


def upload_compliance_document(
    uploaded_by: str, file_name: str, data: bytes, content_type: Optional[str],
    item_id: Optional[str] = None, entity_id: Optional[str] = None,
) -> dict:
    """Store the file, then record it. The storage key is a random id (the
    original name, which may contain any characters, is kept in the row)."""
    sb = get_client()
    ext = os.path.splitext(file_name)[1].lower()
    if not re.fullmatch(r"\.[a-z0-9]{1,10}", ext):
        ext = ""
    path = f"{item_id or entity_id}/{uuid.uuid4().hex}{ext}"
    content_type = content_type or "application/octet-stream"
    bucket = sb.storage.from_(COMPLIANCE_DOCS_BUCKET)
    bucket.upload(path, data, {"content-type": content_type})
    try:
        res = sb.table("compliance_documents").insert({
            "item_id": item_id, "entity_id": entity_id, "file_name": file_name,
            "storage_path": path, "content_type": content_type, "size_bytes": len(data),
            "uploaded_by": uploaded_by,
        }).execute()
    except Exception:
        bucket.remove([path])  # don't leave an unlisted file behind
        raise
    return res.data[0]


def compliance_document_url(doc: dict, expires_in: int = 3600) -> str:
    """Short-lived download link; it stops working after `expires_in` seconds."""
    bucket = get_client().storage.from_(COMPLIANCE_DOCS_BUCKET)
    try:
        # Ask for a download under the original file name.
        res = bucket.create_signed_url(doc["storage_path"], expires_in, {"download": doc["file_name"]})
    except TypeError:  # older storage client without the options argument
        res = bucket.create_signed_url(doc["storage_path"], expires_in)
    return res.get("signedURL") or res.get("signedUrl")


def delete_compliance_document(doc: dict) -> None:
    sb = get_client()
    sb.table("compliance_documents").delete().eq("id", doc["id"]).execute()
    _remove_document_files([doc["storage_path"]])


def _document_paths_for_items(item_ids: list) -> list:
    if not item_ids:
        return []
    sb = get_client()
    rows = sb.table("compliance_documents").select("storage_path").in_("item_id", item_ids).execute().data
    return [r["storage_path"] for r in rows]


def _remove_document_files(paths: list) -> None:
    """Best effort: the rows are already gone, so a failure here only leaves
    unreachable files behind in storage."""
    if not paths:
        return
    try:
        get_client().storage.from_(COMPLIANCE_DOCS_BUCKET).remove(paths)
    except Exception:
        pass


def claim_compliance_reminder(item_id: str, due_date: str) -> bool:
    """Atomically mark an item's reminder as sent for this due date; True only
    for the one caller that flipped it, so sessions don't send duplicates."""
    sb = get_client()
    res = (
        sb.table("compliance_items")
        .update({"reminder_sent_for": due_date})
        .eq("id", item_id)
        .or_(f"reminder_sent_for.is.null,reminder_sent_for.neq.{due_date}")
        .execute()
    )
    return bool(res.data)


def release_compliance_reminder(item_id: str) -> None:
    """Undo a claim when the email failed to send, so it is retried later."""
    sb = get_client()
    sb.table("compliance_items").update({"reminder_sent_for": None}).eq("id", item_id).execute()


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
