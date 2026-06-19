#!/usr/bin/env python3
"""capture.py — unified signal capture hook for claude-evolve.

One script, three modes (chosen by argv[1]) so hooks stay simple:
  correction   <- UserPromptSubmit   (user pushes back -> learn the mistake)
  failure      <- PostToolUseFailure  (Bash build/test fails -> learn the error)
  success      <- PostToolUse Bash    (success soon after a failure -> learn the fix)

Reads the hook JSON payload from stdin. Writes signals to .claude/evolve/signals.jsonl.
Never blocks the turn: any error exits 0 silently.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import store  # noqa: E402

BUILD_RE = re.compile(
    r"\b(cargo|npm|yarn|pnpm|make|pytest|go|rustc|gcc|g\+\+|clang|javac|tsc|"
    r"eslint|mypy|ruff|dotnet|mvn|gradle|cmake|deno|bun|jest|vitest)\b"
)
CORRECTION_RE = re.compile(
    r"that('?s| is| was)?\s*(wrong|incorrect|not right)|not? right|"
    r"don'?t do that|do not do that|undo|revert|not what i (asked|wanted)|"
    r"that broke|broke (it|the)|not like that|stop doing|why did you|"
    r"you (broke|messed|misunderstood)|wrong approach|"
    r"sai rồi|sai rồi|không phải|không đúng|không đúng|làm lại|"
    r"làm lại|sửa lại|sửa lại|bỏ cái|đừng làm|đừng",
    re.I,
)


def _stdin_json() -> dict:
    try:
        return json.loads(sys.stdin.read() or "{}")
    except Exception:
        return {}


def mode_correction(payload: dict) -> None:
    prompt = (payload.get("prompt") or "").strip()
    if not prompt or not CORRECTION_RE.search(prompt):
        return
    store.append_signal({
        "type": "correction", "ts": store.iso(store.now()),
        "text": prompt[:500],
    })
    # Surface a learning trigger into THIS turn (the one fix flat systems miss is the
    # next bit — see inject.py for cross-session surfacing).
    out = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": (
                "[evolve] User appears to be correcting you. After you fix it, the "
                "correction will be recorded as a learning. Avoid repeating it."
            ),
        }
    }
    print(json.dumps(out))


def mode_failure(payload: dict) -> None:
    ti = payload.get("tool_input") or {}
    cmd = (ti.get("command") or "").strip()
    if not cmd or not BUILD_RE.search(cmd):
        return
    # Field name for the error text isn't guaranteed stable across Claude Code versions;
    # probe the likely candidates so a build failure never lands with empty error text.
    err = ""
    for k in ("error", "tool_error", "tool_output", "stderr", "tool_response", "output"):
        v = payload.get(k)
        if isinstance(v, dict):
            v = v.get("stderr") or v.get("error") or v.get("content") or ""
        if v:
            err = str(v)
            break
    err = err[:2000]
    if store.is_noise(err) or store.is_noise(cmd):
        return  # environment-specific / transient -> not a learning
    store.append_signal({
        "type": "build_failure", "ts": store.iso(store.now()),
        "command": cmd[:300], "error": err,
    })
    # mark for fix-pairing
    store.ensure_store()
    (store.store_dir() / store.FAILMARK).write_text(json.dumps({
        "command": cmd[:300], "error": err[:500], "ts": store.now(),
    }))


def mode_success(payload: dict) -> None:
    mark = store.store_dir() / store.FAILMARK
    if not mark.exists():
        return
    try:
        prev = json.loads(mark.read_text())
    except Exception:
        mark.unlink(missing_ok=True)
        return
    # pair only if the fix came soon after the failure (<1h)
    if store.now() - float(prev.get("ts", 0)) > 3600:
        mark.unlink(missing_ok=True)
        return
    ti = payload.get("tool_input") or {}
    cmd = (ti.get("command") or "").strip()
    if not cmd or not BUILD_RE.search(cmd):
        return
    store.append_signal({
        "type": "fix_found", "ts": store.iso(store.now()),
        "failed_command": prev.get("command", ""),
        "error": prev.get("error", ""),
        "fix_command": cmd[:300],
    })
    mark.unlink(missing_ok=True)


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    payload = _stdin_json()
    try:
        if mode == "correction":
            mode_correction(payload)
        elif mode == "failure":
            mode_failure(payload)
        elif mode == "success":
            mode_success(payload)
    except Exception as e:
        store.debug(f"capture[{mode}] error: {e!r}")  # never break the turn
    sys.exit(0)


if __name__ == "__main__":
    main()
