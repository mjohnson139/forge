from __future__ import annotations

import json
import pathlib
import subprocess
import tempfile
import unittest

from forge.axon.registry import load_registry
from forge.axon.runtime import render_crontab_line
from forge.cortex.memory import MemoryStore, RunRecord
from forge.cortex.runtime import CortexRuntime


class FakePipelineService:
    def healthcheck(self):
        return {
            "name": "github",
            "status": "healthy",
            "checked_at": "now",
            "detail": "stub",
        }

    def list(self, status=None):
        return [
            {
                "id": "gh-42",
                "source": "github",
                "title": "Fix login bug",
                "body": "Need a minimal fix and verification.",
                "labels": ["ready", "bug"],
                "status": "ready",
                "updated_at": "2026-03-30T12:00:00+00:00",
                "url": "https://example.test/issues/42",
            }
        ]


class DegradedPipelineService:
    def healthcheck(self):
        return {
            "name": "github",
            "status": "degraded",
            "checked_at": "now",
            "detail": "gh auth status failed",
        }

    def list(self, status=None):
        return []


class MVPFlowTest(unittest.TestCase):
    def test_heartbeat_updates_lens_memory_and_notifications(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = pathlib.Path(tmp)
            (repo_root / "USER.md").write_text(
                "# USER.md\n\n- **Name:** Matt\n- **Timezone:** America/New_York\n- **Style:** Short\n",
                encoding="utf-8",
            )
            (repo_root / "logs").mkdir()
            (repo_root / "forge" / "uplink").mkdir(parents=True)
            (repo_root / "forge" / "uplink" / "inbox.json").write_text("[]", encoding="utf-8")
            memory_store = MemoryStore(repo_root)
            messages: list[str] = []

            def dispatcher(repo_root, pipeline_name, brief):
                self.assertEqual(pipeline_name, "github-task.dot")
                self.assertEqual(brief["task"]["id"], "gh-42")

                class Result:
                    returncode = 0

                return Result()

            runtime = CortexRuntime(
                repo_root=repo_root,
                pipeline_service=FakePipelineService(),
                memory_store=memory_store,
                dispatcher=dispatcher,
                notifier=messages.append,
            )

            result = runtime.heartbeat()

            history_lines = (repo_root / "logs" / "history.jsonl").read_text(
                encoding="utf-8"
            ).strip().splitlines()
            runs = json.loads((repo_root / "forge" / "memory" / "runs.json").read_text(encoding="utf-8"))
            task_memory = json.loads(
                (repo_root / "forge" / "memory" / "tasks" / "gh-42.json").read_text(encoding="utf-8")
            )

        self.assertEqual(result.outcome, "success")
        self.assertEqual(len(history_lines), 2)
        self.assertEqual(runs[0]["state"], "completed")
        self.assertEqual(task_memory["last_outcome"], "success")
        self.assertEqual(len(messages), 1)

    def test_failure_traces_lens_memory_and_uplink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = pathlib.Path(tmp)
            (repo_root / "USER.md").write_text(
                "# USER.md\n\n- **Name:** Matt\n- **Timezone:** America/New_York\n- **Style:** Short\n",
                encoding="utf-8",
            )
            (repo_root / "logs").mkdir()
            (repo_root / "forge" / "uplink").mkdir(parents=True)
            (repo_root / "forge" / "uplink" / "inbox.json").write_text("[]", encoding="utf-8")
            memory_store = MemoryStore(repo_root)
            messages: list[str] = []

            def dispatcher(root, pipeline_name, brief):
                raise RuntimeError("attractor crashed")

            runtime = CortexRuntime(
                repo_root=repo_root,
                pipeline_service=FakePipelineService(),
                memory_store=memory_store,
                dispatcher=dispatcher,
                notifier=messages.append,
                _sleep=lambda _: None,
            )

            result = runtime.heartbeat()

            history_lines = (repo_root / "logs" / "history.jsonl").read_text(
                encoding="utf-8"
            ).strip().splitlines()
            runs = json.loads(
                (repo_root / "forge" / "memory" / "runs.json").read_text(encoding="utf-8")
            )
            failures = (repo_root / "forge" / "memory" / "failures.jsonl").read_text(
                encoding="utf-8"
            ).strip().splitlines()

        self.assertEqual(result.outcome, "failure")
        self.assertTrue(len(history_lines) >= 2)
        self.assertEqual(runs[0]["state"], "failed")
        self.assertEqual(len(failures), 1)
        self.assertEqual(len(messages), 1)
        self.assertIn("failure", messages[0].lower())

    def test_stale_run_detection_integration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = pathlib.Path(tmp)
            (repo_root / "USER.md").write_text(
                "# USER.md\n\n- **Name:** Matt\n- **Timezone:** America/New_York\n- **Style:** Short\n",
                encoding="utf-8",
            )
            (repo_root / "logs").mkdir()
            (repo_root / "forge" / "uplink").mkdir(parents=True)
            (repo_root / "forge" / "uplink" / "inbox.json").write_text("[]", encoding="utf-8")
            memory_store = MemoryStore(repo_root)
            memory_store.ensure_layout()
            old_hb = "2020-01-01T00:00:00+00:00"
            memory_store.upsert_run(
                RunRecord(
                    run_id="run-stale-int",
                    task_id="gh-stale",
                    job_name="cortex-heartbeat",
                    pipeline="github-task",
                    state="running",
                    attempt=1,
                    started_at=old_hb,
                    updated_at=old_hb,
                    last_heartbeat_at=old_hb,
                    last_error=None,
                    next_action="dispatch",
                )
            )
            messages: list[str] = []

            runtime = CortexRuntime(
                repo_root=repo_root,
                pipeline_service=FakePipelineService(),
                memory_store=memory_store,
                notifier=messages.append,
                _sleep=lambda _: None,
            )

            runtime.heartbeat()

            run = memory_store.get_run("run-stale-int")

        self.assertEqual(run.state, "stale")
        self.assertTrue(
            any("stale" in m.lower() for m in messages),
            f"Expected stale alert in messages: {messages}",
        )

    def test_github_auth_failure_traces_lens_and_uplink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = pathlib.Path(tmp)
            (repo_root / "USER.md").write_text(
                "# USER.md\n\n- **Name:** Matt\n- **Timezone:** America/New_York\n- **Style:** Short\n",
                encoding="utf-8",
            )
            (repo_root / "logs").mkdir()
            (repo_root / "forge" / "uplink").mkdir(parents=True)
            (repo_root / "forge" / "uplink" / "inbox.json").write_text("[]", encoding="utf-8")
            memory_store = MemoryStore(repo_root)
            messages: list[str] = []

            runtime = CortexRuntime(
                repo_root=repo_root,
                pipeline_service=DegradedPipelineService(),
                memory_store=memory_store,
                notifier=messages.append,
                _sleep=lambda _: None,
            )

            result = runtime.heartbeat()

            history_lines = (repo_root / "logs" / "history.jsonl").read_text(
                encoding="utf-8"
            ).strip().splitlines()
            failures = (repo_root / "forge" / "memory" / "failures.jsonl").read_text(
                encoding="utf-8"
            ).strip().splitlines()

        self.assertEqual(result.outcome, "failure")
        self.assertTrue(len(history_lines) >= 1)
        self.assertEqual(len(failures), 1)
        self.assertEqual(json.loads(failures[0])["source"], "github_auth")
        self.assertEqual(len(messages), 1)

    def test_axon_registry_preview_produces_cron_lines(self) -> None:
        registry_path = (
            pathlib.Path(__file__).parent.parent.parent / "forge" / "axon" / "registry.json"
        )
        jobs = load_registry(str(registry_path))
        lines = [render_crontab_line(schedule=j.schedule, job_name=j.name, command=j.command) for j in jobs]

        self.assertTrue(len(lines) >= 1)
        for line in lines:
            # Each line should contain a cron schedule (5 fields) + command
            parts = line.split()
            self.assertTrue(len(parts) >= 6, f"Line too short: {line!r}")
            # Lines are wrapped with flock for concurrency safety
            self.assertIn("flock", line)
