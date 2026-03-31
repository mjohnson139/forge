from __future__ import annotations

import argparse
from pathlib import Path
import subprocess

from forge.axon.jobs.silence_check import run_silence_check
from forge.axon.registry import load_registry
from forge.axon.runtime import install_crontab, merge_managed_crontab, render_crontab_line


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m forge.axon.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-registry")
    validate.add_argument("--registry", required=True)

    preview = subparsers.add_parser("preview-crontab")
    preview.add_argument("--registry", required=True)

    apply = subparsers.add_parser("apply-crontab")
    apply.add_argument("--registry", required=True)
    apply.add_argument("--yes-apply", action="store_true")

    silence = subparsers.add_parser("silence-check")
    silence.add_argument("--repo-root", required=True)
    silence.add_argument("--max-silence-minutes", type=int, default=60)

    args = parser.parse_args()

    try:
        if args.command == "validate-registry":
            jobs = load_registry(args.registry)
            print(f"validated {len(jobs)} jobs")
            return 0
        if args.command == "preview-crontab":
            for job in load_registry(args.registry):
                print(
                    render_crontab_line(
                        schedule=job.schedule,
                        job_name=job.name,
                        command=job.command,
                    )
                )
            return 0
        if args.command == "apply-crontab":
            if not args.yes_apply:
                parser.exit(status=2, message="error: apply-crontab requires --yes-apply\n")
            managed_lines = [
                render_crontab_line(
                    schedule=job.schedule,
                    job_name=job.name,
                    command=job.command,
                )
                for job in load_registry(args.registry)
            ]
            existing = _read_current_crontab()
            merged = merge_managed_crontab(existing=existing, managed_lines=managed_lines)
            print(merged, end="")
            install_crontab(crontab_text=merged)
            return 0

        result = run_silence_check(
            repo_root=Path(args.repo_root),
            max_silence_minutes=args.max_silence_minutes,
        )
        print(result.summary)
        return 0 if result.outcome == "success" else 1
    except ValueError as exc:
        parser.exit(status=2, message=f"error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())


def _read_current_crontab() -> str:
    result = subprocess.run(
        ["crontab", "-l"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return result.stdout
    stderr = (result.stderr or "").lower()
    if "no crontab for" in stderr:
        return ""
    raise RuntimeError(result.stderr.strip() or "crontab -l failed")
