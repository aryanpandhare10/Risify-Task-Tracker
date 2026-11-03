"""
Audit document repository (admin only): Insurance, Mutual Funds, PMS, ...
each split by financial year. Files are stored in Google Drive (gdrive.py),
not Supabase, so storage is limited only by the Google account.
"""
import datetime as dt

import streamlit as st

from auth import require_login
import gdrive

profile = require_login()
if profile["role"] != "admin":
    st.error("The audit repository is for admins only.")
    st.stop()

ss = st.session_state
today = dt.date.today()
MAX_UPLOAD_MB = 200  # matches server.maxUploadSize in .streamlit/config.toml

# Built-in categories and the first financial year each one starts from.
# Later years are added automatically every 1 April.
DEFAULT_CATEGORIES = {
    "Insurance": "FY 22-23",
    "Mutual Funds": "FY 24-25",
    "PMS": "FY 24-25",
}

st.title("🗂️ Audit")
st.caption("Document repository by category and financial year. Files are stored in Google Drive "
           f"(folder **{gdrive._root_name()}**), so they can also be synced to a PC with Google Drive for desktop.")

if not gdrive.is_configured():
    st.warning(
        "**Google Drive isn't connected yet.** Add a `[google_drive]` section with `client_id`, "
        "`client_secret` and `refresh_token` to the app's secrets — see *Audit documents* in the README "
        "and run `scripts/drive_auth.py` once to get the values."
    )
    st.stop()


# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------
def _ver(name: str) -> int:
    return ss.get(f"au_ver_{name}", 0)


def _bump(name: str) -> None:
    ss[f"au_ver_{name}"] = _ver(name) + 1


def _flash(msg: str, error: bool = False) -> None:
    ss["au_flash_error" if error else "au_flash"] = msg


def _fmt_size(n) -> str:
    n = int(n or 0)
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


@st.cache_data(ttl=120, show_spinner="Loading documents from Google Drive…")
def _load() -> tuple:
    """(files, category folders). Cached briefly so clicking around doesn't
    hit Drive every time; cleared after any upload / delete."""
    return gdrive.list_files(), gdrive.list_categories()


def _fetch(f: dict) -> None:
    """Button callback: pull one file's bytes so a Save button can offer it."""
    try:
        ss["au_dl"] = {"id": f["id"], "data": gdrive.download_file(f["id"])}
    except Exception as e:
        _flash(f"Couldn't download “{f['name']}”: {e}", error=True)


def _trash(f: dict) -> None:
    try:
        gdrive.trash_file(f["id"])
        _load.clear()
        _flash(f"Deleted “{f['name']}” (restorable from the Google Drive bin for 30 days).")
    except Exception as e:
        _flash(f"Couldn't delete “{f['name']}”: {e}", error=True)


def _file_rows(file_list: list, key: str, show_location: bool = False) -> None:
    """One row per file: name + details, open in Drive, download, delete."""
    for f in file_list:
        props = f.get("appProperties") or {}
        c1, c2, c3, c4 = st.columns([6, 1.4, 1.2, 0.6], vertical_alignment="center")
        where = f"{props.get('category')} › {props.get('fy')} · " if show_location else ""
        by = f" by {props['uploaded_by']}" if props.get("uploaded_by") else ""
        c1.markdown(f"{f['name']}  \n:gray[{where}{_fmt_size(f.get('size'))} · "
                    f"uploaded {(f.get('createdTime') or '')[:10]}{by}]")
        if f.get("webViewLink"):
            c2.link_button("Open in Drive", f["webViewLink"], use_container_width=True)
        if ss.get("au_dl", {}).get("id") == f["id"]:
            c3.download_button(
                "💾 Save", data=ss["au_dl"]["data"], file_name=f["name"],
                mime=f.get("mimeType") or "application/octet-stream",
                key=f"au_save_{key}_{f['id']}", use_container_width=True,
            )
        else:
            c3.button("⬇️ Download", key=f"au_fetch_{key}_{f['id']}", on_click=_fetch, args=(f,),
                      use_container_width=True)
        with c4.popover("🗑️", use_container_width=True):
            st.caption(f"Delete “{f['name']}”? It goes to the Google Drive bin.")
            st.button("Delete file", key=f"au_del_{key}_{f['id']}", type="primary",
                      on_click=_trash, args=(f,))


def _uploader(category: str, fy: str, start_fy: str) -> None:
    key = f"{category}_{fy}"
    uv = _ver(f"up_{key}")
    files = st.file_uploader(
        f"Upload to **{category} › {fy}** — any file type, up to {MAX_UPLOAD_MB} MB each",
        accept_multiple_files=True, key=f"au_up_{key}_{uv}",
    )
    if files and st.button("⬆️ Upload", key=f"au_up_btn_{key}_{uv}", type="primary"):
        done, failed = [], []
        progress = st.progress(0.0, text="Uploading…")
        for n, f in enumerate(files, start=1):
            if f.size > MAX_UPLOAD_MB * 1024 * 1024:
                failed.append(f"{f.name}: larger than {MAX_UPLOAD_MB} MB")
            else:
                try:
                    gdrive.upload_file(
                        f.name, f.getvalue(), f.type, category, fy,
                        start_fy=start_fy, uploaded_by=profile.get("full_name") or "",
                    )
                    done.append(f.name)
                except Exception as e:
                    failed.append(f"{f.name}: {e}")
            progress.progress(n / len(files), text=f"Uploading… {n}/{len(files)}")
        _load.clear()
        if done:
            _flash(f"Uploaded {len(done)} file(s) to {category} › {fy}: " + ", ".join(done))
        if failed:
            _flash("Couldn't upload:\n" + "\n".join(f"- {m}" for m in failed), error=True)
        _bump(f"up_{key}")  # clear the uploader
        st.rerun()


# ---------------------------------------------------------------
# Data
# ---------------------------------------------------------------
if "au_flash" in ss:
    st.success(ss.pop("au_flash"))
if "au_flash_error" in ss:
    st.error(ss.pop("au_flash_error"))

try:
    files, drive_categories = _load()
except Exception as e:
    st.error(f"Couldn't reach Google Drive: {e}")
    st.stop()

categories = dict(DEFAULT_CATEGORIES)
for c in drive_categories:
    categories.setdefault(c["name"], c.get("start_fy") or gdrive.fy_label(gdrive.current_fy_start(today)))

files_by: dict = {}
for f in files:
    p = f.get("appProperties") or {}
    files_by.setdefault((p.get("category"), p.get("fy")), []).append(f)

top1, top2 = st.columns([5, 1], vertical_alignment="bottom")
needle = top1.text_input("🔎 Search all audit documents by file name", key="au_search").strip().lower()
if top2.button("🔄 Refresh", use_container_width=True):
    _load.clear()
    st.rerun()

if needle:
    hits = [f for f in files if needle in f["name"].lower()]
    with st.container(border=True):
        st.markdown(f"**Search results** ({len(hits)})")
        if hits:
            _file_rows(hits, key="search", show_location=True)
        else:
            st.caption("No documents match.")

# ---------------------------------------------------------------
# One tab per category; pick a financial year inside it
# ---------------------------------------------------------------
cat_names = list(categories)
tabs = st.tabs(
    [f"{c} ({sum(len(v) for (fc, _), v in files_by.items() if fc == c)})" for c in cat_names]
    + ["➕ Add category"]
)

for cat, tab in zip(cat_names, tabs):
    with tab:
        start_fy = categories[cat]
        # Every FY from the start year to now, plus any year that has files
        # outside that range, newest first.
        fys = set(gdrive.fy_range(start_fy, today)) | {fy for (fc, fy) in files_by if fc == cat and fy}
        fys = sorted(fys, key=gdrive.fy_start_year, reverse=True)
        fy = st.radio(
            "Financial year", fys, horizontal=True, key=f"au_fy_{cat}",
            format_func=lambda y, c=cat: f"{y} ({len(files_by.get((c, y), []))})",
        )
        fy_files = files_by.get((cat, fy), [])
        with st.container(border=True):
            st.markdown(f"**{cat} › {fy}** — {len(fy_files)} document(s)")
            if fy_files:
                _file_rows(fy_files, key=f"{cat}_{fy}")
            else:
                st.caption("No documents yet.")
            st.divider()
            _uploader(cat, fy, start_fy)

with tabs[-1]:
    st.markdown("Add another document category (e.g. Bank statements, Tax returns). "
                "It gets a folder per financial year, from the start year below up to today.")
    av = _ver("add_cat")
    n1, n2 = st.columns([3, 1])
    new_name = n1.text_input("Category name", key=f"au_new_cat_{av}").strip()
    year_options = [gdrive.fy_label(y) for y in range(gdrive.current_fy_start(today), 2009, -1)]
    new_start = n2.selectbox("First financial year", year_options, key=f"au_new_start_{av}")
    if st.button("Add category", key=f"au_add_cat_{av}", type="primary"):
        if not new_name:
            st.error("Enter a category name.")
        elif new_name.lower() in {c.lower() for c in categories}:
            st.error(f"“{new_name}” already exists.")
        elif any(ch in new_name for ch in "/\\"):
            st.error("Category names can't contain / or \\.")
        else:
            try:
                gdrive.create_category(new_name, new_start)
                _load.clear()
                _bump("add_cat")
                _flash(f"Added category “{new_name}” from {new_start}.")
                st.rerun()
            except Exception as e:
                st.error(f"Couldn't create the folder in Google Drive: {e}")
