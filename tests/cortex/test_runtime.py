from __future__ import annotations

import pathlib
import subprocess
import tempfile
import unittest

from forge.cortex.runtime import CortexRuntime, PipelineTimeoutError


class FakeMemoryStore:
    def __init__(
        self,
        stale_runs: list | None = None,
        recent_alerts: dict | None = None,
        failure_event_counts: dict | None = None,
    ) -> None:
        self.started: list[dict[str, object]] = []
        self.completed: list[tuple[str, str]] = []
        self.failed: list[tuple[str, str, str]] = []
        self.task_summaries: list[tuple[str, str, str, str]] = []
        self.failure_events: list[dict[str, object]] = []
        self.alerts_recorded: list[tuple[str, str]] = []
        self.stale_marked: list[str] = []
        self.watchouts_added: list[tuple[str, str]] = []
        self._stale_runs = stale_runs or []
        self._recent_alerts: dict[str, bool] = recent_alerts or {}
        self._failure_event_counts: dict[str, int] = failure_event_counts or {}

    def load_task_memory(self, task_id: str) -> dict[str, object]:
        return {"task_id": task_id, "last_summary": None}

    def find_active_run(self, task_id: str) -> dict[str, object] | None:
        return None

    def find_recipe(self, task: dict[str, object] | None) -> dict[str, object] | None:
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

    def find_stale_runs(self, threshold_minutes: int = 60) -> list:
        return list(self._stale_runs)

    def mark_run_stale(self, run_id: str) -> None:
        self.stale_marked.append(run_id)

    def has_recent_alert(
        self, run_id: str, alert_type: str = "failure", within_minutes: int = 30
    ) -> bool:
        return self._recent_alerts.get(f"{run_id}:{alert_type}", False)

    def record_alert(self, run_id: str, alert_type: str = "failure") -> None:
        self.alerts_recorded.append((run_id, alert_type))

    def failure_event_count(self, source: str) -> int:
        return self._failure_event_counts.get(source, 0)

    def add_recipe_watchout(self, recipe_name: str, watchout: str) -> None:
        self.watchouts_added.append((recipe_name, watchout))


class FakePipelineService:
    def __init__(
        self, tasks: list[dict[str, object]], health_status: str = "healthy"
    ) -> None:
        self.tasks = tasks
        self.health_status = health_status
        self.healthcheck_count = 0

    def healthcheck(self) -> dict[str, object]:
        self.healthcheck_count += 1
        if self.health_status == "healthy":
            return {"name": "github", "status": "healthy", "checked_at": "now", "detail": "ok"}
        return {
            "name": "github",
            "status": "degraded",
            "checked_at": "now",
            "detail": self.health_status,
        }

    def list(self, filter: dict[str, object] | None = None) -> list[dict[str, object]]:
        return list(self.tasks)


def _make_repo_root(tmp: str) -> pathlib.Path:
    repo_root = pathlib.Path(tmp)
    (repo_root / "USER.md").write_text(
        "# USER.md\n\n- **Name:** Matt\n- **Timezone:** America/New_York\n- **Style:** Short\n",
        encoding="utf-8",
    )
    (repo_root / "logs").mkdir()
    (repo_root / "forge" / "uplink").mkdir(parents=True)
    (repo_root / "forge" / "uplink" / "inbox.json").write_text("[]", encoding="utf-8")
    return repo_root


class RuntimeTest(unittest.TestCase):
    def test_heartbeat_skips_cleanly_when_no_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = _make_repo_root(tmp)
            messages: list[str] = []
            runtime = CortexRuntime(
                repo_root=repo_root,
                pipeline_service=FakePipelineService([]),
                memory_store=FakeMemoryStore(),
                notifier=messages.append,
                _sleep=lambda _: None,
            )

            result = runtime.heartbeat()

        self.assertEqual(result.outcome, "skipped")
        self.assertEqual(len(messages), 1)

    def test_heartbeat_starts_and_completes_run_for_first_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = _make_repo_root(tmp)
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
                _sleep=lambda _: None,
            )

            result = runtime.heartbeat()

        self.assertEqual(result.outcome, "success")
        self.assertEqual(calls, [("github-task.dot", "gh-8")])
        self.assertEqual(len(memory.started), 1)
        self.assertEqual(len(memory.completed), 1)
        self.assertEqual(memory.task_summaries[0][0], "gh-8")

    def test_heartbeat_marks_failure_when_dispatch_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = _make_repo_root(tmp)
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
                _sleep=lambda _: None,
            )

            result = runtime.heartbeat()

        self.assertEqual(result.outcome, "failure")
        self.assertEqual(len(memory.failed), 1)
        self.assertEqual(len(memory.failure_events), 1)
        self.assertEqual(len(messages), 1)

    def test_github_auth_failure_is_recorded_after_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = _make_repo_root(tmp)
            memory = FakeMemoryStore()
            messages: list[str] = []
            pipeline_svc = FakePipelineService([], health_status="gh auth status failed")

            runtime = CortexRuntime(
                repo_root=repo_root,
                pipeline_service=pipeline_svc,
                memory_store=memory,
                notifier=messages.append,
                _sleep=lambda _: None,
            )

            result = runtime.heartbeat()

        self.assertEqual(result.outcome, "failure")
        self.assertIn("health check failed", result.summary)
        self.assertEqual(len(memory.failure_events), 1)
        self.assertEqual(memory.failure_events[0]["source"], "github_auth")
        self.assertEqual(len(messages), 1)
        # healthcheck was called twice (initial + retry)
        self.assertEqual(pipeline_svc.healthcheck_count, 2)

    def test_rate_limit_failure_is_recorded_without_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = _make_repo_root(tmp)
            memory = FakeMemoryStore()
            messages: list[str] = []
            pipeline_svc = FakePipelineService([], health_status="HTTP 429 rate limit exceeded")

            runtime = CortexRuntime(
                repo_root=repo_root,
                pipeline_service=pipeline_svc,
                memory_store=memory,
                notifier=messages.append,
                _sleep=lambda _: None,
            )

            result = runtime.heartbeat()

        self.assertEqual(result.outcome, "failure")
        self.assertIn("rate limit", result.summary.lower())
        self.assertEqual(memory.failure_events[0]["source"], "rate_limit")
        # rate limit: no retry, healthcheck called only once
        self.assertEqual(pipeline_svc.healthcheck_count, 1)

    def test_pipeline_timeout_records_timeout_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = _make_repo_root(tmp)
            memory = FakeMemoryStore()
            messages: list[str] = []

            def dispatcher(root, name, brief):
                raise subprocess.TimeoutExpired(cmd="attractor", timeout=600)

            runtime = CortexRuntime(
                repo_root=repo_root,
                pipeline_service=FakePipelineService(
                    [
                        {
                            "id": "gh-10",
                            "source": "github",
                            "title": "Long running task",
                            "body": "Takes forever.",
                            "labels": ["ready"],
                            "status": "ready",
                            "updated_at": "2026-03-30T12:00:00+00:00",
                            "url": "https://example.test/10",
                        }
                    ]
                ),
                memory_store=memory,
                dispatcher=dispatcher,
                notifier=messages.append,
                _sleep=lambda _: None,
            )

            result = runtime.heartbeat()

        self.assertEqual(result.outcome, "timeout")
        self.assertIn("timed out", result.summary)
        self.assertEqual(len(memory.failed), 1)
        self.assertEqual(memory.failure_events[0]["source"], "timeout")
        self.assertEqual(len(messages), 1)

    def test_stale_run_detection_marks_and_notifies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = _make_repo_root(tmp)
            messages: list[str] = []

            class _FakeRun:
                run_id = "run-stale-1"
                task_id = "gh-99"

            memory = FakeMemoryStore(stale_runs=[_FakeRun()])

            runtime = CortexRuntime(
                repo_root=repo_root,
                pipeline_service=FakePipelineService([]),
                memory_store=memory,
                notifier=messages.append,
                _sleep=lambda _: None,
            )

            runtime.heartbeat()

        self.assertIn("run-stale-1", memory.stale_marked)
        self.assertIn(("run-stale-1", "stale"), memory.alerts_recorded)
        self.assertEqual(len(messages), 2)  # stale alert + skipped heartbeat

    def test_duplicate_stale_alert_is_suppressed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = _make_repo_root(tmp)
            messages: list[str] = []

            class _FakeRun:
                run_id = "run-stale-2"
                task_id = "gh-100"

            memory = FakeMemoryStore(
                stale_runs=[_FakeRun()],
                recent_alerts={"run-stale-2:stale": True},
            )

            runtime = CortexRuntime(
                repo_root=repo_root,
                pipeline_service=FakePipelineService([]),
                memory_store=memory,
                notifier=messages.append,
                _sleep=lambda _: None,
            )

            runtime.heartbeat()

        # stale run exists but alert suppressed → not marked again, no stale message
        self.assertNotIn("run-stale-2", memory.stale_marked)
        self.assertEqual(len(messages), 1)  # only the skipped heartbeat

    def test_repeat_failure_writes_recipe_watchout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = _make_repo_root(tmp)
            memory = FakeMemoryStore(failure_event_counts={"cortex": 2})
            messages: list[str] = []

            def dispatcher(root, name, brief):
                raise RuntimeError("attractor crashed")

            runtime = CortexRuntime(
                repo_root=repo_root,
                pipeline_service=FakePipelineService(
                    [
                        {
                            "id": "gh-11",
                            "source": "github",
                            "title": "Flaky task",
                            "body": "Keeps failing.",
                            "labels": ["ready"],
                            "status": "ready",
                            "updated_at": "2026-03-30T12:00:00+00:00",
                            "url": "https://example.test/11",
                        }
                    ]
                ),
                memory_store=memory,
                dispatcher=dispatcher,
                notifier=messages.append,
                _sleep=lambda _: None,
            )

            runtime.heartbeat()

        self.assertEqual(len(memory.watchouts_added), 1)
        self.assertEqual(memory.watchouts_added[0][0], "github default")
