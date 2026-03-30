from __future__ import annotations

from typing import Any


def build_heartbeat_message(
    *,
    summary: str,
    task: dict[str, Any] | None,
    run_state: str,
    next_action: str,
) -> str:
    lines = ["Forge heartbeat", f"- State: `{run_state}`", f"- Summary: {summary}"]
    if task is not None:
        lines.append(f"- Task: `{task['id']}` {task['title']}")
    lines.append(f"- Next action: {next_action}")
    return "\n".join(lines)


def build_failure_message(
    *,
    task: dict[str, Any] | None,
    run_state: str,
    blocker: str,
    next_action: str,
) -> str:
    lines = ["Forge failure", f"- State: `{run_state}`", f"- Blocker: {blocker}"]
    if task is not None:
        lines.append(f"- Task: `{task['id']}` {task['title']}")
    lines.append(f"- Next action: {next_action}")
    return "\n".join(lines)
