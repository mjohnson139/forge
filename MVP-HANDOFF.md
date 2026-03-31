# Forge MVP Handoff

## Status

- Branch: `feat/mvp-foundation`
- Worktree: `/home/matt/dev/ray/worktrees/mvp-main`
- Plan: `docs/superpowers/plans/2026-03-30-forge-mvp-implementation.md`
- State: **merge-ready**
- Tests: **48 passing, 0 failing**

---

## What Is Forge

Forge is an autonomous agent control plane. It monitors a GitHub task board on a cron schedule, picks up actionable issues, assembles a context-rich Brief, dispatches a pipeline (via Attractor), and reports results via Slack. All state is persisted locally in `forge/memory/` and logged to `logs/history.jsonl` (Lens).

---

## How to Run Forge

### Prerequisites

```bash
gh auth login                  # GitHub CLI must be authenticated
export FORGE_GITHUB_TASK_REPO=owner/repo   # or add to TOOLS.md
export FORGE_SLACK_WEBHOOK_URL=https://hooks.slack.com/...  # optional
```

### Manual heartbeat

```bash
cd /home/matt/dev/ray
python3 -m forge.cortex.cli heartbeat --repo-root .
```

### Scheduled heartbeat (Axon)

Preview what would be installed:
```bash
python3 -m forge.axon.cli preview-crontab --registry forge/axon/registry.json
```

Validate registry:
```bash
python3 -m forge.axon.cli validate-registry --registry forge/axon/registry.json
```

Install crontab (requires explicit gate):
```bash
python3 -m forge.axon.cli apply-crontab --registry forge/axon/registry.json --yes-apply
```

This installs three jobs: `cortex-heartbeat` (every 30 min), `board-check` (every 30 min), `silence-check` (hourly at :05).

---

## How to Inspect Memory State

Memory lives in `forge/memory/`:

| File | Contents |
|------|----------|
| `forge/memory/runs.json` | All run records — state, pipeline, timestamps, errors |
| `forge/memory/failures.jsonl` | Append-only failure event log (one JSON object per line) |
| `forge/memory/alert_suppression.json` | Tracks last alert time per run/type to suppress duplicates |
| `forge/memory/tasks/<task-id>.json` | Per-task memory: last outcome, open blockers, recipe hint |
| `forge/memory/recipes.json` | Pattern-matched dispatch recipes with watchouts |

Lens history: `logs/history.jsonl` — every meaningful event logged with timestamp, source, outcome, and next_action.

---

## How Failure Recovery Works

Every failure mode writes traces to **all three sinks**: Lens (`logs/history.jsonl`), Memory (`forge/memory/`), and Uplink (Slack webhook if configured).

| Failure | Detection | Recovery |
|---------|-----------|----------|
| No actionable tasks | `pipeline_service.list()` returns empty | Logged as `skipped`, idle heartbeat sent to Slack |
| GitHub auth failure | `healthcheck()` returns `status: degraded` | Retry once after 5s; if still degraded, record to Memory + Lens + Uplink |
| Rate limit (429) | `healthcheck()` detail contains `429`/`rate limit` | Record immediately, no retry — let next cycle handle |
| Attractor dispatch exception | `dispatcher()` raises `Exception` | Run marked `failed`, failure event appended, Slack alert sent |
| Pipeline timeout | `subprocess.TimeoutExpired` raised | Run marked `failed` with `outcome: timeout`, Slack alert sent |
| Stale running job | `find_stale_runs()` returns runs with heartbeat older than threshold | Run marked `stale`, one-time Slack alert (suppressed within 30 min) |

**Repeat failures trigger watchouts**: if the same `source` has ≥ 2 failure events and a matching recipe exists, a watchout is appended to `forge/memory/recipes.json` automatically.

**Duplicate alert suppression**: stale-run alerts are suppressed if the same `run_id` was alerted within 30 minutes. State persisted in `forge/memory/alert_suppression.json`.

**Retry logic**: GitHub transient failures retry once with a 5s backoff (configurable via `retry_delay_seconds`). Rate limits and pipeline timeouts are not retried.

---

## What Remains Out of Scope

- Live GitHub issue exercise (requires `gh auth` and a real task repo with actionable issues)
- Real Attractor pipeline invocation end-to-end (Attractor binary required at `tools/attractor/attractor`)
- Slack delivery exercise (requires a real webhook URL)
- PR merging — operator always merges

---

## Verification

```
python3 -m unittest discover -s tests -p 'test_*.py' -v
# Ran 48 tests ... OK

python3 -m forge.axon.cli preview-crontab --registry forge/axon/registry.json
# → 3 cron lines, each flock-wrapped

python3 -m forge.axon.cli validate-registry --registry forge/axon/registry.json
# → validated 3 jobs
```

---

## Merge Readiness

**This branch is merge-ready.**

- All 48 tests pass
- No new dependencies (stdlib only)
- All failure modes produce correct traces in Lens + Memory + Uplink
- Axon cron registry validates and previews cleanly
- Operator can install with `--yes-apply` gate
- `TOOLS.md` remains gitignored; `TOOLS.md.example` documents config for local runs
