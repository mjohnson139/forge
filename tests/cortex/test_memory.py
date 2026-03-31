from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from forge.cortex.memory import MemoryStore, Recipe, RunRecord, TaskMemory


class MemoryStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.repo_root = Path(self.tempdir.name)
        self.store = MemoryStore(self.repo_root)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_ensure_layout_creates_empty_files(self) -> None:
        self.store.ensure_layout()

        self.assertTrue(self.store.runs_path.exists())
        self.assertTrue(self.store.recipes_path.exists())
        self.assertTrue(self.store.failures_path.exists())
        self.assertTrue(self.store.tasks_dir.exists())
        self.assertEqual(self.store.load_runs(), [])
        self.assertEqual(self.store.load_recipes(), [])

    def test_upsert_run_replaces_existing_run(self) -> None:
        self.store.ensure_layout()
        first = RunRecord(
            run_id="run-1",
            task_id="gh-1",
            job_name="heartbeat",
            pipeline="github-task",
            state="running",
            attempt=1,
            started_at="2026-03-30T12:00:00Z",
            updated_at="2026-03-30T12:00:00Z",
            last_heartbeat_at="2026-03-30T12:00:00Z",
            last_error=None,
            next_action="dispatch",
        )
        second = RunRecord(
            run_id="run-1",
            task_id="gh-1",
            job_name="heartbeat",
            pipeline="github-task",
            state="completed",
            attempt=1,
            started_at="2026-03-30T12:00:00Z",
            updated_at="2026-03-30T12:05:00Z",
            last_heartbeat_at="2026-03-30T12:05:00Z",
            last_error=None,
            next_action="none",
        )

        self.store.upsert_run(first)
        self.store.upsert_run(second)

        runs = self.store.load_runs()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].state, "completed")
        self.assertEqual(self.store.get_run("run-1").updated_at, "2026-03-30T12:05:00Z")

    def test_task_memory_round_trip_and_brief_context(self) -> None:
        self.store.ensure_layout()
        self.store.upsert_task_memory(
            TaskMemory(
                task_id="gh-7",
                last_summary="Updated login flow.",
                last_outcome="success",
                last_pipeline="github-task",
                open_blockers=["waiting on review"],
                recent_decisions=["split auth from UI"],
                recipe_hint="github-bugfix",
                updated_at="2026-03-30T12:10:00Z",
            )
        )
        self.store.upsert_run(
            RunRecord(
                run_id="run-7",
                task_id="gh-7",
                job_name="cortex-heartbeat",
                pipeline="github-task",
                state="running",
                attempt=2,
                started_at="2026-03-30T12:00:00Z",
                updated_at="2026-03-30T12:12:00Z",
                last_heartbeat_at="2026-03-30T12:12:00Z",
                last_error=None,
                next_action="verify",
            )
        )
        self.store.write_recipes(
            [
                Recipe(
                    name="github-bugfix",
                    match_rules={"source": "github", "labels": ["bug"], "keywords": ["login"]},
                    pipeline="github-task",
                    brief_context={"mode": "fix"},
                    success_patterns=["tests pass", "PR open"],
                    watchouts=["watch for auth regressions"],
                )
            ]
        )

        context = self.store.brief_context_for_task(
            task_id="gh-7",
            source="github",
            title="Fix login bug",
            body="Login fails after refresh.",
            labels=["bug"],
        )

        self.assertEqual(context["task_memory"]["last_outcome"], "success")
        self.assertEqual(context["active_run"]["state"], "running")
        self.assertEqual(context["recipe"]["name"], "github-bugfix")
        self.assertEqual(context["recipe"]["pipeline"], "github-task")

    def test_append_failure_writes_jsonl_line(self) -> None:
        self.store.ensure_layout()
        self.store.append_failure(
            {
                "timestamp": "2026-03-30T12:20:00Z",
                "task_id": "gh-9",
                "run_id": "run-9",
                "summary": "Pipeline failed on verification.",
                "outcome": "failure",
                "next_action": "retry",
            }
        )

        lines = self.store.failures_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["task_id"], "gh-9")

    def test_find_stale_runs_returns_old_running_runs(self) -> None:
        self.store.ensure_layout()
        old_hb = "2020-01-01T00:00:00+00:00"
        self.store.upsert_run(
            RunRecord(
                run_id="run-old",
                task_id="gh-1",
                job_name="heartbeat",
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
        self.store.upsert_run(
            RunRecord(
                run_id="run-fresh",
                task_id="gh-2",
                job_name="heartbeat",
                pipeline="github-task",
                state="running",
                attempt=1,
                started_at="2099-01-01T00:00:00+00:00",
                updated_at="2099-01-01T00:00:00+00:00",
                last_heartbeat_at="2099-01-01T00:00:00+00:00",
                last_error=None,
                next_action="dispatch",
            )
        )

        stale = self.store.find_stale_runs(threshold_minutes=60)

        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0].run_id, "run-old")

    def test_find_stale_runs_ignores_non_running_states(self) -> None:
        self.store.ensure_layout()
        old_hb = "2020-01-01T00:00:00+00:00"
        for state in ("completed", "failed", "stale", "skipped"):
            self.store.upsert_run(
                RunRecord(
                    run_id=f"run-{state}",
                    task_id="gh-1",
                    job_name="heartbeat",
                    pipeline="github-task",
                    state=state,
                    attempt=1,
                    started_at=old_hb,
                    updated_at=old_hb,
                    last_heartbeat_at=old_hb,
                    last_error=None,
                    next_action="none",
                )
            )

        stale = self.store.find_stale_runs(threshold_minutes=60)
        self.assertEqual(stale, [])

    def test_mark_run_stale_updates_state(self) -> None:
        self.store.ensure_layout()
        old_hb = "2020-01-01T00:00:00+00:00"
        self.store.upsert_run(
            RunRecord(
                run_id="run-mark",
                task_id="gh-3",
                job_name="heartbeat",
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

        self.store.mark_run_stale("run-mark")

        run = self.store.get_run("run-mark")
        self.assertEqual(run.state, "stale")
        self.assertIn("stale", run.last_error)

    def test_has_recent_alert_suppresses_duplicates(self) -> None:
        self.store.ensure_layout()
        run_id = "run-suppress"

        self.assertFalse(self.store.has_recent_alert(run_id, "stale"))
        self.store.record_alert(run_id, "stale")
        self.assertTrue(self.store.has_recent_alert(run_id, "stale", within_minutes=30))

    def test_has_recent_alert_different_types_do_not_collide(self) -> None:
        self.store.ensure_layout()
        self.store.record_alert("run-x", "stale")
        self.assertFalse(self.store.has_recent_alert("run-x", "failure"))
        self.assertTrue(self.store.has_recent_alert("run-x", "stale"))

    def test_failure_event_count_counts_by_source(self) -> None:
        self.store.ensure_layout()
        self.store.append_failure_event(task_id="gh-1", run_id="r1", source="github_auth", summary="fail")
        self.store.append_failure_event(task_id="gh-2", run_id="r2", source="github_auth", summary="fail")
        self.store.append_failure_event(task_id="gh-3", run_id="r3", source="timeout", summary="slow")

        self.assertEqual(self.store.failure_event_count("github_auth"), 2)
        self.assertEqual(self.store.failure_event_count("timeout"), 1)
        self.assertEqual(self.store.failure_event_count("cortex"), 0)

    def test_add_recipe_watchout_appends_to_recipe(self) -> None:
        self.store.ensure_layout()
        self.store.write_recipes(
            [
                Recipe(
                    name="github-bugfix",
                    match_rules={"source": "github"},
                    pipeline="github-task",
                    watchouts=["watch for flakiness"],
                )
            ]
        )

        self.store.add_recipe_watchout("github-bugfix", "Repeated timeout failures: pipeline hung")

        recipes = self.store.load_recipes()
        self.assertEqual(len(recipes[0].watchouts), 2)
        self.assertIn("Repeated timeout failures: pipeline hung", recipes[0].watchouts)

    def test_add_recipe_watchout_does_not_duplicate(self) -> None:
        self.store.ensure_layout()
        self.store.write_recipes(
            [
                Recipe(
                    name="github-bugfix",
                    match_rules={"source": "github"},
                    pipeline="github-task",
                    watchouts=["already there"],
                )
            ]
        )

        self.store.add_recipe_watchout("github-bugfix", "already there")

        recipes = self.store.load_recipes()
        self.assertEqual(len(recipes[0].watchouts), 1)

