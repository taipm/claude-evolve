# Changelog

## 0.1.0 — 2026-06-19

### Resurfacing reliability
- **Trigger-oriented skill descriptions**: promoted skills now describe WHEN to use them
  ("Use when `cargo` fails with E0382…") instead of restating the observation, so Claude
  Code actually invokes them when the task matches.
- **CLAUDE.md channel**: `scripts/export_md.py` regenerates `.claude/evolve/LEARNINGS.md`
  every turn; add `@.claude/evolve/LEARNINGS.md` to your project CLAUDE.md for the
  highest-reliability resurfacing (read on every turn, top priority).

### Hardening (pre-release, adversarial review + eval/AB harness)
- **Concurrency**: file-lock (`fcntl`) around all `learnings.json` mutations; signals
  claimed by atomic rename (`take_signals`) so racing hooks never lose a signal.
- **Timezone**: age math fixed to parse UTC (`calendar.timegm`) — curator/confidence were
  wrong by the local offset (broke on every non-UTC machine).
- **Noise filter**: env-noise guard now applies ONLY to raw build-error text at capture —
  no longer silently drops corrections/fixes that mention "api key", "rate limit", etc.
- **Dedup**: error-code matcher anchored to known prefixes (no false codes like `GMT2026`);
  `normalize` keeps quoted identifiers so `'Foo'` vs `'Bar'` errors stay distinct.
- **Slugs**: unicode-only titles (e.g. Vietnamese) get hash-suffixed unique skill dirs
  instead of all collapsing to one `evolve-/` dir.
- **Injection safety**: injected context + SKILL.md bodies sanitized and framed as
  untrusted reference data (supply-chain hardening for shared stores).
- **Robustness**: build-error field probing across versions, unique tmp on save,
  signal-size guard, `EVOLVE_DEBUG` log, accurate injection char cap.
- Added `tests/eval.py` (17/17) and `tests/ab.py` (parameter A/B study).

### Initial

Initial release. Self-improving skill loop for Claude Code, ported from the Hermes Agent
learning loop.

- **Capture** hooks: corrections (UserPromptSubmit), build/test failures
  (PostToolUseFailure), fixes (PostToolUse success-after-failure pairing).
- **Consolidate** (Stop): signals → learnings with patch-not-append dedup by normalized
  key, environment/transient noise guardrails.
- **Promote**: lessons seen ≥ `EVOLVE_PROMOTE_AT` become auto-loading `.claude/skills/`
  SKILL.md files.
- **Inject** (SessionStart): real learning content (ranked by frequency × recency) added
  to context — closing the loop that count-only systems leave open.
- **Curate**: ACTIVE → STALE (60d) → ARCHIVED (120d) state machine.
- Commands: `/claude-evolve:status`, `:review`, `:init`. Agent: `learning-reviewer`.
- Zero pip dependencies; model-agnostic core with optional `claude -p` polish.
- Installable via Claude Code marketplace (Gitea + GitHub mirror) or `install.sh`.
