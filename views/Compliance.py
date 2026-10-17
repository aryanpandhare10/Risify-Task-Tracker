"""
Compliance tracker: entities (companies / individuals) -> compliance items
(licences, filings, visas, ...) -> sub-tasks. Everything is editable in the
page, and any item or entity can carry extra free-form "field: value" details.
"""
import datetime as dt

import pandas as pd
import streamlit as st

from auth import require_login
from db import (
    list_compliance_entities, create_compliance_entity, update_compliance_entity,
    delete_compliance_entity, list_compliance_items, create_compliance_item,
    update_compliance_item, delete_compliance_item,
)
import utils

profile = require_login()
if profile["role"] not in ("admin", "compliance"):
    st.error("You don't have access to the compliance tracker.")
    st.stop()

ss = st.session_state
today = dt.date.today()

NEW_CATEGORY = "➕ New category…"
DEFAULT_CATEGORIES = ["Documents", "Compliances", "Personal documents"]
STATUS_BY_LABEL = {v: k for k, v in utils.COMPLIANCE_STATUS_LABELS.items()}

# Starter checklists offered when a new entity is added.
ENTITY_TEMPLATE_DETAILS = {
    "company": ["Directors", "Shareholders", "% Holding", "Rate per share", "Quantity",
                "Incorporation date", "License No."],
    "individual": ["Employee of"],
}
ENTITY_TEMPLATE_ITEMS = {
    "company": [
        ("Documents", "Business License / Membership Certificate"),
        ("Documents", "E-Establishment"),
        ("Documents", "Office Agreement"),
        ("Documents", "PI Indemnity"),
        ("Compliances", "Corporate tax Filing date"),
        ("Compliances", "FATCA & CRS"),
    ],
    "individual": [
        ("Personal documents", "Insurance Card"),
        ("Personal documents", "Visa"),
        ("Personal documents", "Emirates ID"),
        ("Personal documents", "Tenancy Contract"),
    ],
}


# ---------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------
def _ver(name: str) -> int:
    return ss.get(f"cp_ver_{name}", 0)


def _bump(name: str) -> None:
    """Bump a version counter that is part of some widgets' keys, so those
    widgets (and any table row selection) start fresh on the next run."""
    ss[f"cp_ver_{name}"] = _ver(name) + 1


def _flash(msg: str) -> None:
    ss["cp_flash"] = msg


def _to_iso(v):
    """date / Timestamp / NaT / None -> 'YYYY-MM-DD' or None."""
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    if isinstance(v, pd.Timestamp):
        v = v.date()
    if isinstance(v, dt.datetime):
        v = v.date()
    return v.isoformat() if isinstance(v, dt.date) else (str(v) or None)


def _clean_text(v):
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    v = str(v).strip()
    return v or None


def _date_or_none(iso):
    return dt.date.fromisoformat(iso) if iso else None


def _pairs_editor(pairs: list, key: str):
    """Editable two-column 'Field / Value' table for extra details. Returns
    the cleaned list of {'field', 'value'} pairs."""
    df = pd.DataFrame(
        [{"Field": p.get("field", ""), "Value": p.get("value", "")} for p in (pairs or [])],
        columns=["Field", "Value"],
    ).astype("object")
    edited = st.data_editor(
        df, key=key, num_rows="dynamic", hide_index=True, use_container_width=True,
        column_config={
            "Field": st.column_config.TextColumn("Field", help="e.g. Policy no., Provider, Portal login"),
            "Value": st.column_config.TextColumn("Value"),
        },
    )
    out = []
    for row in edited.to_dict("records"):
        field = _clean_text(row.get("Field"))
        if field:
            out.append({"field": field, "value": _clean_text(row.get("Value")) or ""})
    return out


def _category_input(label: str, current, categories: list, key: str):
    """Selectbox of known categories plus a 'new category' text box."""
    options = categories + [NEW_CATEGORY]
    index = options.index(current) if current in options else 0
    choice = st.selectbox(label, options, index=index, key=f"{key}_sel")
    if choice == NEW_CATEGORY:
        return _clean_text(st.text_input("New category name", key=f"{key}_new"))
    return choice


def _mark_done(item: dict) -> None:
    """Recurring items roll forward one cycle (due date and start date) and go
    back to Pending; one-time / no-frequency items are set to Done."""
    months = utils.COMPLIANCE_FREQUENCY_MONTHS.get(item.get("frequency"))
    if months and item.get("due_date"):
        nxt = utils.add_months(dt.date.fromisoformat(item["due_date"]), months)
        fields = {"due_date": nxt.isoformat(), "status": "pending", "last_done_on": today.isoformat()}
        if item.get("start_date"):
            fields["start_date"] = utils.add_months(
                dt.date.fromisoformat(item["start_date"]), months
            ).isoformat()
        update_compliance_item(item["id"], **fields)
        _flash(f"Marked “{item['particulars']}” done — next due {nxt}.")
    else:
        update_compliance_item(item["id"], status="done", last_done_on=today.isoformat())
        _flash(f"Marked “{item['particulars']}” done.")
    _bump("items_table")


# ---------------------------------------------------------------
# Data
# ---------------------------------------------------------------
entities = list_compliance_entities()
items = list_compliance_items()
entity_by_id = {e["id"]: e for e in entities}
entity_ids = [e["id"] for e in entities]
item_by_id = {i["id"]: i for i in items}
roots = [i for i in items if not i.get("parent_id")]
children_by_parent: dict = {}
for i in items:
    if i.get("parent_id"):
        children_by_parent.setdefault(i["parent_id"], []).append(i)
categories = sorted(set(DEFAULT_CATEGORIES) | {i["category"] for i in items if i.get("category")})


def _entity_label(eid) -> str:
    e = entity_by_id.get(eid)
    return e["name"] if e else "—"


def _item_title(it: dict) -> str:
    parent = item_by_id.get(it.get("parent_id"))
    return f"{parent['particulars']} › {it['particulars']}" if parent else it["particulars"]


# ---------------------------------------------------------------
# Header, alerts
# ---------------------------------------------------------------
st.title("🛡️ Compliance Tracker")

if "cp_flash" in ss:
    st.success(ss.pop("cp_flash"))

alerts = {i["id"]: utils.compliance_alert(i, today) for i in items}
overdue = sorted((i for i in items if alerts[i["id"]] == "overdue"), key=lambda i: i["due_date"])
due_soon = sorted((i for i in items if alerts[i["id"]] == "due_soon"), key=lambda i: i["due_date"])

m1, m2, m3, m4 = st.columns(4)
m1.metric("Overdue", len(overdue))
m2.metric("Due soon", len(due_soon))
m3.metric("Open items", sum(1 for i in items if i["status"] not in utils.COMPLIANCE_CLOSED_STATUSES))
m4.metric("Entities", len(entities))

if overdue:
    st.error("**Overdue**\n" + "\n".join(
        f"- **{_entity_label(i['entity_id'])}** — {_item_title(i)}: due {i['due_date']} "
        f"({utils.due_when(utils.compliance_days_left(i, today))})"
        for i in overdue
    ))
if due_soon:
    st.warning("**Due soon**\n" + "\n".join(
        f"- **{_entity_label(i['entity_id'])}** — {_item_title(i)}: due {i['due_date']} "
        f"({utils.due_when(utils.compliance_days_left(i, today))})"
        for i in due_soon
    ))

tab_tracker, tab_entities, tab_add = st.tabs(["📅 Tracker", "🏢 Entities", "➕ Add item"])

# ===============================================================
# Tracker tab — all top-level items; click a row to edit it and
# manage its sub-tasks and extra details.
# ===============================================================
with tab_tracker:
    if not entities:
        st.info("No entities yet — add one on the **🏢 Entities** tab.")
    elif not roots:
        st.info("No compliance items yet — add one on the **➕ Add item** tab.")
    else:
        with st.expander("🔎 Filters"):
            fcol1, fcol2 = st.columns(2)
            f_entity = fcol1.selectbox(
                "Entity", [None] + entity_ids, key="cp_f_entity",
                format_func=lambda e: "All entities" if e is None else _entity_label(e),
            )
            f_search = fcol2.text_input("Search particulars / remarks", key="cp_f_search")
            f_kind = utils.checkbox_filter(
                st, "Entity type", utils.ENTITY_KIND_OPTIONS, key_prefix="cp_f_kind",
                format_func=lambda k: utils.ENTITY_KIND_LABELS[k],
            )
            f_category = utils.checkbox_filter(st, "Category", categories, key_prefix="cp_f_cat")
            f_status = utils.checkbox_filter(
                st, "Status", utils.COMPLIANCE_STATUS_OPTIONS, key_prefix="cp_f_status",
                format_func=lambda s: utils.COMPLIANCE_STATUS_LABELS[s],
            )
            f_alert_only = st.toggle("Only overdue / due soon", key="cp_f_alert_only")

        needle = (f_search or "").strip().lower()
        shown = [
            i for i in roots
            if (f_entity is None or i["entity_id"] == f_entity)
            and entity_by_id.get(i["entity_id"], {}).get("kind") in f_kind
            and (not i.get("category") or i["category"] in f_category)
            and i["status"] in f_status
            and (not f_alert_only or alerts[i["id"]] in ("overdue", "due_soon"))
            and (not needle or needle in (i["particulars"] + " " + (i.get("remarks") or "")).lower())
        ]
        # Keep entity order from the Entities tab, then the item's own order.
        entity_rank = {eid: n for n, eid in enumerate(entity_ids)}
        shown.sort(key=lambda i: (entity_rank.get(i["entity_id"], 0), i.get("sort_order") or 0,
                                  i.get("category") or ""))

        if not shown:
            st.caption(f"No items match the filters (0 of {len(roots)}).")
        else:
            shown_alerts = [alerts[i["id"]] for i in shown]
            rows = []
            for n, i in enumerate(shown, start=1):
                subs = children_by_parent.get(i["id"], [])
                rows.append({
                    "S.No.": n,
                    "Entity": _entity_label(i["entity_id"]),
                    "Category": i.get("category") or "",
                    "Particulars": i["particulars"],
                    "Frequency": utils.COMPLIANCE_FREQUENCY_LABELS.get(i.get("frequency"), "Not set"),
                    "Start date": i.get("start_date") or "",
                    "Due / expiry date": i.get("due_date") or "",
                    "Alert": utils.compliance_alert_label(i, today),
                    "Status": utils.COMPLIANCE_STATUS_LABELS.get(i["status"], i["status"]),
                    "Sub-tasks": (
                        f"{sum(1 for s in subs if s['status'] in utils.COMPLIANCE_CLOSED_STATUSES)}/{len(subs)}"
                        if subs else ""
                    ),
                    "Remarks": i.get("remarks") or "",
                    "Extra details": utils.pairs_to_text(i.get("extra")),
                })
            table_df = pd.DataFrame(rows)

            def _alert_colors(col: pd.Series) -> list:
                return [
                    f"color: {utils.COMPLIANCE_ALERT_COLORS[a]}" if utils.COMPLIANCE_ALERT_COLORS[a] else ""
                    for a in shown_alerts
                ]

            event = st.dataframe(
                table_df.style.apply(_alert_colors, subset=["Due / expiry date", "Alert", "Status"]),
                use_container_width=True, hide_index=True,
                on_select="rerun", selection_mode="single-row",
                key=f"cp_items_table_{_ver('items_table')}",
            )
            st.caption(f"Showing {len(shown)} of {len(roots)} item(s) · Click a row to edit it and its sub-tasks.")

            sel = event.selection.rows
            if sel and sel[0] < len(shown):
                it = shown[sel[0]]
                k = it["id"]
                rev = f"{k}_{it.get('updated_at')}"  # fresh widgets after any save
                with st.container(border=True):
                    st.markdown(f"#### ✏️ #{sel[0] + 1} — {_entity_label(it['entity_id'])} · {it['particulars']}")
                    if it.get("last_done_on"):
                        st.caption(f"Last marked done on {it['last_done_on']}")

                    c1, c2, c3 = st.columns(3)
                    e_entity = c1.selectbox(
                        "Entity", entity_ids, index=entity_ids.index(it["entity_id"]),
                        format_func=_entity_label, key=f"cp_e_entity_{rev}",
                    )
                    with c2:
                        e_category = _category_input("Category", it.get("category"), categories, f"cp_e_cat_{rev}")
                    e_particulars = c3.text_input("Particulars", value=it["particulars"], key=f"cp_e_part_{rev}")

                    c4, c5, c6, c7, c8 = st.columns(5)
                    e_frequency = c4.selectbox(
                        "Frequency", utils.COMPLIANCE_FREQUENCY_OPTIONS,
                        index=utils.COMPLIANCE_FREQUENCY_OPTIONS.index(it.get("frequency")),
                        format_func=lambda f: utils.COMPLIANCE_FREQUENCY_LABELS[f], key=f"cp_e_freq_{rev}",
                    )
                    e_start = c5.date_input(
                        "Start date", value=_date_or_none(it.get("start_date")), key=f"cp_e_start_{rev}",
                    )
                    e_due = c6.date_input(
                        "Due / expiry date", value=_date_or_none(it.get("due_date")), key=f"cp_e_due_{rev}",
                    )
                    e_status = c7.selectbox(
                        "Status", utils.COMPLIANCE_STATUS_OPTIONS,
                        index=utils.COMPLIANCE_STATUS_OPTIONS.index(it["status"]),
                        format_func=lambda s: utils.COMPLIANCE_STATUS_LABELS[s], key=f"cp_e_status_{rev}",
                    )
                    e_remind = c8.number_input(
                        "Remind (days before)", min_value=0, step=1,
                        value=int(it.get("reminder_days") or 0), key=f"cp_e_remind_{rev}",
                    )
                    e_remarks = st.text_area("Remarks", value=it.get("remarks") or "", key=f"cp_e_remarks_{rev}")
                    st.markdown("**Extra details** — add any field you need (add rows at the bottom).")
                    e_extra = _pairs_editor(it.get("extra"), key=f"cp_e_extra_{rev}")

                    b1, b2, b3, b4 = st.columns([1, 1.6, 1.6, 1])
                    if b1.button("💾 Save", key=f"cp_e_save_{k}", type="primary"):
                        if not _clean_text(e_particulars) or not e_category:
                            st.error("Particulars and category are required.")
                        else:
                            update_compliance_item(
                                k, entity_id=e_entity, category=e_category,
                                particulars=_clean_text(e_particulars), frequency=e_frequency,
                                start_date=_to_iso(e_start), due_date=_to_iso(e_due), status=e_status,
                                reminder_days=int(e_remind), remarks=_clean_text(e_remarks), extra=e_extra,
                            )
                            if e_entity != it["entity_id"]:
                                for s in children_by_parent.get(k, []):
                                    update_compliance_item(s["id"], entity_id=e_entity)
                            _flash(f"Saved “{_clean_text(e_particulars)}”.")
                            _bump("items_table")  # row order may change
                            st.rerun()
                    b2.button(
                        "✅ Mark done", key=f"cp_e_done_{k}", on_click=_mark_done, args=(it,),
                        help="Recurring items roll to the next due date; others are set to Done.",
                    )
                    confirm = b3.checkbox("Confirm delete (incl. sub-tasks)", key=f"cp_e_confirm_{k}")
                    if b4.button("🗑️ Delete", key=f"cp_e_del_{k}", disabled=not confirm):
                        delete_compliance_item(k)
                        _flash(f"Deleted “{it['particulars']}”.")
                        _bump("items_table")
                        st.rerun()

                    # -------- Sub-tasks --------
                    st.divider()
                    st.markdown("**Sub-tasks** — edit cells directly, add rows at the bottom, "
                                "select a row and press Delete to remove it, then **Save sub-tasks**.")
                    subs = children_by_parent.get(k, [])
                    sub_df = pd.DataFrame({
                        "id": pd.Series([s["id"] for s in subs], dtype="object"),
                        "Sub-task": pd.Series([s["particulars"] for s in subs], dtype="object"),
                        "Due date": pd.to_datetime(
                            pd.Series([s.get("due_date") for s in subs], dtype="object"), errors="coerce"
                        ),
                        "Status": pd.Series(
                            [utils.COMPLIANCE_STATUS_LABELS[s["status"]] for s in subs], dtype="object"
                        ),
                        "Remind (days before)": pd.Series(
                            [s.get("reminder_days") for s in subs], dtype="float64"
                        ),
                        "Remarks": pd.Series([s.get("remarks") or "" for s in subs], dtype="object"),
                    })
                    sub_key = f"cp_subs_{k}_{_ver('subs')}"
                    edited_subs = st.data_editor(
                        sub_df, key=sub_key, num_rows="dynamic", hide_index=True, use_container_width=True,
                        column_config={
                            "id": None,
                            "Sub-task": st.column_config.TextColumn("Sub-task", required=True),
                            "Due date": st.column_config.DateColumn("Due date", format="YYYY-MM-DD"),
                            "Status": st.column_config.SelectboxColumn(
                                "Status", options=list(STATUS_BY_LABEL), default="Pending",
                            ),
                            "Remind (days before)": st.column_config.NumberColumn(
                                "Remind (days before)", min_value=0, step=1, format="%d",
                                default=utils.COMPLIANCE_DEFAULT_REMINDER_DAYS,
                            ),
                            "Remarks": st.column_config.TextColumn("Remarks"),
                        },
                    )
                    if st.button("💾 Save sub-tasks", key=f"cp_subs_save_{k}"):
                        orig = {s["id"]: s for s in subs}
                        kept = set()
                        for row in edited_subs.to_dict("records"):
                            rid = row.get("id") if isinstance(row.get("id"), str) else None
                            title = _clean_text(row.get("Sub-task"))
                            if rid:
                                kept.add(rid)
                            if not title:
                                continue  # blank new row, or title cleared: leave as is
                            remind = row.get("Remind (days before)")
                            fields = {
                                "particulars": title,
                                "due_date": _to_iso(row.get("Due date")),
                                "status": STATUS_BY_LABEL.get(row.get("Status"), "pending"),
                                "reminder_days": int(remind) if remind is not None and not pd.isna(remind)
                                else utils.COMPLIANCE_DEFAULT_REMINDER_DAYS,
                                "remarks": _clean_text(row.get("Remarks")),
                            }
                            if rid:
                                o = orig[rid]
                                if any((o.get(f) or None) != (v or None) for f, v in fields.items()):
                                    update_compliance_item(rid, **fields)
                            else:
                                create_compliance_item(
                                    profile["id"], entity_id=it["entity_id"], parent_id=k,
                                    category=it.get("category"), **fields,
                                )
                        for sid in orig:
                            if sid not in kept:
                                delete_compliance_item(sid)
                        _bump("subs")
                        _flash("Sub-tasks saved.")
                        st.rerun()

# ===============================================================
# Entities tab — companies and individuals, with free-form details
# ===============================================================
with tab_entities:
    if entities:
        ent_rows = []
        for n, e in enumerate(entities, start=1):
            e_items = [i for i in items if i["entity_id"] == e["id"]]
            ent_rows.append({
                "S.No.": n,
                "Type": utils.ENTITY_KIND_LABELS.get(e["kind"], e["kind"]),
                "Name": e["name"],
                "Open items": sum(1 for i in e_items if i["status"] not in utils.COMPLIANCE_CLOSED_STATUSES),
                "Overdue": sum(1 for i in e_items if alerts[i["id"]] == "overdue"),
                "Details": utils.pairs_to_text(e.get("details")),
            })
        ent_event = st.dataframe(
            pd.DataFrame(ent_rows), use_container_width=True, hide_index=True,
            on_select="rerun", selection_mode="single-row",
            key=f"cp_entities_table_{_ver('entities_table')}",
        )
        st.caption("Click an entity to edit its name and details.")

        esel = ent_event.selection.rows
        if esel and esel[0] < len(entities):
            ent = entities[esel[0]]
            ek = ent["id"]
            erev = f"{ek}_{len(ent.get('details') or [])}_{ent['name']}"
            with st.container(border=True):
                st.markdown(f"#### ✏️ {ent['name']}")
                ec1, ec2 = st.columns([1, 3])
                ent_kind = ec1.selectbox(
                    "Type", utils.ENTITY_KIND_OPTIONS,
                    index=utils.ENTITY_KIND_OPTIONS.index(ent["kind"]),
                    format_func=lambda x: utils.ENTITY_KIND_LABELS[x], key=f"cp_ent_kind_{erev}",
                )
                ent_name = ec2.text_input("Name", value=ent["name"], key=f"cp_ent_name_{erev}")
                st.markdown("**Details** — add any field you need.")
                ent_details = _pairs_editor(ent.get("details"), key=f"cp_ent_details_{erev}_{_ver('ent_details')}")
                d1, d2, d3 = st.columns([1, 2.5, 1])
                if d1.button("💾 Save", key=f"cp_ent_save_{ek}", type="primary"):
                    if not _clean_text(ent_name):
                        st.error("Name is required.")
                    else:
                        update_compliance_entity(ek, kind=ent_kind, name=_clean_text(ent_name), details=ent_details)
                        _bump("ent_details")
                        _flash(f"Saved {_clean_text(ent_name)}.")
                        st.rerun()
                n_items = sum(1 for i in items if i["entity_id"] == ek)
                ent_confirm = d2.checkbox(
                    f"Confirm delete this entity and its {n_items} item(s)", key=f"cp_ent_confirm_{ek}",
                )
                if d3.button("🗑️ Delete", key=f"cp_ent_del_{ek}", disabled=not ent_confirm):
                    delete_compliance_entity(ek)
                    _bump("entities_table")
                    _flash(f"Deleted {ent['name']}.")
                    st.rerun()
    else:
        st.caption("No entities yet.")

    with st.expander("➕ Add entity", expanded=not entities):
        av = _ver("add_entity")
        na1, na2 = st.columns([1, 3])
        new_kind = na1.selectbox(
            "Type", utils.ENTITY_KIND_OPTIONS, format_func=lambda x: utils.ENTITY_KIND_LABELS[x],
            key=f"cp_new_ent_kind_{av}",
        )
        new_name = na2.text_input("Name", key=f"cp_new_ent_name_{av}")
        st.markdown("**Details** — fill in what you know; add or remove fields freely.")
        new_details = _pairs_editor(
            [{"field": f, "value": ""} for f in ENTITY_TEMPLATE_DETAILS[new_kind]],
            key=f"cp_new_ent_details_{new_kind}_{av}",
        )
        template = ENTITY_TEMPLATE_ITEMS[new_kind]
        add_checklist = st.checkbox(
            "Also add the standard checklist: " + ", ".join(p for _, p in template),
            value=True, key=f"cp_new_ent_checklist_{av}",
        )
        if st.button("Add entity", key=f"cp_new_ent_add_{av}", type="primary"):
            if not _clean_text(new_name):
                st.error("Name is required.")
            else:
                ent = create_compliance_entity(new_kind, new_name, new_details, profile["id"])
                if add_checklist:
                    for n, (cat, particulars) in enumerate(template, start=1):
                        create_compliance_item(
                            profile["id"], entity_id=ent["id"], category=cat,
                            particulars=particulars, sort_order=n,
                        )
                _bump("add_entity")
                _bump("entities_table")
                _flash(f"Added {ent['name']}.")
                st.rerun()

# ===============================================================
# Add item tab
# ===============================================================
with tab_add:
    if not entities:
        st.info("Add an entity first, on the **🏢 Entities** tab.")
    else:
        iv = _ver("add_item")
        a1, a2, a3 = st.columns(3)
        n_entity = a1.selectbox("Entity", entity_ids, format_func=_entity_label, key=f"cp_new_entity_{iv}")
        with a2:
            n_category = _category_input("Category", None, categories, f"cp_new_cat_{iv}")
        n_particulars = a3.text_input("Particulars", key=f"cp_new_part_{iv}")
        a4, a5, a6, a7, a8 = st.columns(5)
        n_frequency = a4.selectbox(
            "Frequency", utils.COMPLIANCE_FREQUENCY_OPTIONS,
            format_func=lambda f: utils.COMPLIANCE_FREQUENCY_LABELS[f], key=f"cp_new_freq_{iv}",
        )
        n_start = a5.date_input("Start date", value=None, key=f"cp_new_start_{iv}")
        n_due = a6.date_input("Due / expiry date", value=None, key=f"cp_new_due_{iv}")
        n_status = a7.selectbox(
            "Status", utils.COMPLIANCE_STATUS_OPTIONS,
            format_func=lambda s: utils.COMPLIANCE_STATUS_LABELS[s], key=f"cp_new_status_{iv}",
        )
        n_remind = a8.number_input(
            "Remind (days before)", min_value=0, step=1,
            value=utils.COMPLIANCE_DEFAULT_REMINDER_DAYS, key=f"cp_new_remind_{iv}",
        )
        n_remarks = st.text_area("Remarks", key=f"cp_new_remarks_{iv}")
        st.markdown("**Extra details** (optional) — add any field you need.")
        n_extra = _pairs_editor([], key=f"cp_new_extra_{iv}")
        st.caption("Sub-tasks can be added after creating the item: click it in the Tracker tab.")
        if st.button("Add item", key=f"cp_new_add_{iv}", type="primary"):
            if not _clean_text(n_particulars) or not n_category:
                st.error("Particulars and category are required.")
            else:
                same_entity = [i for i in roots if i["entity_id"] == n_entity]
                create_compliance_item(
                    profile["id"], entity_id=n_entity, category=n_category,
                    particulars=_clean_text(n_particulars), frequency=n_frequency,
                    start_date=_to_iso(n_start), due_date=_to_iso(n_due), status=n_status,
                    reminder_days=int(n_remind), remarks=_clean_text(n_remarks), extra=n_extra,
                    sort_order=max((i.get("sort_order") or 0 for i in same_entity), default=0) + 1,
                )
                _bump("add_item")
                _bump("items_table")
                _flash(f"Added “{_clean_text(n_particulars)}” for {_entity_label(n_entity)}.")
                st.rerun()
