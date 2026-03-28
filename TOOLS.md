# TOOLS.md

## GitHub Task Board

Repo: `mjohnson139/ray-groove-issues`

### Labels (workflow)
| Label | Meaning | Ray's action |
|-------|---------|--------------|
| `idea` | Not ready | Ignore |
| `ready` | Matt approved — pick up | Move to `in-progress`, act |
| `in-progress` | Being worked on | Monitor |
| `in-review` | PR open, waiting Matt | Notify Matt |
| `feedback` | Matt gave feedback | Pick back up, move to `in-progress` |
| `accepted` | Done | Matt sets this |

### Check the board (use this exact command — label filter is broken in older gh)
```bash
gh issue list --repo mjohnson139/ray-groove-issues \
  --json number,title,body,labels,updatedAt \
  | python3 -c "
import json, sys
issues = json.load(sys.stdin)
actionable = [i for i in issues if any(l['name'] in ['ready','feedback'] for l in i['labels'])]
stale = [i for i in issues if any(l['name'] == 'in-progress' for l in i['labels'])]
print('=== READY/FEEDBACK ===')
for i in actionable:
    labels = [l['name'] for l in i['labels']]
    print(f\"  #{i['number']} [{','.join(labels)}] {i['title']}\")
print('=== IN PROGRESS ===')
for i in stale:
    print(f\"  #{i['number']} {i['title']} (updated: {i['updatedAt'][:10]})\")
"
```

### Move a label
```bash
gh issue edit <n> --repo mjohnson139/ray-groove-issues \
  --remove-label <old> --add-label <new>
```

### Add a comment
```bash
gh issue comment <n> --repo mjohnson139/ray-groove-issues --body "<text>"
```

## Dev (Coding Agent)
Ray never writes code. Delegate to Dev by running Claude Code in the relevant workspace directory.

Handoff format:
```
Dev, implement [feature] on feat/[branch].

Repo: Groove-Breathwork/[repo]
Base: main → Your branch: feat/[branch]
GitHub Issue: #[n]
Model: claude-sonnet-4-6

1. Pull fresh from main
2. Create branch
3. Implement + tests
4. PR against main, link issue #[n], send URL
```

## Slack (coming soon)
Notification target: #ray-groove-manager
