from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from forge.cortex.memory import MemoryStore
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
