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
