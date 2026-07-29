#!/usr/bin/env bash
# Register the run and print the board summary plus one next action.
set -uo pipefail
. "${CLAUDE_PLUGIN_ROOT}/hooks/_lib.sh"
S="$AGENT_SYNC_PY"
agent_sync_configured || exit 0
run_limited 10 python3 "$S" status 2>&1 || true
exit 0
