# Pipeline — Task Aggregator NLSpec

## Overview

Pipeline is a pluggable fan-in layer. Multiple task sources — GitHub Issues, Linear, Notion, Slack threads, direct operator input — collapse into one normalized work stream. Cortex talks to Pipeline; Pipeline talks to adapters. Cortex never calls GitHub directly.

---

## Responsibilities

- Provide a unified interface for querying and updating tasks regardless of source
- Normalize all task objects to a canonical format
- Route queries to the appropriate adapter based on task source
- Return only tasks that are actionable (status: `ready` or `feedback`) unless asked otherwise
- Update task state (labels, status) on behalf of Cortex

---

## Interface

**Adapter interface** — every adapter must implement:

```
list(filter?: {status?: string[]}) → Task[]
update(id: string, changes: Partial<Task>) → void
```

**Normalized task object** (canonical format):

```
{
  "id":         "<source-prefixed unique ID, e.g. gh-123>",
  "source":     "<github | linear | notion | slack | direct>",
  "title":      "<short summary>",
  "body":       "<full description / acceptance criteria>",
  "labels":     ["<label1>", "<label2>"],
  "status":     "<ready | in-progress | in-review | feedback | accepted | idea>",
  "updated_at": "<ISO 8601 timestamp>",
  "url":        "<link to original task>"
}
```

**Status vocabulary:**

| Status | Meaning |
|--------|---------|
| `ready` | Task is actionable — Cortex should pick it up |
| `in-progress` | Task is being worked on |
| `in-review` | Work is done, awaiting review |
| `feedback` | Reviewer has left comments, Cortex should address |
| `accepted` | Task is complete and accepted |
| `idea` | Backlog / not yet ready |

---

## Behavior

### Query flow

1. Cortex calls `Pipeline.list({status: ['ready', 'feedback']})`
2. Pipeline calls each registered adapter's `list()` method
3. Each adapter queries its source (e.g., `gh issue list`) and maps results to the normalized format
4. Pipeline merges results, sorts by `updated_at` ascending (oldest first), and returns the list
5. Cortex iterates the list, assembles a Brief for each, and dispatches Kinetic

### Update flow

1. Cortex calls `Pipeline.update(id, {status: 'in-progress'})`
2. Pipeline routes the call to the correct adapter based on the `source` field in the id
3. Adapter translates the change to the native API (e.g., adds `in-progress` label via `gh issue edit`)

### Adapter v1: GitHub Issues

- **Repo:** `mjohnson139/ray-groove-issues`
- **Mechanism:** `gh` CLI — no API tokens beyond what `gh auth` provides
- **Label-based workflow:** status is encoded as GitHub labels (e.g., label `ready` = status `ready`)
- **list():** runs `gh issue list --repo mjohnson139/ray-groove-issues --label ready --json number,title,body,labels,updatedAt,url`
- **update():** runs `gh issue edit <number> --remove-label <old> --add-label <new>`

### Adapter stubs (future, not yet implemented)

- **Linear** — via Claude.ai MCP (`mcp__claude_ai_Linear__list_issues`)
- **Notion** — via Claude.ai MCP (`mcp__claude_ai_Notion__notion-search`)
- **Slack threads** — operator-tagged threads as tasks
- **Direct** — operator inputs a task description via Uplink command

---

## Constraints

- **Pipeline never modifies tasks without explicit instruction from Cortex.** Read-mostly by default.
- **Pipeline does not store state.** It queries on demand. No local cache, no persistence layer.
- **Pipeline never calls multiple adapters in parallel** unless explicitly designed for fan-out. Start sequential, measure first (Pike Rule 1).
- **Normalized format is the contract.** Adapters must map to it completely. If a field is unavailable from the source, use `null` — do not omit the key.
- **IDs are source-prefixed** (`gh-123`, `linear-abc`) to prevent collisions across adapters.

---

## Integration Points

| Component | How Pipeline interacts |
|-----------|----------------------|
| **Cortex** | Primary caller — queries for ready/feedback tasks, issues updates |
| **Brief** | Pipeline's normalized task object becomes the `task` field in the Brief |
| **Lens** | Pipeline does not write to Lens directly; Cortex logs Pipeline results |
| **Anvil** | Pipeline relies on Anvil-managed credentials (e.g., `gh auth status` must be healthy) |

---

## Open Questions

- Should Pipeline support a priority or ordering field beyond `updated_at`?
- When adding a new adapter, how does Cortex discover it — auto-scan or explicit registry entry?
- For the GitHub adapter, should `body` include comments/conversation, or only the issue description?
