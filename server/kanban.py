"""Kanban board reader."""

import os
import sqlite3
from server.config import HERMES_HOME
# =============================================================================
# Kanban reader — clean grouped structure for the frontend
# =============================================================================

# Status → column mapping
_STATUS_TO_COLUMN = {
    "triage":  "triage",
    "todo":    "todo",
    "ready":   "ready",
    "running": "running",
    "blocked": "blocked",
    "done":    "done",
    "archived":"archived",
}

_KANBAN_COLUMNS = ["triage", "todo", "ready", "running", "blocked", "done", "archived"]

_PRIORITY_NAMES = {0: "low", 1: "medium", 2: "high", 3: "critical"}


def _read_kanban_tasks(db_path):
    """Read tasks from a kanban.db. Returns list of task dicts or None on failure."""
    try:
        db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        db.execute("PRAGMA query_only=1")
        rows = db.execute(
            "SELECT id, title, body, assignee, status, priority, "
            "created_at, started_at, completed_at, "
            "workspace_path, skills, result, created_by, model_override "
            "FROM tasks ORDER BY priority DESC, created_at ASC"
        ).fetchall()
        db.close()

        tasks = []
        for r in rows:
            tid, title, body, assignee, status, priority, \
                created_at, started_at, completed_at, \
                workspace_path, skills, result, created_by, model_override = r
            tasks.append({
                "id": tid,
                "title": title or "",
                "body": body or "",
                "assignee": assignee or "",
                "status": status or "todo",
                "priority": priority or 0,
                "priority_name": _PRIORITY_NAMES.get(priority or 0, "low"),
                "created_at": created_at,
                "started_at": started_at,
                "completed_at": completed_at,
                "workspace_path": workspace_path or "",
                "skills": skills or "",
                "result": result or "",
                "created_by": created_by or "",
                "model_override": model_override or "",
                "labels": [],
            })
        return tasks
    except Exception:
        return None


def read_kanban_boards(errors_out):
    """Read all kanban boards (root + per-board) and group tasks by status column.
    Returns {"boards": {name: {name, columns: {backlog,in_progress,done}, task_count}}, "default_board": str}.
    Mutates errors_out on failures.
    """
    boards = {}
    board_names = []

    # Board-specific kanban DBs first (these have the real data)
    boards_dir = os.path.join(HERMES_HOME, "kanban", "boards")
    try:
        for board_name in sorted(os.listdir(boards_dir)):
            board_db = os.path.join(boards_dir, board_name, "kanban.db")
            if os.path.isfile(board_db):
                tasks = _read_kanban_tasks(board_db)
                if tasks is not None:
                    columns = {c: [] for c in _KANBAN_COLUMNS}
                    for t in tasks:
                        col = _STATUS_TO_COLUMN.get(t["status"], "backlog")
                        columns[col].append(t)
                    boards[board_name] = {
                        "name": board_name,
                        "columns": columns,
                        "task_count": len(tasks),
                    }
                    board_names.append(board_name)
                else:
                    errors_out.append(f"kanban board '{board_name}': read failed")
    except Exception as e:
        errors_out.append(f"kanban boards directory: {e}")

    # Root kanban.db (usually empty, but include if it has tasks)
    root_db = os.path.join(HERMES_HOME, "kanban.db")
    if os.path.isfile(root_db):
        tasks = _read_kanban_tasks(root_db)
        if tasks is not None and len(tasks) > 0:
            columns = {c: [] for c in _KANBAN_COLUMNS}
            for t in tasks:
                col = _STATUS_TO_COLUMN.get(t["status"], "backlog")
                columns[col].append(t)
            boards["default"] = {
                "name": "default",
                "columns": columns,
                "task_count": len(tasks),
            }
            board_names.append("default")

    # Default board — first one with tasks, or first alphabetically
    first_with_tasks = None
    for name in board_names:
        if boards.get(name, {}).get("task_count", 0) > 0:
            first_with_tasks = name
            break
    default_board = first_with_tasks or (board_names[0] if board_names else "default")

    return {
        "boards": boards,
        "default_board": default_board,
    }
