#!/usr/bin/env python3
"""inject.py — SessionStart hook. THE fix for the broken loop.

Flat-text learning systems only print a COUNT ("5 mistakes accumulated"), so the
next session never actually sees the knowledge. This injects the real content of the
top learnings into additionalContext, capped, ranked by confidence. Loop closed.

Also runs the curator pass so stale learnings drop out of injection over time.
Always exits 0.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import store  # noqa: E402

MAX_ITEMS = int(__import__("os").environ.get("EVOLVE_INJECT_MAX", "12"))
MAX_CHARS = int(__import__("os").environ.get("EVOLVE_INJECT_CHARS", "2400"))


def main() -> None:
    data = store.load_learnings()
    if not data:
        sys.exit(0)
    store.curate(data)
    store.save_learnings(data)

    active = [r for r in data.values() if r.get("state") == "active"]
    if not active:
        sys.exit(0)
    active.sort(key=store.confidence, reverse=True)

    lines, used = [], 0
    for r in active[:MAX_ITEMS]:
        tag = r["type"].upper()
        seen = r.get("seen_count", 1)
        promoted = " (skill)" if r.get("promoted") else ""
        item = f"- [{tag} x{seen}{promoted}] {r['title']}"
        body = r.get("body", "").strip().replace("\n", " ")
        if body and len(body) < 200:
            item += f" — {body}"
        if used + len(item) > MAX_CHARS:
            break
        lines.append(item)
        used += len(item)

    if not lines:
        sys.exit(0)

    ctx = (
        "[evolve] Learnings from prior sessions in this project — apply them, "
        "do not repeat past mistakes:\n" + "\n".join(lines)
    )
    out = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": ctx,
        }
    }
    print(json.dumps(out))
    sys.exit(0)


if __name__ == "__main__":
    main()
