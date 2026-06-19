#!/usr/bin/env python3
"""store.py — shared store + telemetry for claude-evolve.

Closes the learning loop that flat-text systems leave open:
  capture -> consolidate (PATCH, not append) -> promote to SKILL.md -> INJECT -> curate

Pure stdlib. No pip deps. No hardcoded model. Per-project store under .claude/evolve/.

Concurrency: hooks fire per tool call and can overlap, and the store is meant to be
committed/shared. All mutations of learnings.json + the signal handoff run under an
advisory file lock (fcntl on POSIX; best-effort no-op elsewhere). Signals are taken by
atomic rename (take_signals) so a late append is never lost to a racing consolidate.
"""
import calendar
import hashlib
import json
import os
import re
import time
from contextlib import contextmanager
from pathlib import Path

try:
    import fcntl  # POSIX
except Exception:  # Windows / unusual platforms
    fcntl = None

# ---- locations -------------------------------------------------------------

def project_root() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())

def store_dir() -> Path:
    return project_root() / ".claude" / "evolve"

def _path(name: str) -> Path:
    return store_dir() / name

LEARNINGS = "learnings.json"
SIGNALS = "signals.jsonl"
FAILMARK = ".last-failure"
LOCKFILE = ".lock"

# lifecycle thresholds (days) — mirrors Hermes curator
STALE_AFTER = float(os.environ.get("EVOLVE_STALE_DAYS", "60"))
ARCHIVE_AFTER = float(os.environ.get("EVOLVE_ARCHIVE_DAYS", "120"))
PROMOTE_AT = int(os.environ.get("EVOLVE_PROMOTE_AT", "2"))   # seen_count to become a SKILL
MAX_SIGNALS = int(os.environ.get("EVOLVE_MAX_SIGNALS", "5000"))  # guard runaway files

# ---- io & locking ----------------------------------------------------------

def ensure_store() -> Path:
    d = store_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d

@contextmanager
def locked():
    """Advisory exclusive lock across processes. Best-effort if fcntl is unavailable."""
    ensure_store()
    lf = _path(LOCKFILE)
    fh = open(lf, "w")
    try:
        if fcntl is not None:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            if fcntl is not None:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()

def debug(msg: str) -> None:
    """Opt-in diagnostics (EVOLVE_DEBUG=1) — hooks swallow errors to never break a turn,
    so this is the only window into a silently-failing capture."""
    if os.environ.get("EVOLVE_DEBUG") != "1":
        return
    try:
        ensure_store()
        with open(_path("debug.log"), "a") as f:
            f.write(f"{iso(now())} {msg}\n")
    except Exception:
        pass

def now() -> float:
    return time.time()

def iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))

def load_learnings() -> dict:
    p = _path(LEARNINGS)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}

def save_learnings(data: dict) -> None:
    ensure_store()
    p = _path(LEARNINGS)
    tmp = p.with_suffix(f".json.{os.getpid()}.tmp")   # unique per writer
    try:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        os.replace(tmp, p)   # atomic
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except Exception:
                pass

def append_signal(sig: dict) -> None:
    ensure_store()
    line = json.dumps(sig, ensure_ascii=False) + "\n"
    with locked():
        # cap runaway growth (pathological build loops)
        p = _path(SIGNALS)
        if p.exists() and p.stat().st_size > MAX_SIGNALS * 4096:
            return
        with open(p, "a") as f:
            f.write(line)

def take_signals() -> list:
    """Atomically claim the current signals for processing (rename-then-read), so a
    concurrent append lands in a fresh file and is never lost. Returns parsed list."""
    with locked():
        p = _path(SIGNALS)
        if not p.exists():
            return []
        claim = _path(f"{SIGNALS}.{os.getpid()}.{int(now())}.proc")
        try:
            p.rename(claim)
        except Exception:
            return []
    out = []
    for line in claim.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    try:
        claim.unlink()
    except Exception:
        pass
    return out

# ---- sanitization ----------------------------------------------------------

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

def sanitize(text: str) -> str:
    """Neutralize untrusted text before it enters SKILL.md / injected context.
    Strips control chars and defuses markdown/code-fence/heading break-outs so a
    poisoned build error or shared store cannot inject structure or instructions."""
    if not text:
        return ""
    t = _CTRL.sub(" ", text)
    t = t.replace("```", "ʼʼʼ")          # no code-fence break-out
    t = re.sub(r"(?m)^\s*#", "·#", t)      # no heading break-out
    t = re.sub(r"(?m)^\s*---\s*$", "—", t)  # no frontmatter break-out
    return t

# ---- normalization & guardrails -------------------------------------------

def normalize(text: str) -> str:
    """Strip volatile bits so structurally-identical errors collapse to one key.
    Keeps quoted identifiers (e.g. 'Foo' vs 'Bar') — those distinguish real errors."""
    t = (text or "").lower()
    t = re.sub(r"/[^\s:'\"]+", " ", t)         # file paths
    t = re.sub(r"line \d+|column \d+|:\d+", " ", t)   # positions
    t = re.sub(r"0x[0-9a-f]+", " ", t)          # hex addrs
    t = re.sub(r"\b\d+\b", " ", t)              # bare numbers
    t = t.replace("'", " ").replace('"', " ").replace("`", " ")  # keep inner words
    t = re.sub(r"\s+", " ", t).strip()
    return t[:400]

# Transient / environment-specific errors — capturing them creates false constraints.
# Applied ONLY to raw build-failure error text at capture time (capture.py), never to
# user corrections or fixes (those may legitimately mention these words).
_DENY = re.compile(
    r"command not found|no such file|enoent|eacces|"
    r"address already in use|connection refused|could not resolve host|"
    r"network is unreachable|temporarily unavailable|no space left|"
    r"broken pipe|segmentation fault",
    re.I,
)

def is_noise(text: str) -> bool:
    return bool(_DENY.search(text or ""))

# ---- learning upsert (PATCH not append) -----------------------------------

def _slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return s[:48] if s else ""

def stable_slug(prefix: str, *parts: str) -> str:
    """Non-empty, collision-resistant slug. Falls back to a hash of the parts so that
    unicode-only titles (e.g. Vietnamese corrections) don't all collapse to one dir."""
    body = _slug(parts[0] if parts else "")
    h = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:8]
    base = f"{prefix}-{body}" if body else f"{prefix}"
    return f"{base}-{h}"

def upsert(data: dict, typ: str, title: str, body: str, key=None) -> dict:
    """Bump an existing learning if its normalized key matches; else create."""
    key = key or normalize(title + " " + body)
    for rec in data.values():
        if rec.get("key") == key and rec.get("type") == typ:
            rec["seen_count"] = int(rec.get("seen_count", 1)) + 1
            rec["last_seen"] = iso(now())
            rec["state"] = "active"
            if body and len(body) > len(rec.get("body", "")):
                rec["body"] = body[:2000]
            return rec
    ts = iso(now())
    rid = stable_slug(typ, title, str(now()))
    rec = {
        "id": rid, "type": typ, "key": key,
        "title": title.strip()[:120], "body": body.strip()[:2000],
        "seen_count": 1, "first_seen": ts, "last_seen": ts,
        "state": "active", "promoted": False, "skill": None,
    }
    data[rid] = rec
    return rec

# ---- curator (state machine) ----------------------------------------------

def _age_days(iso_ts: str) -> float:
    try:
        # iso() emits UTC; parse as UTC (timegm), not local (mktime).
        t = calendar.timegm(time.strptime(iso_ts, "%Y-%m-%dT%H:%M:%SZ"))
        return max(0.0, (now() - t) / 86400.0)
    except Exception:
        return 0.0

def curate(data: dict) -> dict:
    """ACTIVE -> STALE -> ARCHIVED by inactivity. Deterministic, no LLM."""
    for rec in data.values():
        age = _age_days(rec.get("last_seen", iso(now())))
        if age >= ARCHIVE_AFTER:
            rec["state"] = "archived"
        elif age >= STALE_AFTER and rec.get("state") != "archived":
            rec["state"] = "stale"
    return data

def confidence(rec: dict) -> float:
    """Higher = more worth surfacing. Frequency dominates; recency scales it so a
    recent lesson outranks an equally-frequent stale one (README: frequency x recency)."""
    age = _age_days(rec.get("last_seen", iso(now())))
    recency = max(0.0, 1.0 - age / max(ARCHIVE_AFTER, 1))
    return int(rec.get("seen_count", 1)) * (1.0 + recency)
