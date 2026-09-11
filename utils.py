"""
Shared constants and small helpers used across pages.
"""

STATUS_OPTIONS = ["todo", "in_progress", "in_review", "done"]
STATUS_LABELS = {
    "todo": "To Do",
    "in_progress": "In Progress",
    "in_review": "In Review",
    "done": "Done",
}

PRIORITY_OPTIONS = ["lowest", "low", "medium", "high", "highest"]
PRIORITY_ICONS = {
    "lowest": "🔽",
    "low": "🔻",
    "medium": "➖",
    "high": "🔺",
    "highest": "🔴",
}

# Issue types selectable when creating a top-level item.
# "subtask" is created only from within a parent task, not from this list.
ISSUE_TYPE_ROOT_OPTIONS = ["task", "story", "bug"]
ISSUE_TYPE_ICONS = {
    "task": "✅",
    "subtask": "↳",
    "bug": "🐞",
    "story": "📘",
}


def name_to_id_map(profiles: list) -> dict:
    return {p["full_name"]: p["id"] for p in profiles}


def checkbox_filter(st, label: str, options: list, key_prefix: str, format_func=None, per_row: int = 4) -> list:
    """Render `options` as a row of plain checkboxes (all checked by default)
    instead of a multiselect's colored tag pills. Returns the checked options."""
    st.caption(label)
    selected = []
    cols = st.columns(min(per_row, len(options)) or 1)
    for i, opt in enumerate(options):
        text = format_func(opt) if format_func else str(opt)
        if cols[i % len(cols)].checkbox(text, value=True, key=f"{key_prefix}_{opt}"):
            selected.append(opt)
    return selected


def project_progress(tasks: list) -> dict:
    """Aggregate progress for one project's tasks (flat list, subtasks included).

    Hours completion = sum(logged_hours) / sum(estimate_hours) across the
    tasks — reflects actual hours worked (self-reported by assignees) against
    what was estimated, independent of task status.
    """
    total_tasks = len(tasks)
    done_tasks = [t for t in tasks if t["status"] == "done"]
    total_hours = sum(float(t.get("estimate_hours") or 0) for t in tasks)
    logged_hours = sum(float(t.get("logged_hours") or 0) for t in tasks)

    return {
        "total_tasks": total_tasks,
        "done_tasks": len(done_tasks),
        "task_pct": (len(done_tasks) / total_tasks * 100) if total_tasks else 0.0,
        "total_hours": total_hours,
        "logged_hours": logged_hours,
        "hours_pct": (logged_hours / total_hours * 100) if total_hours else 0.0,
    }


def per_assignee_progress(tasks: list, id_to_name: dict) -> list:
    """Group a project's tasks by assignee and compute progress per person.
    Returns a list of dicts sorted by full name, "Unassigned" last."""
    by_assignee: dict = {}
    for t in tasks:
        aid = t.get("assignee_id")
        by_assignee.setdefault(aid, []).append(t)

    rows = []
    for aid, ts in by_assignee.items():
        prog = project_progress(ts)
        rows.append({
            "name": id_to_name.get(aid, "Unassigned") if aid else "Unassigned",
            **prog,
        })

    rows.sort(key=lambda r: (r["name"] == "Unassigned", r["name"]))
    return rows
