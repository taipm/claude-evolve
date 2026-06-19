#!/usr/bin/env python3
"""effectiveness.py — A/B harness measuring the LEVERAGE of the claude-evolve loop.

WHAT THIS MEASURES
------------------
This script quantifies how much the learning loop's promotion timing and
deduplication reduce the repeat-rate of known errors, UNDER AN ASSUMED
avoidance probability p_avoid.

It does NOT prove that Claude actually avoids learned errors at p_avoid.
That claim requires real-usage logs where the injected lesson was present
and the error's subsequent occurrence rate is measured against a control
group that did not receive the lesson.  This harness models the plugin's
structural contribution — promotion timing, dedup, key collapsing — given
a hypothetical avoidance effect.

METHODOLOGY
-----------
1. A deterministic synthetic error stream of ~8 distinct error codes is
   built from a fixed recipe.  Repetition counts per error are baked in;
   no randomness.

2. Two arms, each in their own fresh CLAUDE_PROJECT_DIR:
   - OFF arm: every event is emitted (capture.py failure + consolidate.py).
     Repeats = occurrences AFTER the first occurrence of each error.
   - ON arm: same stream, but before emitting each event the current
     learnings store is checked.  If that error's lesson is PROMOTED
     (rec["promoted"] == True), the event is suppressed with probability
     p_avoid — modelling Claude avoiding the now-learned mistake.
     Suppression is deterministic: suppress when
         (event_index * 9973) % 100 < int(p_avoid * 100)
     The multiplier 9973 is a prime chosen to spread index-based hashes
     across the [0,100) range without clustering; it produces a fixed,
     reproducible suppression pattern for every (event_index, p_avoid)
     pair so the output is identical across repeated runs.

3. Metric: repeats_after_first, total_emitted, avoided (ON only).
   Effectiveness = (OFF_repeats - ON_repeats) / OFF_repeats * 100 %

4. Sensitivity sweep: run ON arm for p_avoid in [0.3, 0.6, 0.9].

CAVEAT (also printed at runtime): These numbers assume a fixed p_avoid;
the real avoidance probability is unknown without production A/B data.

Run:  python3 tests/effectiveness.py
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths — always absolute
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

# Import store from the scripts directory so we can call load_learnings()
sys.path.insert(0, str(SCRIPTS))
import store  # noqa: E402

# ---------------------------------------------------------------------------
# Synthetic error stream definition (deterministic — no random, no wall-clock)
# ---------------------------------------------------------------------------
# Each entry: (error_code, recurrences_total)
# recurrences_total is the TOTAL number of times the error appears in the
# stream (first occurrence + repeats).  Errors with count > 1 will
# contribute to the repeat metric.
#
# Error codes are chosen to match the _ERRCODE patterns in consolidate.py
# so they are deduped by code (key = "build:<code>"), which is realistic
# and exercises the most important dedup path.

ERROR_SPEC = [
    ("E0382", 5),   # borrow of moved value — very common in Rust learning curve
    ("E0499", 4),   # cannot borrow as mutable more than once
    ("E0597", 3),   # borrow may outlive current function
    ("TS2345", 4),  # TypeScript argument-type mismatch
    ("TS2339", 2),  # property does not exist
    ("CS0246", 3),  # C# type not found
    ("CS0103", 2),  # C# name does not exist in context
    ("E0277", 1),   # trait bound not satisfied (one-off — should not promote)
]

# Map from error code to the full error text template.  The variation string
# keeps each occurrence slightly different (realistic) without relying on RNG;
# it is derived from the event index via a simple modular sequence.
_VARIANTS = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta"]

def _error_text(code: str, variant: str) -> str:
    """Produce a realistic build error string for the given code."""
    templates = {
        "E0382": f"error[E0382]: borrow of moved value: {variant}",
        "E0499": f"error[E0499]: cannot borrow `{variant}` as mutable more than once at a time",
        "E0597": f"error[E0597]: `{variant}` does not live long enough",
        "TS2345": f"error TS2345: Argument of type '{variant}' is not assignable to parameter",
        "TS2339": f"error TS2339: Property '{variant}' does not exist on type 'Response'",
        "CS0246": f"error CS0246: The type or namespace name '{variant}' could not be found",
        "CS0103": f"error CS0103: The name '{variant}' does not exist in the current context",
        "E0277": f"error[E0277]: the trait bound `{variant}: Display` is not satisfied",
    }
    return templates.get(code, f"error[{code}]: {variant}")

def _build_command(code: str) -> str:
    if code.startswith("TS"):
        return "npm run build"
    if code.startswith("CS"):
        return "dotnet build"
    return "cargo build"

def build_event_stream() -> list:
    """Return a list of (event_index, error_code, error_text, command) tuples.

    Events are interleaved by code to mirror real sessions where different
    errors appear in different turns.  The order is deterministic: we
    round-robin through the codes, emitting one occurrence per pass until
    all recurrence counts are exhausted.
    """
    # Build per-code remaining lists
    remaining = {code: count for code, count in ERROR_SPEC}
    occurrence_num = {code: 0 for code, _ in ERROR_SPEC}
    codes = [code for code, _ in ERROR_SPEC]

    events = []
    event_index = 0
    active = True
    while active:
        active = False
        for code in codes:
            if remaining[code] > 0:
                active = True
                n = occurrence_num[code]
                variant = _VARIANTS[n % len(_VARIANTS)]
                events.append((event_index, code, _error_text(code, variant), _build_command(code)))
                remaining[code] -= 1
                occurrence_num[code] += 1
                event_index += 1
    return events

EVENT_STREAM = build_event_stream()

# ---------------------------------------------------------------------------
# Subprocess helpers (same pattern as eval.py and soak.py)
# ---------------------------------------------------------------------------

def run_script(script: str, *args, payload=None, proj_dir=None):
    env = dict(os.environ)
    if proj_dir:
        env["CLAUDE_PROJECT_DIR"] = proj_dir
    subprocess.run(
        ["python3", str(SCRIPTS / script), *args],
        input=json.dumps(payload or {}),
        text=True,
        capture_output=True,
        env=env,
    )

def fresh_project() -> tuple:
    """Return (proj_dir_path_str, env_dict) for a throwaway project."""
    d = tempfile.mkdtemp(prefix="evolve-effectiveness-")
    return d, {"CLAUDE_PROJECT_DIR": d}

def load_learnings_for(proj_dir: str) -> dict:
    """Read the learnings store from a project directory (no env mutation needed
    because we call store functions directly with os.environ patched momentarily)."""
    p = Path(proj_dir) / ".claude" / "evolve" / "learnings.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}

def get_promoted_codes(proj_dir: str) -> set:
    """Return the set of error codes whose learning is currently promoted."""
    data = load_learnings_for(proj_dir)
    promoted = set()
    for rec in data.values():
        if rec.get("promoted"):
            key = rec.get("key", "")
            # key is "build:E0382" or "fix:E0382" etc.
            if ":" in key:
                code_part = key.split(":", 1)[1]
                # Normalised keys may or may not still contain the raw code;
                # also scan the title as a fallback.
                promoted.add(code_part.upper())
            # Also extract from title (e.g. "Build error: error[E0382]: …")
            title = rec.get("title", "")
            m = re.search(
                r"error\[([A-Za-z]+\d+)\]|\b(TS\d{3,5})\b|\b(CS\d{3,5})\b|\b(C\d{4})\b|\b(E\d{3,4})\b",
                title,
            )
            if m:
                code = next(g for g in m.groups() if g)
                promoted.add(code.upper())
    return promoted

# ---------------------------------------------------------------------------
# Suppress decision — deterministic, no RNG
# ---------------------------------------------------------------------------

def should_suppress(event_index: int, p_avoid: float) -> bool:
    """Return True iff this event should be suppressed (Claude avoids the error).

    Determinism: (event_index * 9973) % 100 < int(p_avoid * 100)
    9973 is prime; the product spreads indices across [0,100) without
    clustering, giving a stable, reproducible suppression pattern that is
    independent of wall-clock time and does not use random().
    """
    return (event_index * 9973) % 100 < int(p_avoid * 100)

# ---------------------------------------------------------------------------
# OFF arm
# ---------------------------------------------------------------------------

def run_off_arm() -> dict:
    """Feed every event through capture+consolidate; count repeats.

    Returns:
        {
          "proj_dir": str,
          "total_emitted": int,
          "first_seen": {code: first_event_index},
          "repeats": int,   # events after first occurrence of that code
          "per_code": {code: {"total": int, "repeats": int}},
        }
    """
    proj_dir, _env = fresh_project()

    first_seen: dict = {}       # code -> event_index of first occurrence
    per_code: dict = {}
    total_emitted = 0
    total_repeats = 0

    for event_index, code, error_text, command in EVENT_STREAM:
        # Emit
        run_script(
            "capture.py", "failure",
            payload={"tool_input": {"command": command}, "error": error_text},
            proj_dir=proj_dir,
        )
        run_script("consolidate.py", proj_dir=proj_dir)

        total_emitted += 1
        if code not in per_code:
            per_code[code] = {"total": 0, "repeats": 0}
        per_code[code]["total"] += 1

        if code not in first_seen:
            first_seen[code] = event_index
        else:
            # This is a repeat
            per_code[code]["repeats"] += 1
            total_repeats += 1

    return {
        "proj_dir": proj_dir,
        "total_emitted": total_emitted,
        "first_seen": first_seen,
        "repeats": total_repeats,
        "per_code": per_code,
    }

# ---------------------------------------------------------------------------
# ON arm
# ---------------------------------------------------------------------------

def run_on_arm(p_avoid: float) -> dict:
    """Same stream as OFF, but suppresses events whose lesson is promoted.

    Returns:
        {
          "proj_dir": str,
          "total_emitted": int,
          "avoided": int,
          "repeats": int,
          "per_code": {code: {"total": int, "repeats": int, "avoided": int}},
        }
    """
    proj_dir, _env = fresh_project()

    first_seen: dict = {}
    per_code: dict = {}
    total_emitted = 0
    total_repeats = 0
    total_avoided = 0

    for event_index, code, error_text, command in EVENT_STREAM:
        # Check whether this error's lesson is already promoted in the store
        promoted_codes = get_promoted_codes(proj_dir)
        is_promoted = code.upper() in promoted_codes

        # Suppression: only possible if promoted and deterministic hash says yes
        if is_promoted and should_suppress(event_index, p_avoid):
            # Claude avoids the mistake — do NOT emit the event
            if code not in per_code:
                per_code[code] = {"total": 0, "repeats": 0, "avoided": 0}
            per_code[code]["avoided"] = per_code[code].get("avoided", 0) + 1
            total_avoided += 1
            continue

        # Emit the event
        run_script(
            "capture.py", "failure",
            payload={"tool_input": {"command": command}, "error": error_text},
            proj_dir=proj_dir,
        )
        run_script("consolidate.py", proj_dir=proj_dir)

        total_emitted += 1
        if code not in per_code:
            per_code[code] = {"total": 0, "repeats": 0, "avoided": 0}
        per_code[code]["total"] += 1

        if code not in first_seen:
            first_seen[code] = event_index
        else:
            per_code[code]["repeats"] += 1
            total_repeats += 1

    return {
        "proj_dir": proj_dir,
        "total_emitted": total_emitted,
        "avoided": total_avoided,
        "repeats": total_repeats,
        "per_code": per_code,
    }

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def print_separator(char="=", width=70):
    print(char * width)

def main():
    print_separator()
    print("claude-evolve :: Effectiveness / Leverage Harness")
    print_separator()
    print()
    print("CAVEAT: This harness measures the structural LEVERAGE of the")
    print("  learning loop (promotion timing + dedup) under an assumed")
    print("  avoidance probability p_avoid.  It does NOT prove that Claude")
    print("  avoids learned errors at p_avoid in real usage; that requires")
    print("  production A/B logs with and without lesson injection.")
    print()

    # --- Build event stream summary ----------------------------------------
    total_events = len(EVENT_STREAM)
    total_spec_repeats = sum(max(0, count - 1) for _, count in ERROR_SPEC)
    print(f"Synthetic stream: {total_events} events, {len(ERROR_SPEC)} distinct error codes")
    print(f"  Expected OFF repeats (first-occurrence model): {total_spec_repeats}")
    print()

    # --- OFF arm -----------------------------------------------------------
    print_separator("-")
    print("Running OFF arm (no suppression)...")
    off = run_off_arm()
    print(f"  total emitted : {off['total_emitted']}")
    print(f"  repeats       : {off['repeats']}")
    off_proj = off["proj_dir"]

    # Show per-code breakdown
    print()
    print("  Per-code breakdown (OFF):")
    print(f"  {'Code':<10} {'Total':>6} {'Repeats':>8} {'Promoted?':>10}")
    print(f"  {'-'*10} {'-'*6} {'-'*8} {'-'*10}")
    off_promoted = get_promoted_codes(off_proj)
    for code, spec_count in ERROR_SPEC:
        info = off.get("per_code", {}).get(code, {"total": 0, "repeats": 0})
        promoted_mark = "YES" if code in off_promoted else "no"
        print(f"  {code:<10} {info['total']:>6} {info['repeats']:>8} {promoted_mark:>10}")

    print()

    # --- ON arm sensitivity sweep ------------------------------------------
    print_separator("-")
    print("Running ON arm sensitivity sweep (p_avoid in [0.3, 0.6, 0.9])...")
    print()

    sweep_results = []
    for p_avoid in [0.3, 0.6, 0.9]:
        on = run_on_arm(p_avoid)
        if off["repeats"] > 0:
            reduction = (off["repeats"] - on["repeats"]) / off["repeats"]
        else:
            reduction = 0.0
        sweep_results.append({
            "p_avoid": p_avoid,
            "on_repeats": on["repeats"],
            "avoided": on["avoided"],
            "total_emitted": on["total_emitted"],
            "reduction": reduction,
            "proj_dir": on["proj_dir"],
        })
        print(f"  p_avoid={p_avoid:.1f}: emitted={on['total_emitted']:3d}, "
              f"repeats={on['repeats']:3d}, avoided={on['avoided']:3d}, "
              f"repeat-rate reduction={reduction*100:.1f}%")

    print()

    # --- Summary table -------------------------------------------------------
    print_separator("=")
    print("RESULTS TABLE")
    print_separator("=")
    print()
    print(f"  OFF arm:")
    print(f"    total emitted : {off['total_emitted']}")
    print(f"    repeats       : {off['repeats']}")
    repeat_rate_off = off["repeats"] / max(off["total_emitted"], 1)
    print(f"    repeat rate   : {repeat_rate_off*100:.1f}%")
    print()
    print(f"  {'p_avoid':>8} | {'ON repeats':>10} | {'avoided':>8} | {'repeat rate':>12} | {'reduction vs OFF':>16}")
    print(f"  {'-'*8}-+-{'-'*10}-+-{'-'*8}-+-{'-'*12}-+-{'-'*16}")
    for r in sweep_results:
        on_rate = r["on_repeats"] / max(r["total_emitted"] + r["avoided"], 1)
        print(f"  {r['p_avoid']:>8.1f} | {r['on_repeats']:>10d} | {r['avoided']:>8d} | "
              f"{on_rate*100:>11.1f}% | {r['reduction']*100:>15.1f}%")
    print()

    # --- Sanity checks -------------------------------------------------------
    print_separator("-")
    print("Sanity checks:")
    ok_count = 0
    fail_count = 0

    def check(desc, condition):
        nonlocal ok_count, fail_count
        status = "PASS" if condition else "FAIL"
        print(f"  [{status}] {desc}")
        if condition:
            ok_count += 1
        else:
            fail_count += 1

    # OFF repeats should match specification
    check(
        f"OFF repeats ({off['repeats']}) match spec ({total_spec_repeats})",
        off["repeats"] == total_spec_repeats,
    )

    # ON should always have fewer or equal repeats than OFF (for all p_avoid)
    for r in sweep_results:
        check(
            f"ON (p={r['p_avoid']:.1f}) repeats <= OFF repeats",
            r["on_repeats"] <= off["repeats"],
        )

    # Reduction should be monotonically increasing with p_avoid
    reductions = [r["reduction"] for r in sweep_results]
    check(
        f"Repeat-rate reduction increases with p_avoid ({[f'{x*100:.1f}%' for x in reductions]})",
        reductions[0] <= reductions[1] <= reductions[2],
    )

    # Avoided count should be > 0 for all p_avoid (since some errors DO promote)
    for r in sweep_results:
        check(
            f"ON (p={r['p_avoid']:.1f}) avoided > 0",
            r["avoided"] > 0,
        )

    # E0277 (one-off, count=1) should never promote in OFF arm
    check(
        "E0277 (one-off) not promoted in OFF arm",
        "E0277" not in off_promoted,
    )

    # High-frequency errors (E0382, count=5) should promote in OFF arm
    check(
        "E0382 (5x) promoted in OFF arm",
        "E0382" in off_promoted,
    )

    print()
    print_separator("=")
    print(f"Sanity: {ok_count}/{ok_count+fail_count} checks passed")
    print_separator("=")
    print()

    # --- Cleanup ------------------------------------------------------------
    dirs_to_clean = [off_proj] + [r["proj_dir"] for r in sweep_results]
    cleaned = 0
    for d in dirs_to_clean:
        try:
            shutil.rmtree(d)
            cleaned += 1
        except Exception as exc:
            print(f"  Warning: could not remove {d}: {exc}")
    print(f"Cleaned up {cleaned} temp directories.")
    print()
    print("CAVEAT (repeat): p_avoid is ASSUMED, not measured.  Real leverage")
    print("  requires comparing error-recurrence rates in production sessions")
    print("  where the evolve lesson was injected vs sessions where it was not.")
    print()

    sys.exit(0)


if __name__ == "__main__":
    main()
