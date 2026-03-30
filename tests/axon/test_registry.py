import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


class RepoScaffoldTest(unittest.TestCase):
    def test_expected_axon_paths_exist(self) -> None:
        repo_root = pathlib.Path(__file__).resolve().parents[2]
        self.assertTrue((repo_root / "forge" / "uplink" / "inbox.json").exists())
        self.assertTrue((repo_root / "logs" / ".gitkeep").exists())


from forge.axon.registry import load_registry
from forge.axon.runtime import build_claude_command, render_crontab_line


class RegistryRuntimeTest(unittest.TestCase):
    def test_load_registry_returns_jobs_in_file_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "registry.json"
            path.write_text(
                json.dumps(
                    [
                        {
                            "name": "board-check",
                            "schedule": "*/30 * * * *",
                            "command": "echo board",
                            "last_run": None,
                            "last_outcome": None,
                        },
                        {
                            "name": "silence-check",
                            "schedule": "5 * * * *",
                            "command": "echo silence",
                            "last_run": None,
                            "last_outcome": "pending",
                        },
                    ]
                ),
                encoding="utf-8",
            )

            jobs = load_registry(path)

        self.assertEqual([job.name for job in jobs], ["board-check", "silence-check"])

    def test_build_claude_command_writes_to_named_job_log(self) -> None:
        command = build_claude_command(
            repo_root="/home/matt/dev/ray",
            prompt="Check the task board. Log results.",
            job_name="board-check",
        )
        self.assertIn("cd /home/matt/dev/ray", command)
        self.assertIn("logs/board-check.log", command)
        self.assertIn("claude --print", command)

    def test_render_crontab_line_wraps_job_with_flock(self) -> None:
        line = render_crontab_line(
            schedule="*/30 * * * *",
            job_name="board-check",
            command="cd /home/matt/dev/ray && claude --print 'hi'",
        )
        self.assertTrue(line.startswith("*/30 * * * * flock -n "))
        self.assertIn(".axon-board-check.lock", line)
        self.assertIn("bash -lc", line)


class AxonCliTest(unittest.TestCase):
    def test_validate_registry_command_exits_zero_for_valid_registry(self) -> None:
        repo_root = pathlib.Path(__file__).resolve().parents[2]
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "forge.axon.cli",
                "validate-registry",
                "--registry",
                str(repo_root / "forge" / "axon" / "registry.json"),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("validated", result.stdout)
