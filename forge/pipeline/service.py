from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import os
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from forge.pipeline.github_adapter import GitHubIssueAdapter, IntegrationHealth, NormalizedTask


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

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "Task":
        return cls(
            id=str(payload["id"]),
            source=str(payload["source"]),
            title=str(payload.get("title", "")),
            body=str(payload.get("body", "")),
            labels=list(payload.get("labels", [])),
            status=str(payload.get("status", "idea")),
            updated_at=str(payload.get("updated_at", "")),
            url=str(payload.get("url", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PipelineService:
    def __init__(self, adapter: Any | None = None, *, repo_root: str | None = None):
        self.repo_root = repo_root
        self.adapter = adapter or self._build_default_adapter()

    @classmethod
    def from_github_repo(cls, repo: str, runner: Any | None = None) -> "PipelineService":
        return cls(adapter=GitHubIssueAdapter(repo, runner=runner))

    def healthcheck(self) -> dict[str, Any]:
        if hasattr(self.adapter, "check_health"):
            health = self.adapter.check_health()
            if isinstance(health, IntegrationHealth):
                return {
                    "name": health.name,
                    "status": health.status,
                    "checked_at": health.checked_at,
                    "detail": health.detail,
                }
            return dict(health)
        return {
            "name": "github",
            "status": "degraded",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "detail": "adapter has no health check",
        }

    def list(self, status: Sequence[str] | Mapping[str, Any] | None = None) -> list[Task]:
        if isinstance(status, Mapping):
            status = status.get("status")
        allowed = list(status) if status is not None else ["ready", "feedback"]
        try:
            raw_tasks = self.adapter.list(statuses=allowed)
        except TypeError:
            raw_tasks = self.adapter.list()
        tasks = [self._normalize_task(task) for task in raw_tasks]
        filtered = [task for task in tasks if task.status in allowed]
        return sorted(filtered, key=lambda task: task.updated_at)

    def update(self, task_id: str, changes: Mapping[str, Any]) -> None:
        self.adapter.update(task_id, changes)

    def _normalize_task(self, task: Any) -> Task:
        if isinstance(task, Task):
            return task
        if isinstance(task, NormalizedTask):
            return Task(
                id=task.id,
                source=task.source,
                title=task.title,
                body=task.body,
                labels=list(task.labels),
                status=task.status,
                updated_at=task.updated_at,
                url=task.url,
            )
        if isinstance(task, Mapping):
            return Task.from_mapping(task)
        raise TypeError(f"unsupported task type: {type(task)!r}")

    def _build_default_adapter(self) -> Any:
        repo = _detect_task_repo(self.repo_root)
        if repo is None:
            return _NullAdapter()
        return GitHubIssueAdapter(repo)


class _NullAdapter:
    def list(self, statuses=None):
        return []

    def update(self, task_id, changes):
        return None

    def check_health(self):
        return {
            "name": "github",
            "status": "degraded",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "detail": "task repo not configured",
        }


def _detect_task_repo(repo_root: str | None) -> str | None:
    if repo_root is None:
        return os.getenv("FORGE_GITHUB_TASK_REPO")

    env_value = os.getenv("FORGE_GITHUB_TASK_REPO")
    if env_value:
        return env_value

    tools_md = Path(repo_root) / "TOOLS.md"
    if tools_md.exists():
        content = tools_md.read_text(encoding="utf-8")
        match = re.search(r"^Repo:\s+`([^`]+)`$", content, flags=re.MULTILINE)
        if match:
            return match.group(1)

    return None
