# Axon Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Axon's file-driven cron registry and the first runtime helpers so Forge can define scheduled jobs, render safe crontab lines, and run a silence-check job with Lens-compatible logging.

**Architecture:** Axon stays small. A Python stdlib module under `forge/axon/` owns registry parsing, command rendering, crontab line generation, and the silence-check job. The registry remains the source of truth, cron execution stays external, and every meaningful Axon action writes a Lens entry or produces the payload needed to do so.

**Tech Stack:** Python 3 stdlib, JSON, `unittest`, shell `flock`, Markdown

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Create | `forge/axon/__init__.py` | Package marker for Axon modules |
| Create | `forge/axon/registry.json` | Initial Axon job registry |
| Create | `forge/axon/registry.py` | Registry load/validate/save helpers |
| Create | `forge/axon/runtime.py` | Cron command and crontab line rendering helpers |
| Create | `forge/axon/lens.py` | Minimal append-only Lens helpers for Axon jobs |
| Create | `forge/axon/jobs/__init__.py` | Package marker for Axon jobs |
| Create | `forge/axon/jobs/silence_check.py` | Silence detection job |
| Create | `forge/axon/cli.py` | Small CLI for validate/preview/silence-check |
| Create | `forge/uplink/inbox.json` | Initial empty inbound queue file |
| Create | `logs/.gitkeep` | Track logs directory scaffold |
| Create | `tests/axon/test_registry.py` | Registry/runtime tests |
| Create | `tests/axon/test_silence_check.py` | Silence-check tests |
| Create | `AXON-HANDOFF.md` | Run status and next-step handoff |
| Modify | `.gitignore` | Ignore Axon runtime log files |

---

### Task 1: Axon Scaffolding

**Files:**
- Create: `logs/.gitkeep`
- Create: `forge/axon/__init__.py`
- Create: `forge/axon/jobs/__init__.py`
- Create: `forge/uplink/inbox.json`
- Modify: `.gitignore`

- [ ] **Step 1: Add the failing repo-scaffold test**

Create `tests/axon/test_registry.py` with:

```python
import pathlib
import unittest


class RepoScaffoldTest(unittest.TestCase):
    def test_expected_axon_paths_exist(self) -> None:
        repo_root = pathlib.Path(__file__).resolve().parents[2]
        self.assertTrue((repo_root / "forge" / "uplink" / "inbox.json").exists())
        self.assertTrue((repo_root / "logs" / ".gitkeep").exists())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.axon.test_registry.RepoScaffoldTest.test_expected_axon_paths_exist -v`

Expected: `FAIL` because the Axon scaffold files do not exist yet.

- [ ] **Step 3: Add the minimal scaffold**

Create:

```text
forge/axon/__init__.py
forge/axon/jobs/__init__.py
forge/uplink/inbox.json   -> []
logs/.gitkeep
```

Append to `.gitignore`:

```gitignore
# Axon runtime logs
logs/*.log
logs/*.log.1
logs/*.log.2
logs/*.log.3
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.axon.test_registry.RepoScaffoldTest.test_expected_axon_paths_exist -v`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add .gitignore forge/axon/__init__.py forge/axon/jobs/__init__.py forge/uplink/inbox.json logs/.gitkeep tests/axon/test_registry.py
git commit -m "chore: scaffold Axon runtime directories"
```

---

### Task 2: Registry and Runtime Rendering

**Files:**
- Create: `forge/axon/registry.json`
- Create: `forge/axon/registry.py`
- Create: `forge/axon/runtime.py`
- Modify: `tests/axon/test_registry.py`

- [ ] **Step 1: Write the failing registry tests**

Add to `tests/axon/test_registry.py`:

```python
import json
import tempfile

from forge.axon.registry import load_registry
from forge.axon.runtime import build_claude_command, render_crontab_line


class RegistryRuntimeTest(unittest.TestCase):
    def test_load_registry_returns_jobs_in_file_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "registry.json"
            path.write_text(json.dumps([
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
            ]), encoding="utf-8")

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.axon.test_registry.RegistryRuntimeTest -v`

Expected: `ImportError` or `FAIL` because the Axon registry/runtime modules do not exist yet.

- [ ] **Step 3: Write the minimal implementation**

Create `forge/axon/registry.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class Job:
    name: str
    schedule: str
    command: str
    last_run: str | None
    last_outcome: str | None


def load_registry(path: str | Path) -> list[Job]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Job(**item) for item in data]
```

Create `forge/axon/runtime.py` with:

```python
from __future__ import annotations

import shlex


def build_claude_command(*, repo_root: str, prompt: str, job_name: str) -> str:
    quoted_prompt = shlex.quote(prompt)
    return (
        f"cd {shlex.quote(repo_root)} && "
        f"claude --print {quoted_prompt} >> logs/{job_name}.log 2>&1"
    )


def render_crontab_line(*, schedule: str, job_name: str, command: str) -> str:
    lock_path = f"/tmp/.axon-{job_name}.lock"
    wrapped = f"flock -n {shlex.quote(lock_path)} bash -lc {shlex.quote(command)}"
    return f"{schedule} {wrapped}"
```

Create `forge/axon/registry.json` with:

```json
[
  {
    "name": "board-check",
    "schedule": "*/30 * * * *",
    "command": "cd /home/matt/dev/ray && claude --print 'Check the GitHub task board. Log results.' >> logs/board-check.log 2>&1",
    "last_run": null,
    "last_outcome": null
  },
  {
    "name": "silence-check",
    "schedule": "5 * * * *",
    "command": "cd /home/matt/dev/ray && python3 -m forge.axon.cli silence-check --repo-root /home/matt/dev/ray >> logs/silence-check.log 2>&1",
    "last_run": null,
    "last_outcome": null
  }
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.axon.test_registry.RegistryRuntimeTest -v`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add forge/axon/registry.json forge/axon/registry.py forge/axon/runtime.py tests/axon/test_registry.py
git commit -m "feat: add Axon registry and crontab rendering"
```

---

### Task 3: Lens Append Helpers and Silence Detection

**Files:**
- Create: `forge/axon/lens.py`
- Create: `forge/axon/jobs/silence_check.py`
- Create: `tests/axon/test_silence_check.py`

- [ ] **Step 1: Write the failing silence-check tests**

Create `tests/axon/test_silence_check.py`:

```python
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
                json.dumps({
                    "timestamp": "2026-03-29T21:45:00+00:00",
                    "source": "axon-cron",
                    "job": "board-check",
                    "summary": "Board checked.",
                    "outcome": "success",
                    "next_action": "none",
                    "task_id": None,
                }) + "\n",
                encoding="utf-8",
            )

            result = run_silence_check(repo_root=repo_root, now_iso="2026-03-29T22:00:00+00:00")

        self.assertFalse(result.alert_needed)
        self.assertEqual(result.outcome, "success")

    def test_stale_history_appends_failure_entry_and_requests_alert(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = pathlib.Path(tmp)
            logs_dir = repo_root / "logs"
            logs_dir.mkdir()
            history_path = logs_dir / "history.jsonl"
            history_path.write_text(
                json.dumps({
                    "timestamp": "2026-03-29T19:30:00+00:00",
                    "source": "axon-cron",
                    "job": "board-check",
                    "summary": "Board checked.",
                    "outcome": "success",
                    "next_action": "none",
                    "task_id": None,
                }) + "\n",
                encoding="utf-8",
            )

            result = run_silence_check(repo_root=repo_root, now_iso="2026-03-29T22:00:00+00:00")
            lines = history_path.read_text(encoding="utf-8").strip().splitlines()

        self.assertTrue(result.alert_needed)
        self.assertEqual(result.outcome, "failure")
        self.assertEqual(len(lines), 2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.axon.test_silence_check -v`

Expected: `ImportError` or `FAIL` because the Lens/silence-check modules do not exist yet.

- [ ] **Step 3: Write the minimal implementation**

Create `forge/axon/lens.py` with:

```python
from __future__ import annotations

import json
from pathlib import Path


def append_history_entry(repo_root: str | Path, entry: dict[str, object]) -> None:
    logs_dir = Path(repo_root) / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    history_path = logs_dir / "history.jsonl"
    history_path.open("a", encoding="utf-8").write(json.dumps(entry) + "\n")
```

Create `forge/axon/jobs/silence_check.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from forge.axon.lens import append_history_entry


@dataclass(frozen=True)
class SilenceCheckResult:
    outcome: str
    alert_needed: bool
    summary: str


def run_silence_check(*, repo_root: str | Path, now_iso: str | None = None, max_silence_minutes: int = 60) -> SilenceCheckResult:
    repo_root = Path(repo_root)
    history_path = repo_root / "logs" / "history.jsonl"
    now = datetime.fromisoformat(now_iso) if now_iso else datetime.now(timezone.utc)
    entries = history_path.read_text(encoding="utf-8").splitlines() if history_path.exists() else []
    last_entry = json.loads(entries[-1]) if entries else None
    last_timestamp = datetime.fromisoformat(last_entry["timestamp"]) if last_entry else None

    if last_timestamp and now - last_timestamp <= timedelta(minutes=max_silence_minutes):
        append_history_entry(repo_root, {
            "timestamp": now.isoformat(),
            "source": "axon-cron",
            "job": "silence-check",
            "summary": "Silence check passed.",
            "outcome": "success",
            "next_action": "none",
            "task_id": None,
        })
        return SilenceCheckResult("success", False, "Silence check passed.")

    summary = "No Forge activity in >60 minutes."
    append_history_entry(repo_root, {
        "timestamp": now.isoformat(),
        "source": "axon-cron",
        "job": "silence-check",
        "summary": summary,
        "outcome": "failure",
        "next_action": "dispatch uplink alert",
        "task_id": None,
    })
    return SilenceCheckResult("failure", True, summary)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.axon.test_silence_check -v`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add forge/axon/lens.py forge/axon/jobs/silence_check.py tests/axon/test_silence_check.py
git commit -m "feat: add Axon silence check job"
```

---

### Task 4: CLI Surface

**Files:**
- Create: `forge/axon/cli.py`
- Modify: `tests/axon/test_registry.py`

- [ ] **Step 1: Write the failing CLI tests**

Add to `tests/axon/test_registry.py`:

```python
import subprocess
import sys


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.axon.test_registry.AxonCliTest -v`

Expected: `FAIL` because the CLI does not exist yet.

- [ ] **Step 3: Write the minimal CLI**

Create `forge/axon/cli.py` with:

```python
from __future__ import annotations

import argparse
from pathlib import Path

from forge.axon.jobs.silence_check import run_silence_check
from forge.axon.registry import load_registry
from forge.axon.runtime import render_crontab_line


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m forge.axon.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-registry")
    validate.add_argument("--registry", required=True)

    preview = subparsers.add_parser("preview-crontab")
    preview.add_argument("--registry", required=True)

    silence = subparsers.add_parser("silence-check")
    silence.add_argument("--repo-root", required=True)
    silence.add_argument("--max-silence-minutes", type=int, default=60)

    args = parser.parse_args()

    if args.command == "validate-registry":
        jobs = load_registry(args.registry)
        print(f"validated {len(jobs)} jobs")
        return 0
    if args.command == "preview-crontab":
        for job in load_registry(args.registry):
            print(render_crontab_line(schedule=job.schedule, job_name=job.name, command=job.command))
        return 0

    result = run_silence_check(repo_root=Path(args.repo_root), max_silence_minutes=args.max_silence_minutes)
    print(result.summary)
    return 0 if result.outcome == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.axon.test_registry.AxonCliTest -v`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add forge/axon/cli.py tests/axon/test_registry.py
git commit -m "feat: add Axon CLI commands"
```

---

### Task 5: Verification and Handoff

**Files:**
- Modify: `AXON-HANDOFF.md`

- [ ] **Step 1: Run the full Axon test suite**

Run: `python3 -m unittest discover -s tests -p 'test_*.py' -v`

Expected: all Axon tests pass.

- [ ] **Step 2: Capture crontab preview output**

Run: `python3 -m forge.axon.cli preview-crontab --registry forge/axon/registry.json`

Expected: one rendered line per job, each wrapped with `flock -n`.

- [ ] **Step 3: Update `AXON-HANDOFF.md`**

Record:
- current branch
- completed tasks
- latest verification commands and results
- remaining work: Uplink alert delivery, registry last_run updates, operator-approved crontab install path

- [ ] **Step 4: Commit**

```bash
git add AXON-HANDOFF.md
git commit -m "docs: update Axon handoff"
```
