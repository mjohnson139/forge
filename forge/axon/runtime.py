from __future__ import annotations

import shlex
import subprocess
from typing import Callable


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


def merge_managed_crontab(*, existing: str, managed_lines: list[str]) -> str:
    start_marker = "# forge-axon:start"
    end_marker = "# forge-axon:end"
    managed_block = "\n".join([start_marker, *managed_lines, end_marker])

    if start_marker in existing and end_marker in existing:
        before, _, remainder = existing.partition(start_marker)
        _, _, after = remainder.partition(end_marker)
        pieces = [before.rstrip("\n"), managed_block, after.lstrip("\n")]
        return "\n".join(piece for piece in pieces if piece).rstrip("\n") + "\n"

    base = existing.rstrip("\n")
    pieces = [piece for piece in (base, managed_block) if piece]
    return "\n\n".join(pieces).rstrip("\n") + "\n"


def install_crontab(
    *,
    crontab_text: str,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> None:
    command_runner = runner or subprocess.run
    result = command_runner(
        ["crontab", "-"],
        input=crontab_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "crontab install failed")
