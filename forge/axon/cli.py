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
