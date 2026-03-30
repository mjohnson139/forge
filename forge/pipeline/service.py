from __future__ import annotations

from collections.abc import Sequence

from forge.pipeline.github_adapter import GithubIssueAdapter, IntegrationHealth, Task


class PipelineService:
    def __init__(self, *, github: GithubIssueAdapter) -> None:
        self.github = github

    @classmethod
    def from_github_repo(cls, repo: str) -> "PipelineService":
        return cls(github=GithubIssueAdapter(repo=repo))

    def list(self, statuses: Sequence[str] | None = None) -> list[Task]:
        return self.github.list(statuses=statuses)

    def update(self, task_id: str | int, changes: dict[str, object]) -> None:
        self.github.update(task_id, changes)

    def check_health(self) -> IntegrationHealth:
        return self.github.check_health()
