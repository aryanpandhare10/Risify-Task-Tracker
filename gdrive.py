"""
Google Drive storage for the Audit document repository (admin only).

Files live in the Drive of the Google account that authorised the app
(see scripts/drive_auth.py), under:

    Risify Audit / <Category> / <FY 24-25> / <file>

so they can be browsed in Drive and synced to a PC with Google Drive for
desktop. The app uses the `drive.file` scope: it can only see files and
folders it created itself. Everything it creates is tagged with
appProperties (risify_audit = root | category | fy | file), which is how it
finds them again, so renaming folders in Drive doesn't break anything.
"""
import datetime as dt
import io
from typing import Optional

import streamlit as st

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
TAG = "risify_audit"
FOLDER_MIME = "application/vnd.google-apps.folder"
_FILE_FIELDS = "id, name, size, mimeType, createdTime, webViewLink, appProperties"


# ---------------------------------------------------------------
# Financial years (India: 1 April - 31 March), labelled "FY 24-25"
# ---------------------------------------------------------------
def fy_label(start_year: int) -> str:
    return f"FY {start_year % 100:02d}-{(start_year + 1) % 100:02d}"


def fy_start_year(label: str) -> int:
    """'FY 24-25' -> 2024."""
    return 2000 + int(label.split()[1].split("-")[0])


def current_fy_start(today: Optional[dt.date] = None) -> int:
    today = today or dt.date.today()
    return today.year if today.month >= 4 else today.year - 1


def fy_range(start_label: str, today: Optional[dt.date] = None) -> list:
    """Every FY from `start_label` up to the current one, newest first. A new
    FY appears on its own each 1 April."""
    return [fy_label(y) for y in range(current_fy_start(today), fy_start_year(start_label) - 1, -1)]


# ---------------------------------------------------------------
# Connection
# ---------------------------------------------------------------
def is_configured() -> bool:
    cfg = st.secrets.get("google_drive", {})
    return all(cfg.get(k) for k in ("client_id", "client_secret", "refresh_token"))


def _service():
    """One Drive client per browser session (the underlying HTTP client
    isn't thread-safe, and Streamlit runs sessions in threads)."""
    if "gdrive_service" not in st.session_state:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        cfg = st.secrets["google_drive"]
        creds = Credentials(
            None, refresh_token=cfg["refresh_token"], token_uri="https://oauth2.googleapis.com/token",
            client_id=cfg["client_id"], client_secret=cfg["client_secret"], scopes=SCOPES,
        )
        st.session_state["gdrive_service"] = build("drive", "v3", credentials=creds, cache_discovery=False)
    return st.session_state["gdrive_service"]


def _root_name() -> str:
    return st.secrets.get("google_drive", {}).get("root_folder_name", "Risify Audit")


def _quote(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "\\'")


def _list(q: str, fields: str) -> list:
    svc, out, token = _service(), [], None
    while True:
        res = svc.files().list(
            q=q, spaces="drive", fields=f"nextPageToken, files({fields})",
            pageSize=1000, pageToken=token,
        ).execute()
        out += res.get("files", [])
        token = res.get("nextPageToken")
        if not token:
            return out


def _tag_query(kind: str) -> str:
    return f"appProperties has {{ key='{TAG}' and value='{kind}' }} and trashed=false"


# ---------------------------------------------------------------
# Folders
# ---------------------------------------------------------------
def _ensure_folder(name: str, kind: str, parent: Optional[str], props: Optional[dict] = None) -> str:
    """Find (by tag + name + parent) or create a folder; returns its id."""
    cache = st.session_state.setdefault("gdrive_folders", {})
    ck = (kind, name, parent)
    if ck in cache:
        return cache[ck]
    q = f"mimeType='{FOLDER_MIME}' and name='{_quote(name)}' and {_tag_query(kind)}"
    if parent:
        q += f" and '{parent}' in parents"
    found = _list(q, "id")
    if found:
        fid = found[0]["id"]
    else:
        body = {"name": name, "mimeType": FOLDER_MIME, "appProperties": {TAG: kind, **(props or {})}}
        if parent:
            body["parents"] = [parent]
        fid = _service().files().create(body=body, fields="id").execute()["id"]
    cache[ck] = fid
    return fid


def _root_id() -> str:
    return _ensure_folder(_root_name(), "root", None)


def list_categories() -> list:
    """Category folders already in Drive: [{'name', 'start_fy'}]."""
    rows = _list(f"mimeType='{FOLDER_MIME}' and {_tag_query('category')}", "name, appProperties")
    return [
        {"name": r["name"], "start_fy": (r.get("appProperties") or {}).get("start_fy")}
        for r in rows
    ]


def create_category(name: str, start_fy: str) -> None:
    _ensure_folder(name, "category", _root_id(), {"start_fy": start_fy})


def _fy_folder_id(category: str, fy: str, start_fy: Optional[str]) -> str:
    cat_id = _ensure_folder(category, "category", _root_id(), {"start_fy": start_fy} if start_fy else None)
    return _ensure_folder(fy, "fy", cat_id, {"category": category})


# ---------------------------------------------------------------
# Files
# ---------------------------------------------------------------
def list_files() -> list:
    """Every audit file the app uploaded (not in the bin), newest first.
    Each has appProperties 'category' and 'fy'."""
    files = _list(f"mimeType!='{FOLDER_MIME}' and {_tag_query('file')}", _FILE_FIELDS)
    return sorted(files, key=lambda f: f.get("createdTime") or "", reverse=True)


def upload_file(
    file_name: str, data: bytes, mime_type: Optional[str], category: str, fy: str,
    start_fy: Optional[str] = None, uploaded_by: str = "",
) -> dict:
    from googleapiclient.http import MediaIoBaseUpload

    parent = _fy_folder_id(category, fy, start_fy)
    media = MediaIoBaseUpload(
        io.BytesIO(data), mimetype=mime_type or "application/octet-stream",
        resumable=True, chunksize=8 * 1024 * 1024,
    )
    body = {
        "name": file_name, "parents": [parent],
        "appProperties": {TAG: "file", "category": category, "fy": fy, "uploaded_by": uploaded_by[:100]},
    }
    return _service().files().create(body=body, media_body=media, fields=_FILE_FIELDS).execute()


def download_file(file_id: str) -> bytes:
    from googleapiclient.http import MediaIoBaseDownload

    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, _service().files().get_media(fileId=file_id))
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()


def trash_file(file_id: str) -> None:
    """Move to the Drive bin (restorable from Drive for 30 days)."""
    _service().files().update(fileId=file_id, body={"trashed": True}).execute()
