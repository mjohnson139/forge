from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

from forge.pipeline.github_adapter import GitHubIssueAdapter, NormalizedTask


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
        self.adapter = adapter or _NullAdapter()

    def healthcheck(self) -> dict[str, Any]:
        return {
            "name": "github",
            "status": "healthy" if not isinstance(self.adapter, _NullAdapter) else "degraded",
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    def list(self, status: Sequence[str] | Mapping[str, Any] | None = None) -> list[Task]:
        if isinstance(status, Mapping):
            status = status.get("status")
        allowed = list(status) if status is not None else ["ready", "feedback"]
        tasks = [self._normalize_task(task) for task in self.adapter.list()]
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


class _NullAdapter:
    def list(self):
        return []

    def update(self, task_id, changes):
        return None
