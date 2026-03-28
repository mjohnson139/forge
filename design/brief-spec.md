# Brief — Context Packet NLSpec

## Overview

A Brief is the full intelligence packet assembled by Cortex before handing off to Kinetic. It is the "smart object" in Forge — per Pike Rule 5, everything else stays stupid. The Brief contains everything Kinetic needs to execute a task; Kinetic should need nothing outside the Brief to do its job.

---

## Responsibilities

- Aggregate task data, history, operator profile, tool health, and active overrides into one coherent packet
- Serve as the single handoff artifact between Cortex and Kinetic
- Be logged to Lens for observability and auditability
- Provide Kinetic with all context via `--context` flags at invocation time

---

## Interface

**Brief schema:**

```
{
  "task": {
    "id":         "<source-prefixed ID>",
    "source":     "<github | linear | ...>",
    "title":      "<task title>",
    "body":       "<full description / acceptance criteria>",
    "labels":     ["<label>"],
    "status":     "<ready | feedback | ...>",
    "updated_at": "<ISO 8601>",
    "url":        "<link to original task>"
  },
  "history": [
    "<last N relevant Lens entries for this task_id or project — summary strings>"
  ],
  "operator": {
    "name":             "<operator name>",
    "timezone":         "<e.g. America/Chicago>",
    "style":            "<communication preferences>",
    "approval_rules":   "<what requires explicit approval>"
  },
  "tools": [
    {
      "name":    "<integration name>",
      "status":  "<healthy | degraded | failed>",
      "checked_at": "<ISO 8601>"
    }
  ],
  "context": {
    "<key>": "<value>"
  },
  "assembled_at": "<ISO 8601 timestamp>"
}
```

**Fields:**

| Field | Source | Purpose |
|-------|--------|---------|
| `task` | Pipeline (normalized task object) | What to work on |
| `history` | Lens (`logs/history.jsonl`, last N entries matching `task_id`) | What has already been tried or decided |
| `operator` | `USER.md` | How to communicate, what needs approval |
| `tools` | Anvil health check results | What integrations are available right now |
| `context` | Uplink `inbox.json` overrides, runtime flags | Active operator overrides (e.g., "focus on X", "skip Y") |
| `assembled_at` | Current timestamp | When this Brief was built |

---

## Behavior

### Assembly process

1. Cortex reads the normalized task from Pipeline
2. Cortex queries `logs/history.jsonl` for entries where `task_id` matches or where project context is relevant — takes last N (default: 10) entries
3. Cortex reads `USER.md` to populate the `operator` field
4. Cortex reads Anvil health status for all active integrations
5. Cortex reads `forge/uplink/inbox.json` for any active operator overrides (keyed by `task_id` or global)
6. Cortex assembles the Brief struct and sets `assembled_at`
7. Brief is serialized and logged to Lens as a single entry (`source: cortex`, `outcome: pending`)
8. Brief is passed to Kinetic as `--context` flags (one flag per leaf value: `--context task_id=<id> --context task_title=<title> --context operator_name=<name> ...`)

### Kinetic invocation with Brief

```
npx attractor workspaces/<project>/pipelines/<pipeline>.dot \
  --context task_id=<id> \
  --context task_title=<title> \
  --context task_body=<body> \
  --context task_url=<url> \
  --context operator_name=<name> \
  --context operator_tz=<tz> \
  --context tool_github=<healthy|degraded|failed> \
  --context override_focus=<value if set> \
  ...
```

Long values (e.g., `task_body`) may be written to a temp file and passed as a file reference if CLI arg length is a concern.

---

## Constraints

- **Brief is immutable once assembled.** If operator context changes mid-run, a new Brief is assembled for the next run — not patched into the running one.
- **Kinetic needs nothing outside the Brief.** If Kinetic requires a piece of context that isn't in the Brief schema, that is a schema gap — fix the schema, not a workaround.
- **Brief is always logged to Lens.** Never dispatch Kinetic without first writing the Brief to `history.jsonl`.
- **`assembled_at` must be accurate.** Do not cache or reuse Briefs across runs.
- **Sensitive operator data** (approval rules, style notes) stays within Forge — never echoed to external services or public logs.

---

## Integration Points

| Component | Role in Brief lifecycle |
|-----------|------------------------|
| **Cortex** | Assembles the Brief; the only component that creates Briefs |
| **Pipeline** | Provides the `task` field |
| **Lens** | Provides the `history` field; receives the assembled Brief as a log entry |
| **USER.md** | Provides the `operator` field |
| **Anvil** | Provides the `tools` field (health status) |
| **Uplink** | Provides the `context` field (operator overrides via `inbox.json`) |
| **Kinetic** | Consumes the Brief via `--context` flags |

---

## Open Questions

- What is the right value of N for history entries? Default 10 — but task-specific history may need to look further back.
- Should `task_body` be truncated if very long, or passed via temp file? Decide at Kinetic integration time.
- Should the Brief be stored as a file (e.g., `forge/briefs/<task_id>-<timestamp>.json`) for debugging, or only exist in Lens?
