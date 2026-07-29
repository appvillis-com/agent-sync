#!/usr/bin/env bash
# Register the run and print the board summary plus one next action.
set -uo pipefail
S="${CLAUDE_PLUGIN_ROOT}/skills/agent-sync/scripts/agent_sync.py"
[ -f "${CLAUDE_PROJECT_DIR:-$PWD}/.claude/agent-sync.json" ] || exit 0
timeout 10 python3 "$S" status 2>&1 || true
exit 0
