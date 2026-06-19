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
curl -fsSL https://raw.githubusercontent.com/taipm/claude-evolve/main/install.sh | bash
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
| `/claude-evolve:dashboard` | Metrics + a standalone visual HTML dashboard of learning quality |
| `/claude-evolve:review` | LLM-assisted cleanup — dedup, sharpen, force-promote |
| `/claude-evolve:init`   | Explain the loop / set up git tracking for the store |

Measure it directly too:

```bash
python3 scripts/metrics.py      # retention, promotion rate, dedup ratio, freshness, effectiveness proxy
python3 scripts/dashboard.py    # -> .claude/evolve/dashboard.html (open in a browser)
```

**Effectiveness is two layers.** The *mechanics* (capture / dedup / promote / inject / curate)
are verified by `tests/`. The *behavioral* effect — does injecting a lesson actually reduce its
recurrence? — is surfaced as a **proxy** (`effectiveness_proxy`): a promoted lesson that goes
quiet *suggests* it's helping. Proving causation needs an on/off A/B over real usage.

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
| `EVOLVE_MAX_SIGNALS` | `5000` | Guard against runaway `signals.jsonl` growth |
| `EVOLVE_LLM` | unset | Set `1` to polish lessons with `claude -p` (opt-in; serializes consolidation) |
| `EVOLVE_DEBUG` | unset | Set `1` to log silent hook errors to `.claude/evolve/debug.log` |

Defaults are evidence-backed — see **Quality** below.

---

## Security & trust

The store under `.claude/evolve/` is meant to be committable and shared, which makes it
**trusted input**: cloning a repo with a poisoned `learnings.json` would surface its content
to your session. Mitigations built in:

- Injected context and generated `SKILL.md` bodies are **sanitized** — control characters
  stripped, code-fence / heading / frontmatter break-outs defused — and explicitly framed
  as *reference data, not instructions*.
- Still: **review a third party's committed store before trusting it**, the same way you'd
  review their code.
- The optional `EVOLVE_LLM` polish sends lesson text to `claude -p`; keep it off if your
  build output may contain untrusted/adversarial text.

---

## Quality

Concurrency-safe (POSIX `fcntl` advisory lock around every store mutation; signals are
claimed by atomic rename so a racing hook never loses one). Timestamps are UTC end-to-end.
Two harnesses ship in `tests/`:

```bash
python3 tests/eval.py   # 17/17 — precision/recall, dedup, unicode slugs, injection, latency, TZ
python3 tests/ab.py     # A/B study backing the default tunables
```

Hook latency is ~35–45 ms per turn. On non-POSIX platforms (Windows) locking degrades to
best-effort; everything else is portable Python 3.8+ stdlib.

---

## How it compares to Hermes

`claude-evolve` ports Hermes' key mechanisms — per-turn background refine, patch-not-append,
usage telemetry + state machine, auto-promotion, and a curator — into Claude Code's hook
system. Hermes does its refine in a forked sub-agent; here consolidation is deterministic
Python (free, model-agnostic) with an optional LLM polish.

## License

MIT © taipm
