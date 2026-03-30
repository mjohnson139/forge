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
