#!/usr/bin/env bash
# Register the run and print the board summary plus one next action.
set -uo pipefail
. "${CLAUDE_PLUGIN_ROOT}/hooks/_lib.sh"
S="$AGENT_SYNC_PY"
agent_sync_configured || exit 0

# Stamp who this session is, keyed by the process every command in it descends from.
# A hook has CLAUDE_SESSION_ID in its environment and a plain shell command does not, so without
# this a second session in the same checkout adopts the first one's identity: both acquire and
# release as one run, and the lease stops separating the exact case it exists for. $PPID here is
# the CLI process, which is the one ancestor every later command shares.
if [ -n "${CLAUDE_SESSION_ID:-}" ]; then
  d="$(git rev-parse --show-toplevel 2>/dev/null)/.agent-sync/sessions"
  if mkdir -p "$d" 2>/dev/null; then
    printf '%s' "$CLAUDE_SESSION_ID" > "$d/$PPID" 2>/dev/null || true
    # forget the stamps of processes that are gone, so the directory cannot grow without bound
    for f in "$d"/*; do
      b="$(basename "$f")"
      case "$b" in *[!0-9]*) continue ;; esac
      kill -0 "$b" 2>/dev/null || rm -f "$f"
    done
  fi
fi

run_limited 10 python3 "$S" status 2>&1 || true
exit 0
