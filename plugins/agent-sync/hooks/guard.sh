#!/usr/bin/env bash
# PreToolUse guard. Exit 2 blocks the call and shows stderr as the reason.
# Any other non-zero code is NON-blocking in Claude Code, so every internal
# failure must also exit 2 — a crashing guard that fails open guards nothing.
set -uo pipefail
S="${CLAUDE_PLUGIN_ROOT}/skills/agent-sync/scripts/agent_sync.py"
input=$(cat)

path=$(python3 -c '
import json,sys
try:
    d=json.load(sys.stdin)
except Exception:
    sys.exit(0)
ti=d.get("tool_input") or {}
print(ti.get("file_path") or ti.get("path") or ti.get("notebook_path") or "")
' <<<"$input" 2>/dev/null)

# git commit: check every staged path instead of a single file argument.
if [ -z "$path" ]; then
  cmd=$(python3 -c '
import json,sys
try:
    d=json.load(sys.stdin)
except Exception:
    sys.exit(0)
print((d.get("tool_input") or {}).get("command",""))
' <<<"$input" 2>/dev/null)
  case "$cmd" in
    *"git commit"*)
      while IFS= read -r staged; do
        [ -n "$staged" ] || continue
        if ! python3 "$S" guard "$staged" >/dev/null 2>&1; then
          echo "agent-sync: '$staged' is staged but this run holds no lease on it. Acquire one, or unstage it." >&2
          exit 2
        fi
      done < <(git diff --cached --name-only 2>/dev/null)
      ;;
  esac
  exit 0
fi

[ -f "${CLAUDE_PROJECT_DIR:-$PWD}/.claude/agent-sync.json" ] || exit 0

if out=$(python3 "$S" guard "$path" 2>&1); then
  exit 0
else
  code=$?
  if [ "$code" -eq 2 ]; then
    echo "$out" >&2
    exit 2
  fi
  echo "agent-sync guard failed to run ($code): $out" >&2
  exit 2
fi
