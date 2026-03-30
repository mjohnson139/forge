from __future__ import annotations

import json
import pathlib
import subprocess
import tempfile
import unittest

from forge.pipeline.github_adapter import GithubIssueAdapter, normalize_github_issue
from forge.pipeline.service import PipelineService


class GithubAdapterTest(unittest.TestCase):
    def test_normalize_github_issue_uses_label_as_status(self) -> None:
        task = normalize_github_issue(
            {
                "number": 42,
                "title": "Fix login bug",
                "body": "Users cannot sign in.",
                "labels": [{"name": "ready"}, {"name": "backend"}],
                "updatedAt": "2026-03-30T10:00:00Z",
                "url": "https://github.com/mjohnson139/ray-groove-issues/issues/42",
            }
        )

        self.assertEqual(task.id, "gh-42")
        self.assertEqual(task.source, "github")
        self.assertEqual(task.status, "ready")
        self.assertEqual(task.labels, ["ready", "backend"])
        self.assertEqual(task.updated_at, "2026-03-30T10:00:00Z")

    def test_list_filters_and_sorts_tasks_from_gh_json(self) -> None:
        responses = {
            ("gh", "issue", "list", "--repo", "mjohnson139/ray-groove-issues", "--json", "number,title,body,labels,updatedAt,url"): subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=json.dumps(
                    [
                        {
                            "number": 3,
                            "title": "Later ready task",
                            "body": "Later.",
                            "labels": [{"name": "ready"}],
                            "updatedAt": "2026-03-30T11:00:00Z",
                            "url": "https://example.test/3",
                        },
                        {
                            "number": 1,
                            "title": "Earlier feedback task",
                            "body": "Fix comments.",
                            "labels": [{"name": "feedback"}],
                            "updatedAt": "2026-03-30T09:00:00Z",
                            "url": "https://example.test/1",
                        },
                        {
                            "number": 2,
                            "title": "Ignored task",
                            "body": "Not actionable.",
                            "labels": [{"name": "idea"}],
                            "updatedAt": "2026-03-30T08:00:00Z",
                            "url": "https://example.test/2",
                        },
                    ]
                ),
                stderr="",
            )
        }

        adapter = GithubIssueAdapter(
            repo="mjohnson139/ray-groove-issues",
            runner=lambda args: responses[tuple(args)],
        )

        tasks = adapter.list(statuses=("ready", "feedback"))

        self.assertEqual([task.id for task in tasks], ["gh-1", "gh-3"])
        self.assertEqual([task.status for task in tasks], ["feedback", "ready"])

    def test_update_translates_status_change_to_label_edits(self) -> None:
        commands: list[list[str]] = []

        def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
            commands.append(args)
            if args[:3] == ["gh", "issue", "view"]:
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=0,
                    stdout=json.dumps(
                        {
                            "number": 17,
                            "labels": [{"name": "ready"}],
                        }
                    ),
                    stderr="",
                )
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        adapter = GithubIssueAdapter(repo="mjohnson139/ray-groove-issues", runner=runner)
        adapter.update("gh-17", {"status": "in-progress"})

        self.assertIn(
            [
                "gh",
                "issue",
                "edit",
                "17",
                "--repo",
                "mjohnson139/ray-groove-issues",
                "--remove-label",
                "ready",
                "--add-label",
                "in-progress",
            ],
            commands,
        )

    def test_health_check_reports_healthy_when_auth_succeeds(self) -> None:
        def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
            self.assertEqual(args[:3], ["gh", "auth", "status"])
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        adapter = GithubIssueAdapter(repo="mjohnson139/ray-groove-issues", runner=runner)
        health = adapter.check_health()

        self.assertEqual(health.name, "github")
        self.assertEqual(health.status, "healthy")
        self.assertTrue(health.checked_at.endswith("Z") or "+" in health.checked_at)

    def test_health_check_reports_failed_when_auth_fails(self) -> None:
        def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(args=args, returncode=1, stdout="", stderr="not logged in")

        adapter = GithubIssueAdapter(repo="mjohnson139/ray-groove-issues", runner=runner)
        health = adapter.check_health()

        self.assertEqual(health.status, "failed")
        self.assertIn("not logged in", health.message or "")


class PipelineServiceTest(unittest.TestCase):
    def test_service_proxies_list_update_and_health(self) -> None:
        seen: list[tuple[str, object]] = []

        class StubAdapter:
            def list(self, statuses=None):
                seen.append(("list", statuses))
                return []

            def update(self, task_id, changes):
                seen.append(("update", (task_id, changes)))

            def check_health(self):
                seen.append(("health", None))
                return object()

        service = PipelineService(github=StubAdapter())
        service.list(statuses=("ready",))
        service.update("gh-9", {"status": "in-progress"})
        health = service.check_health()

        self.assertEqual(
            seen,
            [
                ("list", ("ready",)),
                ("update", ("gh-9", {"status": "in-progress"})),
                ("health", None),
            ],
        )
        self.assertIsNotNone(health)

