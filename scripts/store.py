#!/usr/bin/env python3
"""store.py — shared store + telemetry for claude-evolve.

Closes the learning loop that flat-text systems leave open:
  capture -> consolidate (PATCH, not append) -> promote to SKILL.md -> INJECT -> curate

Pure stdlib. No pip deps. No hardcoded model. Per-project store under .claude/evolve/.

Data model (learnings.json): { "<id>": Learning, ... }
  Learning = {
    id, type, key, title, body,
    seen_count, first_seen, last_seen,
    state: active|stale|archived,
    promoted: bool, skill: <slug>|null,
    confidence: float   # derived: seen_count + recency
  }
Telemetry mirrors Hermes .usage.json (counts + state machine), but keyed by
*normalized signal*, so a recurring mistake bumps one record instead of piling up.
"""
import json
import os
import re
import time
from pathlib import Path

# ---- locations -------------------------------------------------------------

def project_root() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())

def store_dir() -> Path:
    d = project_root() / ".claude" / "evolve"
    return d

def _path(name: str) -> Path:
    return store_dir() / name

LEARNINGS = "learnings.json"
SIGNALS = "signals.jsonl"
FAILMARK = ".last-failure"

# lifecycle thresholds (days) — mirrors Hermes curator
STALE_AFTER = float(os.environ.get("EVOLVE_STALE_DAYS", "60"))
ARCHIVE_AFTER = float(os.environ.get("EVOLVE_ARCHIVE_DAYS", "120"))
PROMOTE_AT = int(os.environ.get("EVOLVE_PROMOTE_AT", "2"))   # seen_count to become a SKILL

# ---- io --------------------------------------------------------------------

def ensure_store() -> Path:
    d = store_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d

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
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    os.replace(tmp, p)   # atomic, like Hermes

def append_signal(sig: dict) -> None:
    ensure_store()
    with open(_path(SIGNALS), "a") as f:
        f.write(json.dumps(sig, ensure_ascii=False) + "\n")

def read_signals() -> list:
    p = _path(SIGNALS)
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out

def clear_signals() -> None:
    p = _path(SIGNALS)
    if p.exists():
        p.rename(p.with_suffix(".jsonl.processed"))

# ---- normalization & guardrails -------------------------------------------

def normalize(text: str) -> str:
    """Strip volatile bits so structurally-identical errors collapse to one key."""
    t = text.lower()
    t = re.sub(r"/[^\s:]+", " ", t)            # file paths
    t = re.sub(r"line \d+|column \d+|:\d+", " ", t)   # positions
    t = re.sub(r"0x[0-9a-f]+|\b\d+\b", " ", t)  # hex / numbers
    t = re.sub(r"['\"`].*?['\"`]", " ", t)      # quoted literals (varies per run)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:400]

# Things NOT worth learning — port of Hermes "DO NOT capture" list.
# Environment-specific / transient: capturing them creates false constraints.
_DENY = re.compile(
    r"command not found|no such file|permission denied|enoent|eacces|"
    r"address already in use|connection refused|could not resolve host|"
    r"network is unreachable|timed out|temporarily unavailable|"
    r"no space left|killed|broken pipe|api key|unauthorized|rate limit",
    re.I,
)

def is_noise(text: str) -> bool:
    return bool(_DENY.search(text or ""))

# ---- learning upsert (PATCH not append) -----------------------------------

def _slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return (s or "item")[:48]

def upsert(data: dict, typ: str, title: str, body: str, key=None) -> dict:
    """Bump an existing learning if its normalized key matches; else create.
    Returns the (new or updated) learning record."""
    key = key or normalize(title + " " + body)
    for rec in data.values():
        if rec.get("key") == key and rec.get("type") == typ:
            rec["seen_count"] = int(rec.get("seen_count", 1)) + 1
            rec["last_seen"] = iso(now())
            rec["state"] = "active"
            if body and len(body) > len(rec.get("body", "")):
                rec["body"] = body          # keep the richest description
            return rec
    rid = f"{typ}-{_slug(title)}-{int(now())}"
    rec = {
        "id": rid, "type": typ, "key": key,
        "title": title.strip()[:120], "body": body.strip()[:2000],
        "seen_count": 1, "first_seen": iso(now()), "last_seen": iso(now()),
        "state": "active", "promoted": False, "skill": None,
    }
    data[rid] = rec
    return rec

# ---- curator (state machine) ----------------------------------------------

def _age_days(iso_ts: str) -> float:
    try:
        t = time.mktime(time.strptime(iso_ts, "%Y-%m-%dT%H:%M:%SZ"))
        return (now() - t) / 86400.0
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
    """Higher = more worth surfacing. seen_count dominates, recency adjusts."""
    age = _age_days(rec.get("last_seen", iso(now())))
    recency = max(0.0, 1.0 - age / max(ARCHIVE_AFTER, 1))
    return int(rec.get("seen_count", 1)) * 10 + recency * 5
