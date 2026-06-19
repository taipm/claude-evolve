#!/usr/bin/env python3
"""dashboard.py — render a standalone HTML dashboard of the learning store.

Reads metrics.compute() and writes a self-contained HTML file (no JS deps, no network)
that visualizes retention, promotion, freshness, the recurrence histogram, the
effectiveness proxy, and the top lessons. Usage:

  python3 dashboard.py                 # writes .claude/evolve/dashboard.html
  python3 dashboard.py /tmp/out.html   # custom path
Open the file in a browser.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import store      # noqa: E402
import metrics    # noqa: E402

CSS = """
:root{--bg:#0e1116;--card:#171b22;--ink:#e6edf3;--mut:#8b949e;--ok:#3fb950;
--warn:#d29922;--bad:#f85149;--accent:#58a6ff;--line:#272d36}
*{box-sizing:border-box;font-family:-apple-system,Segoe UI,Roboto,sans-serif}
body{margin:0;background:var(--bg);color:var(--ink);padding:28px}
h1{font-size:20px;margin:0 0 2px}.sub{color:var(--mut);font-size:13px;margin-bottom:20px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:14px;margin-bottom:18px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}
.kpi .v{font-size:30px;font-weight:700}.kpi .l{color:var(--mut);font-size:12px;margin-top:4px}
.kpi .v.ok{color:var(--ok)}.kpi .v.accent{color:var(--accent)}
.bar{height:10px;border-radius:6px;background:#21262d;overflow:hidden;margin:6px 0}
.bar>span{display:block;height:100%}
.row{display:flex;justify-content:space-between;font-size:13px;margin:9px 0 2px}
table{width:100%;border-collapse:collapse;font-size:13px}
td,th{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line)}
th{color:var(--mut);font-weight:600}
.tag{font-size:11px;padding:2px 7px;border-radius:20px;border:1px solid var(--line)}
.t-build_failure{color:var(--bad)}.t-correction{color:var(--warn)}.t-fix{color:var(--ok)}
.pill{font-size:11px;padding:1px 7px;border-radius:20px;background:#1f6feb33;color:var(--accent)}
.note{color:var(--mut);font-size:12px;margin-top:8px;line-height:1.5}
"""

COLORS = {"build_failure": "#f85149", "correction": "#d29922", "fix": "#3fb950", "note": "#8b949e"}


def _bars(d, total):
    out = []
    for k, v in sorted(d.items(), key=lambda x: -x[1]):
        pct = (v / total * 100) if total else 0
        c = COLORS.get(k, "#58a6ff")
        out.append(f'<div class="row"><span>{k}</span><span>{v}</span></div>'
                   f'<div class="bar"><span style="width:{pct:.0f}%;background:{c}"></span></div>')
    return "".join(out)


def render(m: dict) -> str:
    t = m["totals"]; fr = m["freshness"]; ef = m["effectiveness_proxy"]
    ral = m.get("recurrence_after_learning", {})
    rows = "".join(
        f'<tr><td>{r["title"]}</td>'
        f'<td><span class="tag t-{r["type"]}">{r["type"]}</span></td>'
        f'<td>{r["seen"]}</td><td>{r["state"]}</td>'
        f'<td>{"✓" if r["promoted"] else ""}</td></tr>'
        for r in m["top"]
    )
    seen_total = sum(m["seen_histogram"].values())
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>claude-evolve dashboard</title><style>{CSS}</style></head><body>
<h1>claude-evolve · learning dashboard</h1>
<div class="sub">{store.project_root()}</div>

<div class="grid">
  <div class="card kpi"><div class="v">{t['learnings']}</div><div class="l">distinct lessons</div></div>
  <div class="card kpi"><div class="v accent">{t['signals_absorbed']}</div><div class="l">signals absorbed</div></div>
  <div class="card kpi"><div class="v">{int((1-t['distinct_to_signal_ratio'])*100)}%</div><div class="l">were repeats (deduped)</div></div>
  <div class="card kpi"><div class="v ok">{t['skills_promoted']}</div><div class="l">promoted to skills</div></div>
  <div class="card kpi"><div class="v">{int(t['promotion_rate']*100)}%</div><div class="l">promotion rate</div></div>
  <div class="card kpi"><div class="v">{int(fr['active_share']*100)}%</div><div class="l">knowledge active</div></div>
</div>

<div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(240px,1fr))">
  <div class="card"><b>By type</b>{_bars(m['by_type'], t['learnings'])}</div>
  <div class="card"><b>By state (freshness)</b>{_bars(m['by_state'], t['learnings'])}</div>
  <div class="card"><b>Recurrence histogram</b>{_bars(m['seen_histogram'], seen_total)}
    <div class="note">How many times each lesson recurred. Higher buckets = stronger, repeatedly-confirmed lessons.</div></div>
  <div class="card"><b>Effectiveness proxy</b>
    <div class="row"><span>promoted lessons</span><span>{ef['promoted']}</span></div>
    <div class="row"><span>quiet since learned</span><span style="color:var(--ok)">{ef['quiet_since_promotion']}</span></div>
    <div class="row"><span>still recurring</span><span style="color:var(--warn)">{ef['still_recurring']}</span></div>
    <div class="bar"><span style="width:{ef['quiet_share']*100:.0f}%;background:#3fb950"></span></div>
    <div class="note">Proxy only: a promoted lesson that goes <b>quiet</b> (stops recurring) suggests the
    injected knowledge is helping. Proving causation needs an on/off A/B over real usage.</div></div>
  <div class="card"><b>Recurrence after learning</b>
    <div class="row"><span>promoted (instrumented)</span><span>{ral.get('promoted', 0)}</span></div>
    <div class="row"><span>quiet after learning</span><span style="color:var(--ok)">{ral.get('quiet_after', 0)}</span></div>
    <div class="row"><span>recurred after learning</span><span style="color:var(--warn)">{ral.get('recurred_after', 0)}</span></div>
    <div class="row"><span>avg post-promotion recurrences</span><span>{ral.get('avg_post_promotion_recurrences', 0.0)}</span></div>
    <div class="note">Lessons that went quiet after being learned suggest the loop is working; proving causation needs an on/off A/B.</div></div>
</div>

<div class="card"><b>Top lessons</b>
<table><tr><th>lesson</th><th>type</th><th>seen</th><th>state</th><th>skill</th></tr>{rows}</table></div>
</body></html>"""


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else store.store_dir() / "dashboard.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(metrics.compute()))
    print(f"dashboard written: {out}")


if __name__ == "__main__":
    main()
