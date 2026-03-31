from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import subprocess
from typing import Any, Callable, Mapping, Sequence


Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class NormalizedTask:
    id: str
    source: str
    title: str
    body: str
    labels: list[str]
    status: str
    updated_at: str
    url: str

    @classmethod
    def from_github_issue(cls, issue: Mapping[str, Any]) -> "NormalizedTask":
        labels = [str(label["name"]) for label in issue.get("labels", [])]
        status = _status_from_labels(labels)
        return cls(
            id=f"gh-{issue['number']}",
            source="github",
            title=str(issue.get("title", "")),
            body=str(issue.get("body", "")),
            labels=labels,
            status=status,
            updated_at=str(issue.get("updatedAt", "")),
            url=str(issue.get("url", "")),
        )


@dataclass(frozen=True)
class IntegrationHealth:
    name: str
    status: str
    checked_at: str
    detail: str = ""


class GitHubIssueAdapter:
    def __init__(self, repo: str, runner: Runner | None = None):
        self.repo = repo
        self.runner = runner or subprocess.run

    def list(self, statuses: Sequence[str] | None = None) -> list[NormalizedTask]:
        result = self.runner(
            [
                "gh",
                "issue",
                "list",
                "--repo",
                self.repo,
                "--json",
                "number,title,body,labels,updatedAt,url",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "gh issue list failed")
        payload = json.loads(result.stdout or "[]")
        tasks = [NormalizedTask.from_github_issue(item) for item in payload]
        if statuses is None:
            return tasks
        allowed = set(statuses)
        return [task for task in tasks if task.status in allowed]

    def update(self, task_id: str, changes: Mapping[str, Any]) -> None:
        issue_number = task_id.removeprefix("gh-")
        args = ["gh", "issue", "edit", issue_number, "--repo", self.repo]
        status = changes.get("status")
        if status is not None:
            args.extend(["--remove-label", "ready", "--remove-label", "feedback", "--remove-label", "in-progress", "--remove-label", "in-review", "--remove-label", "accepted", "--remove-label", "idea"])
            mapped = _label_for_status(str(status))
            if mapped is not None:
                args.extend(["--add-label", mapped])
        result = self.runner(args, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "gh issue edit failed")

    def check_health(self) -> IntegrationHealth:
        result = self.runner(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            check=False,
        )
        detail = (result.stdout or result.stderr).strip()
        return IntegrationHealth(
            name="github",
            status="healthy" if result.returncode == 0 else "failed",
            checked_at=datetime.now(timezone.utc).isoformat(),
            detail=detail,
        )


def _status_from_labels(labels: Sequence[str]) -> str:
    for label in ("ready", "feedback", "in-progress", "in-review", "accepted", "idea"):
        if label in labels:
            return label
    return "idea"


def _label_for_status(status: str) -> str | None:
    allowed = {"ready", "feedback", "in-progress", "in-review", "accepted", "idea"}
    return status if status in allowed else None
