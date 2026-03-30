from __future__ import annotations

import json
import os
import pathlib
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from forge.pipeline.github_adapter import GitHubIssueAdapter
from forge.pipeline.service import PipelineService, NormalizedTask


class GitHubIssueAdapterTest(unittest.TestCase):
    def test_list_converts_issues_to_normalized_tasks(self) -> None:
        calls: list[tuple[list[str], dict[str, object]]] = []

        def runner(cmd: list[str], **kwargs: object) -> SimpleNamespace:
            calls.append((cmd, kwargs))
            payload = [
                {
                    "number": 7,
                    "title": "Fix login bug",
                    "body": "Refresh breaks auth.",
                    "labels": [{"name": "bug"}, {"name": "ready"}],
                    "updatedAt": "2026-03-30T12:00:00Z",
                    "url": "https://example.test/issues/7",
                },
                {
                    "number": 9,
                    "title": "Refactor parser",
                    "body": "Cleanup pass.",
                    "labels": [{"name": "maintenance"}, {"name": "in-progress"}],
                    "updatedAt": "2026-03-30T13:00:00Z",
                    "url": "https://example.test/issues/9",
                },
            ]
            return SimpleNamespace(returncode=0, stdout=json.dumps(payload))

        adapter = GitHubIssueAdapter("mjohnson139/forge", runner=runner)
        tasks = adapter.list()

        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks[0].id, "gh-7")
        self.assertEqual(tasks[0].status, "ready")
        self.assertEqual(tasks[1].status, "in-progress")
        self.assertIn("--json", calls[0][0])

    def test_update_translates_status_change_to_gh_edit(self) -> None:
        calls: list[list[str]] = []

        def runner(cmd: list[str], **kwargs: object) -> SimpleNamespace:
            calls.append(cmd)
            return SimpleNamespace(returncode=0, stdout="")

        adapter = GitHubIssueAdapter("mjohnson139/forge", runner=runner)
        adapter.update("gh-17", {"status": "in-progress"})

        self.assertEqual(calls[0][:4], ["gh", "issue", "edit", "17"])
        self.assertIn("--add-label", calls[0])
        self.assertIn("in-progress", calls[0])


class PipelineServiceTest(unittest.TestCase):
    def test_list_defaults_to_actionable_tasks_sorted_by_updated_at(self) -> None:
        tasks = [
            NormalizedTask(
                id="gh-2",
                source="github",
                title="Second",
                body="",
                labels=["ready"],
                status="ready",
                updated_at="2026-03-30T13:00:00Z",
                url="https://example.test/issues/2",
            ),
            NormalizedTask(
                id="gh-1",
                source="github",
                title="First",
                body="",
                labels=["feedback"],
                status="feedback",
                updated_at="2026-03-30T12:00:00Z",
                url="https://example.test/issues/1",
            ),
            NormalizedTask(
                id="gh-3",
                source="github",
                title="Ignored",
                body="",
                labels=["in-progress"],
                status="in-progress",
                updated_at="2026-03-30T14:00:00Z",
                url="https://example.test/issues/3",
            ),
        ]

        class Adapter:
            def list(self):
                return tasks

            def update(self, task_id, changes):
                raise AssertionError("not used")

        service = PipelineService(Adapter())
        listed = service.list()

        self.assertEqual([task.id for task in listed], ["gh-1", "gh-2"])

    def test_detects_task_repo_from_tools_md(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = pathlib.Path(tmp)
            (repo_root / "TOOLS.md").write_text(
                "# TOOLS.md\n\n## GitHub Task Board\n\nRepo: `mjohnson139/forge-tasks`\n",
                encoding="utf-8",
            )

            service = PipelineService(repo_root=str(repo_root))

        self.assertEqual(service.adapter.repo, "mjohnson139/forge-tasks")

    def test_env_task_repo_overrides_tools_md(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = pathlib.Path(tmp)
            (repo_root / "TOOLS.md").write_text(
                "# TOOLS.md\n\n## GitHub Task Board\n\nRepo: `mjohnson139/forge-tasks`\n",
                encoding="utf-8",
            )

            with mock.patch.dict(os.environ, {"FORGE_GITHUB_TASK_REPO": "override/tasks"}, clear=False):
                service = PipelineService(repo_root=str(repo_root))

        self.assertEqual(service.adapter.repo, "override/tasks")
