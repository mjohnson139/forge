# Forge MVP Handoff

## Status

- Branch: `feat/mvp-foundation`
- Worktree: `/home/matt/dev/ray/worktrees/mvp-main`
- Plan: `docs/superpowers/plans/2026-03-30-forge-mvp-implementation.md`
- State: `in progress`
- Current task: `Task 7 follow-through — Slack delivery, task-source config, and Axon crontab apply flow`

## Completed So Far

- Merged Axon and Lens root-repo PRs into `main`
- Created `feat/mvp-foundation` from merged `main`
- Added Memory as an explicit design component
- Added the Forge MVP implementation plan
- Implemented the core Cortex slices:
  - `forge/cortex/memory.py`
  - `forge/cortex/brief.py`
  - `forge/cortex/runtime.py`
  - `forge/cortex/cli.py`
- Implemented the Pipeline GitHub adapter/service slice
- Implemented Slack message builders for Uplink heartbeat/failure summaries
- Added webhook-backed Slack delivery for Cortex runtime notifications via `FORGE_SLACK_WEBHOOK_URL` or local `TOOLS.md`
- Seeded `forge/memory/` runtime files
- Added Cortex, Pipeline, and integration test coverage
- Added the first Forge pipeline definitions:
  - `forge/pipelines/github-task.dot`
  - `forge/pipelines/github-task-qa.dot`
- Added `cortex-heartbeat` to the Axon registry
- Added operator-gated Axon `apply-crontab` support with managed-block merge behavior
- Documented practical task-source and Slack config in `TOOLS.md.example`

## Verification

- `python3 -m unittest discover -s tests -p 'test_*.py' -v`
  - Result: `Ran 30 tests ... OK`
- `python3 -m forge.axon.cli preview-crontab --registry forge/axon/registry.json`
  - Result: rendered `cortex-heartbeat`, `board-check`, and `silence-check` cron lines with `flock` wrapping
- `python3 -m forge.cortex.cli heartbeat --repo-root /home/matt/dev/ray/worktrees/mvp-main`
  - Result: `No actionable tasks found.`
- `gh auth status`
  - Result: configured account present but token invalid, so live GitHub task-source exercise is currently blocked on re-auth

## Next Steps

1. Re-auth `gh` in this environment, then exercise `github-task.dot` against a real actionable issue source.
2. Optionally set local `TOOLS.md` and/or `FORGE_GITHUB_TASK_REPO` plus `FORGE_SLACK_WEBHOOK_URL` before scheduled runs.
3. If desired, run `python3 -m forge.axon.cli apply-crontab --registry forge/axon/registry.json --yes-apply` from the real repo root to install the managed Axon cron block.
4. Commit and push the next MVP slice.

## Notes

- `tools/attractor` Lens changes were pushed separately to the nested `attractor` repository.
- Old completed tmux worker sessions from Axon and Lens were cleaned up before starting MVP work.
- The real Attractor QA invocation did not yield a useful captured result in this shell environment, so current verification is based on the Python integration suite plus direct Cortex CLI runs.
- `TOOLS.md` remains gitignored; `TOOLS.md.example` is the tracked place to document task-repo and Slack webhook configuration for local scheduled runs.
