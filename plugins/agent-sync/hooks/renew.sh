#!/usr/bin/env bash
# Runs after every tool call, so it must be a no-op in the common case:
# the script itself throttles on a timestamp file and touches the network at
# most once per renewIntervalSeconds.
set -uo pipefail
S="${CLAUDE_PLUGIN_ROOT}/skills/agent-sync/scripts/agent_sync.py"
[ -f "${CLAUDE_PROJECT_DIR:-$PWD}/.claude/agent-sync.json" ] || exit 0
timeout 10 python3 "$S" renew >/dev/null 2>&1 || true
exit 0
