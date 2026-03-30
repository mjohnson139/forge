from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re
from typing import Any


@dataclass(frozen=True)
class OperatorProfile:
    name: str
    timezone: str
    style: str
    approval_rules: str


def load_operator_profile(repo_root: str | Path) -> OperatorProfile:
    user_md = (Path(repo_root) / "USER.md").read_text(encoding="utf-8")
    values = {
        "name": _extract_bullet_value(user_md, "Name") or "",
        "timezone": _extract_bullet_value(user_md, "Timezone") or "UTC",
        "style": _extract_bullet_value(user_md, "Style") or "",
        "approval_rules": _extract_section_text(user_md, "Approval Rules"),
    }
    return OperatorProfile(**values)


def read_lens_history(
    repo_root: str | Path,
    *,
    task_id: str | None = None,
    limit: int = 10,
) -> list[str]:
    history_path = Path(repo_root) / "logs" / "history.jsonl"
    if not history_path.exists():
        return []

    lines = history_path.read_text(encoding="utf-8").splitlines()
    entries: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        entry = json.loads(line)
        if task_id is not None and entry.get("task_id") != task_id:
            continue
        entries.append(entry)

    return [str(entry.get("summary", "")) for entry in entries[-limit:]]


def assemble_brief(
    task: dict[str, Any],
    *,
    repo_root: str | Path,
    tool_statuses: list[dict[str, Any]],
    memory_store: Any,
    runtime_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    task_id = str(task["id"])
    operator = load_operator_profile(repo_root)
    history = read_lens_history(repo_root, task_id=task_id, limit=10)
    memory = {
        "task_memory": memory_store.load_task_memory(task_id),
        "active_run": memory_store.find_active_run(task_id),
        "recipe": memory_store.find_recipe(task),
    }
    context = {
        "overrides": _load_overrides(repo_root),
    }
    if runtime_context:
        context.update(runtime_context)

    return {
        "task": task,
        "history": history,
        "memory": memory,
        "operator": {
            "name": operator.name,
            "timezone": operator.timezone,
            "style": operator.style,
            "approval_rules": operator.approval_rules,
        },
        "tools": tool_statuses,
        "context": context,
        "assembled_at": _now_iso(),
    }


def brief_to_context_flags(brief: dict[str, Any]) -> list[str]:
    flags: list[str] = []

    def visit(prefix: str, value: Any) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                visit(f"{prefix}_{key}" if prefix else key, nested)
            return
        if isinstance(value, list):
            if value:
                flags.append(f"{prefix}={json.dumps(value)}")
            return
        if value is None:
            return
        flags.append(f"{prefix}={value}")

    visit("", brief)
    return flags


def _load_overrides(repo_root: str | Path) -> list[dict[str, Any]]:
    inbox_path = Path(repo_root) / "forge" / "uplink" / "inbox.json"
    if not inbox_path.exists():
        return []
    data = json.loads(inbox_path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def _extract_bullet_value(markdown: str, label: str) -> str | None:
    pattern = rf"^- \*\*{re.escape(label)}:\*\* (.+)$"
    match = re.search(pattern, markdown, flags=re.MULTILINE)
    return match.group(1).strip() if match else None


def _extract_section_text(markdown: str, header: str) -> str:
    pattern = rf"^## {re.escape(header)}\n(?P<body>.*?)(?:\n## |\Z)"
    match = re.search(pattern, markdown, flags=re.MULTILINE | re.DOTALL)
    return match.group("body").strip() if match else ""


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
