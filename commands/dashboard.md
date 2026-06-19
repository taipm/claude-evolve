---
description: Render a visual HTML dashboard + metrics of the learning store
---

Show the learning metrics and a visual dashboard for this project.

1. Print the metrics:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/metrics.py"
   ```

2. Render the standalone HTML dashboard and tell the user the path to open:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/dashboard.py"
   ```
   It writes `.claude/evolve/dashboard.html` — open it in a browser.

3. Give a short read on learning health: is knowledge accumulating, what share recurs
   (dedup working), how many lessons promoted to skills, and how much is still active vs
   stale. Be explicit that the `effectiveness_proxy` is a proxy — a promoted lesson going
   quiet *suggests* the injected knowledge is helping, but proving it needs an on/off A/B.
