# Policy System Design

**Date:** 2026-03-28
**Status:** Approved

---

## Problem

Forge operates across multiple repos and work types. Without explicit rules, it makes ad-hoc decisions about branching, PRs, and handoffs. The operator needs a single place to declare operating rules that Cortex will follow consistently.

---

## Design

### Single file: `forge/policies.md`

One markdown file. Cortex reads it at boot, after TOOLS.md, and applies it as operating principles (soft enforcement — judgment, not hard stops).

### Override order

```
global → type
```

Type rules win over global rules where they conflict. No repo-specific overrides unless a real repo earns one.

### Workspace type declaration

Each workspace's `CLAUDE.md` declares its type via a `type:` field in its header. If no type is declared, Cortex defaults to `code`.

Example in a workspace CLAUDE.md:
```
type: content
```

### Two types

| Type | When to use |
|------|-------------|
| `code` | Any repo with software — features, fixes, Remotion, etc. |
| `content` | Repos where the work is drafting copy, markdown, or text assets |

---

## Policy Content

### Global (all work)

- Never merge PRs — operator always merges
- Never send external messages without operator approval
- Always log actions to Lens

### Type: `code`

- Never commit directly to `main` — always use a feature branch (`feat/<task-id>`)
- All work requires a PR against `main`, linked to the GitHub issue
- Dev handoff must include branch name and base branch

### Type: `content`

- Committing directly to `main` is allowed for copy/text changes
- PR optional — use judgment based on scope of change
- No Dev handoff format required — Cortex can handle content work directly

---

## Files Changed

- **Create:** `forge/policies.md`
- **Update:** Cortex boot sequence in `CLAUDE.md` — add `forge/policies.md` to the read order (after TOOLS.md)
- **Update:** `design/cortex-spec.md` — add policies to boot sequence and Brief context
- **Update:** workspace `CLAUDE.md` files — add `type:` declaration where needed

---

## What This Is Not

- Not a hard enforcement system — no pre-commit hooks or automated checks
- Not repo-specific — the two types cover all current work
- Not TOOLS.md — policies are governance rules, TOOLS.md is how-to instructions
