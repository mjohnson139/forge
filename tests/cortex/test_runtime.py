from __future__ import annotations

import pathlib
import tempfile
import unittest

from forge.cortex.runtime import CortexRuntime


class FakeMemoryStore:
    def __init__(self) -> None:
        self.started: list[dict[str, object]] = []
        self.completed: list[tuple[str, str]] = []
        self.failed: list[tuple[str, str, str]] = []
        self.task_summaries: list[tuple[str, str, str, str]] = []
        self.failure_events: list[dict[str, object]] = []

    def load_task_memory(self, task_id: str) -> dict[str, object]:
        return {"task_id": task_id, "last_summary": None}

    def find_active_run(self, task_id: str) -> dict[str, object] | None:
        return None

    def find_recipe(self, task: dict[str, object]) -> dict[str, object] | None:
        return {"name": "github default", "pipeline": "github-task.dot"}

    def start_run(self, **kwargs: object) -> None:
        self.started.append(kwargs)

    def complete_run(self, run_id: str, *, next_action: str) -> None:
        self.completed.append((run_id, next_action))

    def fail_run(self, run_id: str, error: str, *, next_action: str) -> None:
        self.failed.append((run_id, error, next_action))

    def append_failure_event(self, **kwargs: object) -> None:
        self.failure_events.append(kwargs)

    def save_task_summary(
        self,
        task_id: str,
        *,
        summary: str,
        outcome: str,
        pipeline: str,
    ) -> None:
        self.task_summaries.append((task_id, summary, outcome, pipeline))


class FakePipelineService:
    def __init__(self, tasks: list[dict[str, object]]) -> None:
        self.tasks = tasks

    def healthcheck(self) -> dict[str, object]:
        return {"name": "github", "status": "healthy", "checked_at": "now"}

    def list(self, filter: dict[str, object] | None = None) -> list[dict[str, object]]:
        return list(self.tasks)


class RuntimeTest(unittest.TestCase):
    def test_heartbeat_skips_cleanly_when_no_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = pathlib.Path(tmp)
            (repo_root / "USER.md").write_text(
                "# USER.md\n\n- **Name:** Matt\n- **Timezone:** America/New_York\n- **Style:** Short\n",
                encoding="utf-8",
            )
            (repo_root / "logs").mkdir()
            (repo_root / "forge" / "uplink").mkdir(parents=True)
            (repo_root / "forge" / "uplink" / "inbox.json").write_text("[]", encoding="utf-8")
            messages: list[str] = []
            runtime = CortexRuntime(
                repo_root=repo_root,
                pipeline_service=FakePipelineService([]),
                memory_store=FakeMemoryStore(),
                notifier=messages.append,
            )

            result = runtime.heartbeat()

        self.assertEqual(result.outcome, "skipped")
        self.assertEqual(len(messages), 1)

    def test_heartbeat_starts_and_completes_run_for_first_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = pathlib.Path(tmp)
            (repo_root / "USER.md").write_text(
                "# USER.md\n\n- **Name:** Matt\n- **Timezone:** America/New_York\n- **Style:** Short\n",
                encoding="utf-8",
            )
            (repo_root / "logs").mkdir()
            (repo_root / "forge" / "uplink").mkdir(parents=True)
            (repo_root / "forge" / "uplink" / "inbox.json").write_text("[]", encoding="utf-8")
            memory = FakeMemoryStore()
            calls: list[tuple[str, str]] = []

            def dispatcher(
                repo_root: pathlib.Path, pipeline_name: str, brief: dict[str, object]
            ) -> object:
                calls.append((pipeline_name, brief["task"]["id"]))  # type: ignore[index]

                class Result:
                    returncode = 0

                return Result()

            runtime = CortexRuntime(
                repo_root=repo_root,
                pipeline_service=FakePipelineService(
                    [
                        {
                            "id": "gh-8",
                            "source": "github",
                            "title": "Fix login bug",
                            "body": "Repro included.",
                            "labels": ["ready"],
                            "status": "ready",
                            "updated_at": "2026-03-30T12:00:00+00:00",
                            "url": "https://example.test/8",
                        }
                    ]
                ),
                memory_store=memory,
                dispatcher=dispatcher,
            )

            result = runtime.heartbeat()

        self.assertEqual(result.outcome, "success")
        self.assertEqual(calls, [("github-task.dot", "gh-8")])
        self.assertEqual(len(memory.started), 1)
        self.assertEqual(len(memory.completed), 1)
        self.assertEqual(memory.task_summaries[0][0], "gh-8")

    def test_heartbeat_marks_failure_when_dispatch_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = pathlib.Path(tmp)
            (repo_root / "USER.md").write_text(
                "# USER.md\n\n- **Name:** Matt\n- **Timezone:** America/New_York\n- **Style:** Short\n",
                encoding="utf-8",
            )
            (repo_root / "logs").mkdir()
            (repo_root / "forge" / "uplink").mkdir(parents=True)
            (repo_root / "forge" / "uplink" / "inbox.json").write_text("[]", encoding="utf-8")
            memory = FakeMemoryStore()
            messages: list[str] = []

            def dispatcher(
                repo_root: pathlib.Path, pipeline_name: str, brief: dict[str, object]
            ) -> object:
                raise RuntimeError("attractor unavailable")

            runtime = CortexRuntime(
                repo_root=repo_root,
                pipeline_service=FakePipelineService(
                    [
                        {
                            "id": "gh-9",
                            "source": "github",
                            "title": "Fix runtime bug",
                            "body": "Repro included.",
                            "labels": ["ready"],
                            "status": "ready",
                            "updated_at": "2026-03-30T12:00:00+00:00",
                            "url": "https://example.test/9",
                        }
                    ]
                ),
                memory_store=memory,
                dispatcher=dispatcher,
                notifier=messages.append,
            )

            result = runtime.heartbeat()

        self.assertEqual(result.outcome, "failure")
        self.assertEqual(len(memory.failed), 1)
        self.assertEqual(len(memory.failure_events), 1)
        self.assertEqual(len(messages), 1)
