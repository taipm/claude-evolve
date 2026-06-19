# claude-evolve

**A self-improving skill loop for Claude Code.** It watches your sessions, learns from
corrections and build failures, refines those lessons in place, auto-promotes the recurring
ones into skills that Claude loads automatically, and feeds prior-session learnings back
into every new session.

Ported from the [Hermes Agent](https://github.com/nousresearch/hermes-agent) learning loop —
rebuilt as a zero-dependency Claude Code plugin anyone can install.

---

## Why

Most "learning" setups capture mistakes into flat `.md` files and then, next session, only
tell Claude *"5 mistakes accumulated"* — a **count**, not the content. The loop never closes:
Claude can't apply what it can't see.

`claude-evolve` closes it:

```
capture → consolidate (PATCH, not append) → promote to SKILL.md → INJECT content → curate
```

| Stage | What happens |
|-------|--------------|
| **Capture** | Hooks record corrections (you push back), build/test failures, and fixes (a success right after a failure). Environment/transient noise is dropped. |
| **Consolidate** | On every turn-end, signals become learnings. A recurring signal **bumps one record's `seen_count`** instead of piling up new lines. |
| **Promote** | A lesson seen ≥ N times (default 2) is written as a real `.claude/skills/evolve-*/SKILL.md` — which Claude Code **auto-loads** next session. |
| **Inject** | On session start, the actual **content** of your top learnings (ranked by recency × frequency) is injected into context — not just a count. |
| **Curate** | Lessons not re-seen for 60d go stale, 120d archived — so injection stays sharp. |

No model lock-in: the core is pure Python and runs with **whatever model you use**. An
optional LLM polish step shells out to `claude -p` only if you opt in.

---

## Install

### Option A — Claude Code marketplace (recommended)

```bash
# add the marketplace, then install
claude plugin marketplace add https://git.microai.club/taipm/claude-evolve
claude plugin install claude-evolve@claude-evolve
```

GitHub mirror works the same:

```bash
claude plugin marketplace add https://github.com/taipm/claude-evolve
claude plugin install claude-evolve@claude-evolve
```

### Option B — one-line installer

```bash
curl -fsSL https://git.microai.club/taipm/claude-evolve/raw/branch/main/install.sh | bash
```

Restart Claude Code (or run `/reload-skills`). That's it — nothing to configure.

**Requirements:** `python3` (3.8+, stdlib only). `PostToolUseFailure` build-failure capture
needs a recent Claude Code; corrections, fixes, promotion and injection work everywhere.

---

## Use

Nothing to do — it runs in the background. Optional commands:

| Command | What |
|---------|------|
| `/claude-evolve:status` | Show the learning store: counts, top lessons, promoted skills |
| `/claude-evolve:review` | LLM-assisted cleanup — dedup, sharpen, force-promote |
| `/claude-evolve:init`   | Explain the loop / set up git tracking for the store |

Agent `learning-reviewer` cross-checks a diff/plan against past mistakes before you ship.

---

## Where it stores things

Per-project, under your repo:

```
.claude/evolve/learnings.json   # the knowledge base (telemetry + lessons)
.claude/evolve/signals.jsonl    # raw signals, cleared after consolidation
.claude/skills/evolve-*/        # auto-generated, auto-loaded skills
```

Commit `.claude/evolve/` to share learnings with your team, or gitignore it to keep them local.

---

## Configuration (env vars, all optional)

| Var | Default | Meaning |
|-----|---------|---------|
| `EVOLVE_PROMOTE_AT` | `2` | Times a lesson must recur before becoming a skill |
| `EVOLVE_STALE_DAYS` | `60` | Inactivity before a lesson goes stale |
| `EVOLVE_ARCHIVE_DAYS` | `120` | Inactivity before a lesson is archived |
| `EVOLVE_INJECT_MAX` | `12` | Max learnings injected per session |
| `EVOLVE_INJECT_CHARS` | `2400` | Max chars injected per session |
| `EVOLVE_LLM` | unset | Set `1` to polish lessons with `claude -p` |

---

## How it compares to Hermes

`claude-evolve` ports Hermes' key mechanisms — per-turn background refine, patch-not-append,
usage telemetry + state machine, auto-promotion, and a curator — into Claude Code's hook
system. Hermes does its refine in a forked sub-agent; here consolidation is deterministic
Python (free, model-agnostic) with an optional LLM polish.

## License

MIT © taipm
