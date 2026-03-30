from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import subprocess
from typing import Any, Callable, Mapping, Sequence


TASK_STATUSES = ("ready", "in-progress", "in-review", "feedback", "accepted", "idea")


@dataclass(frozen=True)
class Task:
    id: str
    source: str
    title: str
    body: str
    labels: list[str]
    status: str
    updated_at: str
    url: str


@dataclass(frozen=True)
class IntegrationHealth:
    name: str
    status: str
    checked_at: str
    message: str | None = None


CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]


def _default_runner(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _label_names(labels: Sequence[Mapping[str, Any] | str]) -> list[str]:
    names: list[str] = []
    for label in labels:
        if isinstance(label, str):
            names.append(label)
        elif isinstance(label, Mapping):
            value = label.get("name")
            if isinstance(value, str):
                names.append(value)
    return names


def _infer_status(labels: Sequence[str]) -> str:
    for status in TASK_STATUSES:
        if status in labels:
            return status
    return "idea"


def _parse_task_number(task_id: str | int) -> int:
    if isinstance(task_id, int):
        return task_id
    if task_id.startswith("gh-"):
        return int(task_id.removeprefix("gh-"))
    return int(task_id)


def normalize_github_issue(issue: Mapping[str, Any]) -> Task:
    labels = _label_names(issue.get("labels", []))
    return Task(
        id=f"gh-{int(issue['number'])}",
        source="github",
        title=str(issue.get("title", "")),
        body=str(issue.get("body", "")),
        labels=labels,
        status=_infer_status(labels),
        updated_at=str(issue.get("updatedAt", "")),
        url=str(issue.get("url", "")),
    )


def _sort_key(task: Task) -> tuple[str, str]:
    return (task.updated_at, task.id)


class GithubIssueAdapter:
    def __init__(
        self,
        *,
        repo: str,
        runner: CommandRunner | None = None,
    ) -> None:
        self._repo = repo
        self._runner = runner or _default_runner

    def list(self, statuses: Sequence[str] | None = None) -> list[Task]:
        result = self._runner(
            [
                "gh",
                "issue",
                "list",
                "--repo",
                self._repo,
                "--json",
                "number,title,body,labels,updatedAt,url",
            ]
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "gh issue list failed")

        payload = json.loads(result.stdout or "[]")
        tasks = [normalize_github_issue(item) for item in payload]
        if statuses is not None:
            wanted = set(statuses)
            tasks = [task for task in tasks if task.status in wanted]
        tasks.sort(key=_sort_key)
        return tasks

    def update(self, task_id: str | int, changes: Mapping[str, Any]) -> None:
        issue_number = _parse_task_number(task_id)
        commands: list[str] = [
            "gh",
            "issue",
            "edit",
            str(issue_number),
            "--repo",
            self._repo,
        ]

        status = changes.get("status")
        if isinstance(status, str):
            current_status = self._current_status(issue_number)
            if current_status and current_status != status:
                commands.extend(["--remove-label", current_status])
            commands.extend(["--add-label", status])

        labels = changes.get("labels")
        if isinstance(labels, Sequence) and not isinstance(labels, (str, bytes)):
            for label in labels:
                if isinstance(label, str):
                    commands.extend(["--add-label", label])

        result = self._runner(commands)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "gh issue edit failed")

    def check_health(self) -> IntegrationHealth:
        result = self._runner(["gh", "auth", "status", "--hostname", "github.com"])
        status = "healthy" if result.returncode == 0 else "failed"
        message = (result.stderr or result.stdout).strip() or None
        return IntegrationHealth(
            name="github",
            status=status,
            checked_at=_now_iso(),
            message=message,
        )

    def _current_status(self, issue_number: int) -> str | None:
        result = self._runner(
            [
                "gh",
                "issue",
                "view",
                str(issue_number),
                "--repo",
                self._repo,
                "--json",
                "labels",
            ]
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "gh issue view failed")
        payload = json.loads(result.stdout or "{}")
        labels = _label_names(payload.get("labels", []))
        return _infer_status(labels)
