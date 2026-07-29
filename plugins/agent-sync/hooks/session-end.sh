#!/usr/bin/env bash
# Release every lease this run holds. An abandoned lease looks like active work
# until its TTL expires.
set -uo pipefail
S="${CLAUDE_PLUGIN_ROOT}/skills/agent-sync/scripts/agent_sync.py"
[ -f "${CLAUDE_PROJECT_DIR:-$PWD}/.claude/agent-sync.json" ] || exit 0
held=$(timeout 10 python3 "$S" whoami 2>/dev/null | sed -n 's/^holds: //p')
[ -z "$held" ] || [ "$held" = "nothing" ] && exit 0
IFS=', ' read -r -a keys <<<"$held"
for k in "${keys[@]}"; do
  [ -n "$k" ] && timeout 10 python3 "$S" release "$k" >/dev/null 2>&1 || true
done
exit 0
