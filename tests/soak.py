#!/usr/bin/env python3
"""soak.py — realistic multi-session lifecycle for claude-evolve.

Drives the real hook scripts across several simulated sessions of a Rust/TS project:
recurring errors that should promote, one-offs that shouldn't, fixes, and noise that
should be dropped. Then fast-forwards time (by backdating timestamps) to exercise the
curator's stale/archive transitions, and prints the final status + what would be injected.

Run:  python3 tests/soak.py
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import store  # noqa: E402

PROJ = tempfile.mkdtemp(prefix="evolve-soak-")
ENV = dict(os.environ, CLAUDE_PROJECT_DIR=PROJ)


def hook(script, *args, payload=None):
    subprocess.run(["python3", str(SCRIPTS / script), *args],
                   input=json.dumps(payload or {}), text=True,
                   capture_output=True, env=ENV)


def correction(text):
    hook("capture.py", "correction", payload={"prompt": text})


def fail(cmd, err):
    hook("capture.py", "failure", payload={"tool_input": {"command": cmd}, "error": err})


def ok(cmd):
    hook("capture.py", "success", payload={"tool_input": {"command": cmd}})


def end_turn():
    hook("consolidate.py")


def store_path():
    return Path(PROJ) / ".claude" / "evolve" / "learnings.json"


def load():
    return json.loads(store_path().read_text()) if store_path().exists() else {}


def inject_ctx():
    p = subprocess.run(["python3", str(SCRIPTS / "inject.py")], input="{}",
                       text=True, capture_output=True, env=ENV)
    if not p.stdout.strip():
        return ""
    return json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]


def backdate(pred, days):
    """Simulate the passage of time: rewind last_seen for matching learnings."""
    data = load()
    ts = store.iso(time.time() - days * 86400)
    for r in data.values():
        if pred(r):
            r["last_seen"] = ts
    store_path().write_text(json.dumps(data, indent=2, ensure_ascii=False))


def banner(t):
    print(f"\n{'─'*60}\n{t}\n{'─'*60}")


# ---------------------------------------------------------------------------

banner("SESSION 1 — first encounters (nothing promotes yet)")
correction("that's wrong, don't use .unwrap() in library code")
fail("cargo build", "error[E0382]: borrow of moved value: cfg")
ok("cargo build")                                   # fix pairing
fail("npm run build", "error TS2345: Argument of type string not assignable")
fail("make", "make: *** [all] segmentation fault")  # noise -> dropped
end_turn()
print("after S1:", {r['type']: r['seen_count'] for r in load().values()})

banner("SESSION 2 — same mistakes recur (should start promoting)")
correction("that's wrong, stop using .unwrap() here")
fail("cargo build", "error[E0382]: borrow of moved value: handle")
fail("npm run build", "error TS2345: Argument of type number not assignable")
fail("docker compose up", "connection refused")     # noise -> dropped
end_turn()

banner("SESSION 3 — one more recurrence + a fresh one-off")
fail("cargo build", "error[E0382]: borrow of moved value: ctx")
correction("no, that broke the migration, revert it")   # one-off
end_turn()

data = load()
print("\nLearnings after 3 sessions:")
for r in sorted(data.values(), key=lambda x: -x["seen_count"]):
    flag = " -> SKILL" if r["promoted"] else ""
    print(f"  x{r['seen_count']} [{r['type']:<14}] {r['title'][:50]}{flag}")

skills_dir = Path(PROJ) / ".claude" / "skills"
sk = sorted(p.parent.name for p in skills_dir.rglob("SKILL.md")) if skills_dir.exists() else []
print(f"\nAuto-promoted skills ({len(sk)}):")
for s in sk:
    print("  -", s)

banner("WHAT A NEW SESSION RECEIVES (injection)")
print(inject_ctx())

banner("TIME PASSES — curator (backdate to exercise stale/archive)")
# rewind the E0382 lesson 70 days (-> stale), the TS2345 lesson 130 days (-> archived)
backdate(lambda r: "E0382" in r.get("key", "") or "e0382" in r.get("title", "").lower(), 70)
backdate(lambda r: "TS2345" in r.get("key", "") or "ts2345" in r.get("title", "").lower(), 130)
inject_ctx()  # triggers curate()+save
data = load()
print("states after aging:")
for r in data.values():
    print(f"  [{r['state']:<8}] x{r['seen_count']} {r['title'][:48]}")

active = [r for r in data.values() if r["state"] == "active"]
print(f"\nInjection now surfaces only {len(active)} active lesson(s) "
      f"(stale/archived dropped):")
ctx = inject_ctx()
print(ctx if ctx else "  (none)")

banner("FINAL STATUS")
subprocess.run(["python3", str(SCRIPTS / "status.py")], env=ENV)

print(f"\nsoak project: {PROJ}")
