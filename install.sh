#!/usr/bin/env bash
# claude-evolve installer — registers the plugin's marketplace and installs it.
# Idempotent. Works against the Gitea origin or the GitHub mirror.
set -euo pipefail

GITEA_URL="https://git.microai.club/taipm/claude-evolve"
GITHUB_URL="https://github.com/taipm/claude-evolve"
# Default to the GitHub mirror: anonymous git clone works everywhere. The Gitea
# origin also supports anonymous clone, but its raw-file web endpoint requires login,
# so the curl-bootstrap one-liner must come from GitHub. Override with EVOLVE_SOURCE.
SRC="${EVOLVE_SOURCE:-$GITHUB_URL}"

echo "claude-evolve installer"
echo "  source: $SRC"

if ! command -v claude >/dev/null 2>&1; then
    echo "error: 'claude' CLI not found. Install Claude Code first." >&2
    exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
    echo "error: python3 not found (required). Install Python 3.8+." >&2
    exit 1
fi

echo "==> Registering marketplace"
claude plugin marketplace add "$SRC" 2>/dev/null \
    || claude plugin marketplace update claude-evolve 2>/dev/null \
    || true

echo "==> Installing plugin"
claude plugin install claude-evolve@claude-evolve

echo
echo "Installed. Restart Claude Code (or run /reload-skills)."
echo "Check it:  /claude-evolve:status"
echo "Mirror:    $GITHUB_URL"
