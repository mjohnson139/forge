from __future__ import annotations

import argparse
from pathlib import Path

from forge.cortex.runtime import CortexRuntime
from forge.cortex.memory import MemoryStore
from forge.pipeline.service import PipelineService


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m forge.cortex.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    heartbeat = subparsers.add_parser("heartbeat")
    heartbeat.add_argument("--repo-root", default=".")

    args = parser.parse_args()

    if args.command == "heartbeat":
        repo_root = Path(args.repo_root).resolve()
        runtime = CortexRuntime(
            repo_root=repo_root,
            pipeline_service=PipelineService(repo_root=repo_root),
            memory_store=MemoryStore(repo_root=repo_root),
        )
        result = runtime.heartbeat()
        print(result.summary)
        return 0 if result.outcome in {"success", "skipped"} else 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
