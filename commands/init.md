---
description: Initialize the claude-evolve store in the current project
---

Initialize claude-evolve for this project:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/status.py"
```

The store lives at `.claude/evolve/` and is created automatically on the first captured
signal — no manual init is strictly required. If the user wants learnings committed to
the repo, tell them to add `.claude/evolve/` to git; if they want them local-only, add
`.claude/evolve/` to `.gitignore`.

Explain the loop in one or two lines so the user knows what to expect:
corrections, build failures and fixes are captured as they happen → consolidated on each
turn-end → recurring lessons auto-become skills under `.claude/skills/` → injected into
the next session. Nothing else for them to do.
