from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib import request


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


class SlackNotifier:
    def __init__(self, *, repo_root: str | Path, sender: Any | None = None) -> None:
        self.repo_root = Path(repo_root)
        self.sender = sender or _post_webhook

    def notify(self, message: str) -> bool:
        webhook_url = _resolve_webhook_url(self.repo_root)
        if webhook_url is None:
            return False
        self.sender(webhook_url, {"text": message})
        return True


def _resolve_webhook_url(repo_root: Path) -> str | None:
    env_value = os.getenv("FORGE_SLACK_WEBHOOK_URL")
    if env_value:
        return env_value

    tools_md = repo_root / "TOOLS.md"
    if not tools_md.exists():
        return None

    for line in tools_md.read_text(encoding="utf-8").splitlines():
        if line.startswith("Webhook URL:"):
            _, _, remainder = line.partition(":")
            value = remainder.strip()
            if value.startswith("`") and value.endswith("`"):
                value = value[1:-1]
            return value or None
    return None


def _post_webhook(webhook_url: str, payload: dict[str, str]) -> None:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        webhook_url,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with request.urlopen(req) as response:
        response.read()
