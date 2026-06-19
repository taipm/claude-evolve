#!/usr/bin/env python3
"""status.py — human-readable summary of the learning store. Used by /evolve:status."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import store  # noqa: E402


def main() -> None:
    data = store.load_learnings()
    if not data:
        print("claude-evolve: no learnings yet for this project.")
        print(f"store: {store.store_dir()}")
        return
    by_state, by_type, promoted = {}, {}, []
    for r in data.values():
        by_state[r.get("state")] = by_state.get(r.get("state"), 0) + 1
        by_type[r.get("type")] = by_type.get(r.get("type"), 0) + 1
        if r.get("promoted"):
            promoted.append(r)
    print(f"claude-evolve store: {store.store_dir()}")
    print(f"  total learnings : {len(data)}")
    print(f"  by state        : {dict(by_state)}")
    print(f"  by type         : {dict(by_type)}")
    print(f"  promoted skills : {len(promoted)}")
    top = sorted([r for r in data.values() if r.get('state') == 'active'],
                 key=store.confidence, reverse=True)[:10]
    if top:
        print("\n  top active learnings:")
        for r in top:
            mark = " *skill*" if r.get("promoted") else ""
            print(f"    x{r.get('seen_count',1):<2} [{r['type']}]{mark} {r['title']}")
    if promoted:
        print("\n  generated skills (.claude/skills/):")
        for r in promoted:
            print(f"    - {r.get('skill')}")


if __name__ == "__main__":
    main()
