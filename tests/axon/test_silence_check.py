from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from forge.axon.jobs.silence_check import run_silence_check


class SilenceCheckTest(unittest.TestCase):
    def test_recent_history_returns_success_without_alert(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = pathlib.Path(tmp)
            logs_dir = repo_root / "logs"
            logs_dir.mkdir()
            history_path = logs_dir / "history.jsonl"
            history_path.write_text(
                json.dumps(
                    {
                        "timestamp": "2026-03-29T21:45:00+00:00",
                        "source": "axon-cron",
                        "job": "board-check",
                        "summary": "Board checked.",
                        "outcome": "success",
                        "next_action": "none",
                        "task_id": None,
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            result = run_silence_check(
                repo_root=repo_root,
                now_iso="2026-03-29T22:00:00+00:00",
            )

        self.assertFalse(result.alert_needed)
        self.assertEqual(result.outcome, "success")

    def test_stale_history_appends_failure_entry_and_requests_alert(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = pathlib.Path(tmp)
            logs_dir = repo_root / "logs"
            logs_dir.mkdir()
            history_path = logs_dir / "history.jsonl"
            history_path.write_text(
                json.dumps(
                    {
                        "timestamp": "2026-03-29T19:30:00+00:00",
                        "source": "axon-cron",
                        "job": "board-check",
                        "summary": "Board checked.",
                        "outcome": "success",
                        "next_action": "none",
                        "task_id": None,
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            result = run_silence_check(
                repo_root=repo_root,
                now_iso="2026-03-29T22:00:00+00:00",
            )
            lines = history_path.read_text(encoding="utf-8").strip().splitlines()

        self.assertTrue(result.alert_needed)
        self.assertEqual(result.outcome, "failure")
        self.assertEqual(len(lines), 2)

    def test_monitor_entries_do_not_mask_real_silence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = pathlib.Path(tmp)
            logs_dir = repo_root / "logs"
            logs_dir.mkdir()
            history_path = logs_dir / "history.jsonl"
            history_path.write_text(
                json.dumps(
                    {
                        "timestamp": "2026-03-29T19:30:00+00:00",
                        "source": "kinetic",
                        "job": "task-7-build",
                        "summary": "Build step completed.",
                        "outcome": "success",
                        "next_action": "test",
                        "task_id": "task-7",
                    }
                )
                + "\n"
                + json.dumps(
                    {
                        "timestamp": "2026-03-29T21:45:00+00:00",
                        "source": "axon-cron",
                        "job": "silence-check",
                        "summary": "Silence check passed.",
                        "outcome": "success",
                        "next_action": "none",
                        "task_id": None,
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            result = run_silence_check(
                repo_root=repo_root,
                now_iso="2026-03-29T22:50:00+00:00",
            )
            lines = history_path.read_text(encoding="utf-8").strip().splitlines()
            latest_entry = json.loads(lines[-1])

        self.assertTrue(result.alert_needed)
        self.assertEqual(result.outcome, "failure")
        self.assertEqual(latest_entry["job"], "silence-check")
        self.assertIn(">60 minutes", latest_entry["summary"])
