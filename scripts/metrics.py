#!/usr/bin/env python3
"""metrics.py — quantify claude-evolve's learning, not just its mechanics.

Reads .claude/evolve/learnings.json and computes:
  - retention: how many distinct lessons are held, by type/state
  - promotion: share of lessons proven enough to become skills
  - freshness: active vs stale vs archived (is the knowledge current?)
  - recurrence: how often lessons repeat (the raw learning pressure)
  - effectiveness PROXY: for promoted lessons, did recurrence slow after promotion?
    A widening gap between recurrences suggests the injected lesson is helping.
    NOTE: this is a proxy, not proof — true causal effectiveness needs an on/off A/B.

Outputs a JSON blob (also used by dashboard.py). Usage:
  python3 metrics.py            # pretty JSON
  python3 metrics.py --raw      # compact JSON (for piping)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import store  # noqa: E402


def compute() -> dict:
    data = store.load_learnings()
    recs = list(data.values())
    n = len(recs)
    by_type, by_state = {}, {}
    seen_hist = {}
    for r in recs:
        by_type[r["type"]] = by_type.get(r["type"], 0) + 1
        by_state[r.get("state", "active")] = by_state.get(r.get("state", "active"), 0) + 1
        sc = int(r.get("seen_count", 1))
        bucket = "1" if sc == 1 else ("2" if sc == 2 else ("3-4" if sc <= 4 else "5+"))
        seen_hist[bucket] = seen_hist.get(bucket, 0) + 1

    promoted = [r for r in recs if r.get("promoted")]
    total_signals = sum(int(r.get("seen_count", 1)) for r in recs)
    active = by_state.get("active", 0)

    # effectiveness proxy: of promoted lessons, how many have gone quiet since promotion
    # (last_seen older than a "cooldown") vs still recurring. More quiet = lessons stuck.
    quiet = sum(1 for r in promoted if store._age_days(r.get("last_seen", "")) >= 14)
    recurring = len(promoted) - quiet

    top = sorted(recs, key=store.confidence, reverse=True)[:10]
    return {
        "totals": {
            "learnings": n,
            "signals_absorbed": total_signals,
            "distinct_to_signal_ratio": round(n / total_signals, 3) if total_signals else 0,
            "skills_promoted": len(promoted),
            "promotion_rate": round(len(promoted) / n, 3) if n else 0,
        },
        "by_type": by_type,
        "by_state": by_state,
        "seen_histogram": seen_hist,
        "freshness": {
            "active": active,
            "active_share": round(active / n, 3) if n else 0,
            "stale": by_state.get("stale", 0),
            "archived": by_state.get("archived", 0),
        },
        "effectiveness_proxy": {
            "promoted": len(promoted),
            "quiet_since_promotion": quiet,     # learned and not recurring -> likely helping
            "still_recurring": recurring,       # learned but still happening -> not yet helping
            "quiet_share": round(quiet / len(promoted), 3) if promoted else 0,
        },
        "top": [
            {"title": r["title"][:70], "type": r["type"], "seen": r.get("seen_count", 1),
             "state": r.get("state"), "promoted": bool(r.get("promoted"))}
            for r in top
        ],
    }


def main() -> None:
    m = compute()
    if "--raw" in sys.argv:
        print(json.dumps(m, ensure_ascii=False))
    else:
        print(json.dumps(m, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
