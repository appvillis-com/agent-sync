#!/usr/bin/env bash
# Release every lease this run holds. An abandoned lease looks like active work
# until its TTL expires.
set -uo pipefail
. "${CLAUDE_PLUGIN_ROOT}/hooks/_lib.sh"
S="$AGENT_SYNC_PY"
agent_sync_configured || exit 0
held=$(run_limited 10 python3 "$S" whoami 2>/dev/null | sed -n 's/^holds: //p')
[ -z "$held" ] || [ "$held" = "nothing" ] && exit 0
IFS=', ' read -r -a keys <<<"$held"
for k in "${keys[@]}"; do
  [ -n "$k" ] && run_limited 10 python3 "$S" release "$k" >/dev/null 2>&1 || true
done
exit 0
