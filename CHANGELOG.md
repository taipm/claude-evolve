# Changelog

## 0.1.0 — 2026-06-19

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
