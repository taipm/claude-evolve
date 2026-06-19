---
description: LLM-assisted review of accumulated learnings — dedup, sharpen, promote
---

You are reviewing this project's accumulated learnings to keep them sharp and useful.

1. Show the current state:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/status.py"
   ```

2. Read the raw store at `.claude/evolve/learnings.json` (in the project dir).

3. For the active learnings, assess and report:
   - **Duplicates / overlaps** — learnings that say the same thing under different
     wording (the normalized-key dedup is structural; you catch semantic overlap).
   - **Vague or environment-specific** entries that should be dropped (missing binaries,
     transient network/credential errors — these are noise, not lessons).
   - **High-value lessons** (high seen_count) that are NOT yet promoted to a skill and
     should be — or that need a clearer title/body before promotion.

4. Propose concrete edits. Only after the user agrees, apply them by editing
   `.claude/evolve/learnings.json` directly (preserve the schema: id, type, key, title,
   body, seen_count, first_seen, last_seen, state, promoted, skill).

5. To force-promote a validated lesson now, set its `seen_count` to at least the promote
   threshold and re-run consolidation:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/consolidate.py"
   ```

Keep the store lean. A few sharp, reusable lessons beat a long list of noise.
