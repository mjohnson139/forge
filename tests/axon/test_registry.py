import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


class RepoScaffoldTest(unittest.TestCase):
    def test_expected_axon_paths_exist(self) -> None:
        repo_root = pathlib.Path(__file__).resolve().parents[2]
        self.assertTrue((repo_root / "forge" / "uplink" / "inbox.json").exists())
        self.assertTrue((repo_root / "logs" / ".gitkeep").exists())


from forge.axon.registry import load_registry
from forge.axon.runtime import (
    build_claude_command,
    install_crontab,
    merge_managed_crontab,
    render_crontab_line,
)


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

    def test_merge_managed_crontab_replaces_existing_forge_block(self) -> None:
        existing = "\n".join(
            [
                "MAILTO=\"\"",
                "# forge-axon:start",
                "old line",
                "# forge-axon:end",
                "@daily echo keep",
            ]
        )

        merged = merge_managed_crontab(existing=existing, managed_lines=["*/30 * * * * echo fresh"])

        self.assertIn("MAILTO=\"\"", merged)
        self.assertIn("*/30 * * * * echo fresh", merged)
        self.assertNotIn("old line", merged)
        self.assertIn("@daily echo keep", merged)

    def test_install_crontab_passes_merged_content_to_crontab_command(self) -> None:
        calls: list[tuple[list[str], str]] = []

        def runner(cmd: list[str], **kwargs: object):
            calls.append((cmd, kwargs["input"]))  # type: ignore[index]
            return mock.Mock(returncode=0, stdout="", stderr="")

        install_crontab(
            crontab_text="MAILTO=\"\"\n# forge-axon:start\nline\n# forge-axon:end\n",
            runner=runner,
        )

        self.assertEqual(calls[0][0], ["crontab", "-"])
        self.assertIn("# forge-axon:start", calls[0][1])

    def test_load_registry_rejects_duplicate_job_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "registry.json"
            path.write_text(
                json.dumps(
                    [
                        {
                            "name": "board-check",
                            "schedule": "*/30 * * * *",
                            "command": "echo first",
                            "last_run": None,
                            "last_outcome": None,
                        },
                        {
                            "name": "board-check",
                            "schedule": "5 * * * *",
                            "command": "echo second",
                            "last_run": None,
                            "last_outcome": "pending",
                        },
                    ]
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "duplicate job name"):
                load_registry(path)

    def test_load_registry_rejects_invalid_outcome(self) -> None:
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
                            "last_outcome": "done",
                        }
                    ]
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "last_outcome"):
                load_registry(path)


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

    def test_validate_registry_command_exits_nonzero_for_invalid_registry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = pathlib.Path(tmp) / "registry.json"
            registry_path.write_text(
                json.dumps(
                    [
                        {
                            "name": "board-check",
                            "schedule": "@hourly",
                            "command": "echo board",
                            "last_run": None,
                            "last_outcome": None,
                        }
                    ]
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "forge.axon.cli",
                    "validate-registry",
                    "--registry",
                    str(registry_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("schedule", result.stderr)

    def test_apply_crontab_requires_explicit_yes_flag(self) -> None:
        repo_root = pathlib.Path(__file__).resolve().parents[2]
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "forge.axon.cli",
                "apply-crontab",
                "--registry",
                str(repo_root / "forge" / "axon" / "registry.json"),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("--yes-apply", result.stderr)
