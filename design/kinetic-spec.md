# Kinetic — Task Engine NLSpec

## Overview

Kinetic IS Attractor (`mjohnson139/attractor`). It is not reimplemented — it is wired in. Kinetic receives a Brief from Cortex and executes the corresponding DOT pipeline graph, traversing nodes that call Claude Code, shell tools, direct LLM calls, or human approval gates via Uplink.

---

## Responsibilities

- Accept a Brief (via `--context` flags) and a pipeline definition (`.dot` file)
- Execute the pipeline graph node by node
- Route human gate nodes to Uplink for operator approval before proceeding
- Feed execution outcomes back into Lens
- Resume from the last checkpoint if a run is interrupted
- Never pick tasks directly — only receive Briefs from Cortex

---

## Interface

**Invocation:**

```
npx attractor <pipeline.dot> \
  --context task_id=<id> \
  --context task_title=<title> \
  --context task_body=<body> \
  --context task_url=<url> \
  --context operator_name=<name> \
  --context operator_tz=<tz> \
  --context tool_github=<healthy|degraded|failed> \
  [--context override_<key>=<value> ...]
```

**Pipeline definitions:** `workspaces/<project>/pipelines/*.dot`

**Outputs:**
- Node execution results (stdout/stderr per node)
- Lens entries appended to `logs/history.jsonl` after each completed node
- Human gate messages dispatched via Uplink
- Checkpoint state (managed internally by Attractor)

---

## Behavior

### Pipeline graph execution

1. Cortex invokes Kinetic with a `.dot` file path and all Brief fields as `--context` flags
2. Attractor parses the DOT graph and begins traversal from the entry node
3. Each node executes its handler (see handler types below)
4. On successful node completion: Attractor evaluates outgoing edges and routes to the next node(s)
5. On node failure: Attractor follows the error edge if defined, or halts and logs the failure
6. On graph completion: Attractor exits; Cortex reads Lens entries to determine outcome

### Node handler types

| Handler | Behavior |
|---------|---------|
| `codergen` | Invokes Claude Code — spawns a `claude` subprocess with a specific coding prompt. This is how Kinetic delegates implementation work to Dev. |
| `tool` | Runs a shell command or CLI tool (e.g., `gh pr create`, `npm test`) |
| `llm` | Makes a direct LLM call without a full Claude Code session — for classification, summarization, planning decisions |
| `human` | Human approval gate — pauses execution, sends request via Uplink, waits for operator reply |

### Human gate behavior

1. Attractor reaches a `human` node
2. Kinetic serializes the approval request: task title, decision required, options (e.g., "approve / reject / skip")
3. Request is dispatched via Uplink to `#ray-groove-manager` on Slack
4. Attractor pauses — it checkpoints state and waits
5. Uplink polls for operator reply on its Axon cron (every 60 seconds)
6. When reply arrives, Uplink writes it to `forge/uplink/inbox.json`
7. Cortex reads `inbox.json`, finds the pending gate decision, and resumes Attractor with the result
8. Attractor reads the decision from context and routes accordingly

### Checkpoint / resume

If a Kinetic run is interrupted (process killed, timeout, error):
- Attractor saves checkpoint state to its internal store after each completed node
- On next invocation with the same `task_id`, Attractor detects the checkpoint and resumes from the last completed node
- Cortex does not need to re-assemble the Brief — the checkpoint includes the context state

### Lens integration

After each completed node (or on failure), Kinetic appends an entry to `logs/history.jsonl`:

```
{
  "timestamp":   "<ISO 8601>",
  "source":      "kinetic",
  "job":         "<task_id>-<node_name>",
  "summary":     "<what the node did>",
  "outcome":     "success | failure | partial | skipped | pending",
  "next_action": "<next node or 'complete'>",
  "task_id":     "<task_id>"
}
```

### Standard pipeline types

| Pipeline | File | Use case |
|----------|------|---------|
| Coding task | `coding-task.dot` | Implement a feature or fix; delegates to `codergen` |
| Research task | `research-task.dot` | Investigate, summarize, or analyze; uses `llm` + `tool` nodes |
| Review task | `review-task.dot` | Review a PR or doc; uses `llm` node + `human` gate for approval |

Pipeline definitions live in `workspaces/<project>/pipelines/`. A project with no custom pipelines falls back to defaults in `forge/pipelines/`.

---

## Constraints

- **Kinetic never picks tasks directly.** It only receives Briefs from Cortex. Cortex is the decision-maker.
- **Kinetic never writes to Pipeline.** It does not update task status — Cortex does, based on Kinetic's Lens output.
- **Kinetic never sends messages to Uplink directly** except through the human gate mechanism defined in the `.dot` pipeline.
- **All context comes from the Brief.** Kinetic does not read `USER.md`, `TOOLS.md`, or other config files — everything it needs is in `--context` flags.
- **Pipeline definitions are version-controlled.** `.dot` files live in the workspace repo, not generated at runtime.

---

## Integration Points

| Component | How Kinetic interacts |
|-----------|----------------------|
| **Cortex** | Receives invocation; Cortex reads Lens output to determine task outcome |
| **Brief** | All task context arrives via `--context` flags derived from the Brief |
| **Lens** | Appends structured entries after each node completion |
| **Uplink** | Human gate nodes send approval requests; Uplink delivers replies via `inbox.json` |
| **Pipeline** | No direct interaction — Cortex updates Pipeline based on Kinetic outcomes |

---

## Open Questions

- How does Attractor's checkpoint store interact with the Forge file layout — where does Attractor write its checkpoint files?
- For the `codergen` handler: does Attractor spawn a full `claude` subprocess, or call the Claude API directly?
- What happens if a human gate times out (operator doesn't reply in N hours)? Define timeout + escalation behavior.
- CXDB history ingest: how does Attractor's conversation history feed integrate with Lens `history.jsonl`?
