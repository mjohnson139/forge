from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from forge.cortex.brief import assemble_brief, load_operator_profile, read_lens_history


class FakeMemoryStore:
    def load_task_memory(self, task_id: str) -> dict[str, object]:
        return {"task_id": task_id, "last_summary": "Prior attempt failed."}

    def find_active_run(self, task_id: str) -> dict[str, object] | None:
        return {"run_id": "run-1", "state": "blocked", "attempt": 2}

    def find_recipe(self, task: dict[str, object]) -> dict[str, object] | None:
        return {"name": "github bugfix", "pipeline": "github-task.dot"}


class BriefTest(unittest.TestCase):
    def test_load_operator_profile_reads_user_md(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = pathlib.Path(tmp)
            (repo_root / "USER.md").write_text(
                "# USER.md\n\n- **Name:** Matt\n- **Timezone:** America/New_York\n- **Style:** Short\n",
                encoding="utf-8",
            )

            profile = load_operator_profile(repo_root)

        self.assertEqual(profile.name, "Matt")
        self.assertEqual(profile.timezone, "America/New_York")
        self.assertEqual(profile.style, "Short")

    def test_read_lens_history_filters_by_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = pathlib.Path(tmp)
            logs_dir = repo_root / "logs"
            logs_dir.mkdir()
            history_path = logs_dir / "history.jsonl"
            history_path.write_text(
                json.dumps({"summary": "ignore", "task_id": "gh-2"}) + "\n"
                + json.dumps({"summary": "keep", "task_id": "gh-1"}) + "\n",
                encoding="utf-8",
            )

            history = read_lens_history(repo_root, task_id="gh-1")

        self.assertEqual(history, ["keep"])

    def test_assemble_brief_includes_memory_history_and_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = pathlib.Path(tmp)
            (repo_root / "USER.md").write_text(
                "# USER.md\n\n- **Name:** Matt\n- **Timezone:** America/New_York\n- **Style:** Short\n",
                encoding="utf-8",
            )
            logs_dir = repo_root / "logs"
            logs_dir.mkdir()
            (logs_dir / "history.jsonl").write_text(
                json.dumps({"summary": "Tried once already.", "task_id": "gh-7"}) + "\n",
                encoding="utf-8",
            )
            inbox_dir = repo_root / "forge" / "uplink"
            inbox_dir.mkdir(parents=True)
            (inbox_dir / "inbox.json").write_text(
                json.dumps([{"scope": "global", "instruction": "prioritize fast feedback"}]),
                encoding="utf-8",
            )

            brief = assemble_brief(
                {
                    "id": "gh-7",
                    "source": "github",
                    "title": "Fix login bug",
                    "body": "Repro included.",
                    "labels": ["ready", "bug"],
                    "status": "ready",
                    "updated_at": "2026-03-30T12:00:00+00:00",
                    "url": "https://example.test/7",
                },
                repo_root=repo_root,
                tool_statuses=[{"name": "github", "status": "healthy", "checked_at": "now"}],
                memory_store=FakeMemoryStore(),
            )

        self.assertEqual(brief["task"]["id"], "gh-7")
        self.assertEqual(brief["history"], ["Tried once already."])
        self.assertEqual(brief["memory"]["task_memory"]["last_summary"], "Prior attempt failed.")
        self.assertEqual(brief["memory"]["recipe"]["name"], "github bugfix")
        self.assertEqual(brief["context"]["overrides"][0]["instruction"], "prioritize fast feedback")
