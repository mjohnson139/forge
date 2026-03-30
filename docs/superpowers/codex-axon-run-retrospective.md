# Codex Axon Run Retrospective

This document captures what the operator expected from the `feat/axon` Codex run, what actually happened, and the workflow requirements that should become a reusable Forge skill. This is explicitly based on the Codex Axon run in `/home/matt/dev/ray/worktrees/axon` on 2026-03-30.

## Why This Exists

The Axon branch produced useful code, but the surrounding execution workflow was incomplete. The implementation landed in the worktree, yet the operator-facing monitoring, GitHub feedback loop, cleanup, and closeout protocol were only partially realized. Future Forge skills should treat those workflow steps as first-class deliverables, not optional orchestration extras.

## Operator Expectations

The expected behavior for future long-running Codex or Claude implementation runs is:

1. Create an hourly monitoring job that reports progress to Slack with the assignment, branch, worktree, active tmux sessions, and current state.
2. Commit incrementally to the feature branch, push the branch, and open a pull request early so review can happen while implementation is still in flight.
3. Detect and handle model or subscription rate limits gracefully, with clear status updates and handoff guidance if progress stalls.
4. Remove temporary monitor crons and helper processes once the run completes or hands off.
5. Run explicit verification steps and report what was actually tested.
6. Produce a final merge-readiness report and a human handoff guide with risks, open questions, and operator watchouts.

## What Happened In The Codex Axon Run

### What worked

- The worker completed the planned Axon implementation in `feat/axon`.
- The worktree ended clean.
- A real feature commit was created: `3b80605 feat: implement Axon cron runtime — silence-check, registry, CLI, tests`.
- Verification was run and recorded in the handoff notes.
- A local status file existed and captured useful state.

### What was missing

- The status loop did not keep the local status file in sync with the true terminal state. `AXON-STATUS.md` still said `State: running` after the worker had already completed.
- There was no hourly Slack progress report that mirrored the kickoff context and current tmux state.
- The branch was not pushed and no pull request was opened during implementation, which removed the fast feedback path.
- There was no explicit rate-limit handling path in the monitor logic.
- There was no explicit monitor-cron cleanup step recorded at completion.
- The end-of-run closeout existed only as a local handoff note, not as a merge-readiness report intended for operator review.

## Required Workflow For The Future Skill

### 1. Kickoff

At run start, create:

- a feature branch
- a dedicated worktree
- a worker tmux session
- a monitor tmux session
- a status markdown file in the repo root
- an initial Slack kickoff message

The kickoff Slack message must include:

- assignment summary
- branch name
- worktree path
- worker session name
- monitor session name
- status file path
- next expected checkpoint time

### 2. Monitoring

The monitor must run at least hourly and update both Slack and the local status file. Each update should include:

- original assignment
- current phase
- latest commit sha and subject
- `git status --short`
- whether the worker and monitor tmux sessions still exist
- the tail of the worker pane
- any blocker, especially auth, sandbox, network, or rate-limit failures
- the next action

If the worker exits, the monitor must immediately switch from heartbeat mode to closeout mode.

### 3. GitHub Feedback Loop

The workflow should create review surfaces early:

- first small commit as soon as scaffolding or the first vertical slice is working
- branch push immediately after the first meaningful commit
- draft PR creation immediately after the first push
- follow-up commits pushed continuously as milestones land

The PR body should include:

- assignment summary
- implementation checklist
- verification checklist
- known risks or incomplete items
- instructions for testing locally

### 4. Rate-Limit Handling

The monitor should treat model exhaustion and throttling as normal operational states. On rate-limit detection it should:

- capture the exact error text
- mark the run as `blocked-rate-limit`
- send Slack with the failure mode and timestamp
- write a short handoff with the last safe resume command
- avoid claiming the run is still progressing normally

The monitor should distinguish between:

- transient retryable rate limits
- hard subscription exhaustion
- unrelated tool or sandbox errors

### 5. Verification Standard

Every implementation run should leave behind a verification section with:

- commands run
- pass or fail result
- any tests not run
- any manual inspection performed
- remaining unverified risk

For the Codex Axon run, the recorded verification included unit tests, CLI validation, and crontab preview rendering. That was useful and should remain part of the template.

### 6. Completion And Cleanup

When the worker completes or hands off:

- stop any monitor cron or scheduled loop
- remove temporary monitor artifacts if they are not part of the product
- update the status file to a terminal state
- send a final Slack summary
- prepare merge-readiness notes
- prepare operator handoff notes

The final Slack summary should include:

- assignment summary
- final branch and PR link
- verification outcome
- merge readiness
- any operator action required

## Merge-Readiness Deliverables

Every future run should produce both:

### Merge readiness report

This is the concise reviewer-facing artifact. It should answer:

- what changed
- what was verified
- what remains risky
- whether the branch is ready for merge

### Human handoff guide

This is the operator-facing artifact. It should answer:

- how to resume work
- what to watch in logs or sessions
- what follow-up tasks are still open
- what failure modes are most likely next

## Concrete Skill Requirements

The eventual Forge skill should own this lifecycle end to end:

- bootstrap branch, worktree, tmux, status file, and Slack kickoff
- start and later remove an hourly monitor
- maintain Slack and local status updates
- push branch and open PR early
- handle rate limits explicitly
- run verification and summarize evidence
- publish merge-readiness and handoff documents at the end

## Codex Axon Run Notes

The Codex Axon run was successful on implementation, but incomplete on orchestration. The code branch moved forward; the operator workflow did not. The lesson is that the execution wrapper needs to be treated as product behavior. Future Codex and Claude run plans should include those orchestration steps as required checklist items with explicit completion criteria.
