#!/usr/bin/env bash
# Runs after every tool call, so it must be a no-op in the common case:
# the script itself throttles on a timestamp file and touches the network at
# most once per renewIntervalSeconds.
set -uo pipefail
. "${CLAUDE_PLUGIN_ROOT}/hooks/_lib.sh"
S="$AGENT_SYNC_PY"
agent_sync_configured || exit 0
run_limited 10 python3 "$S" renew >/dev/null 2>&1 || true
exit 0
