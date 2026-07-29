#!/bin/sh
# POSIX fallback installer. Prefer `npx agent-sync install` — it is cross-platform.
# This script is POSIX-only: on Windows use npx, the Claude Code plugin, or the
# skills CLI, never this file.
set -eu

REPO="appvillis-com/agent-sync"
NAME="agent-sync"
SHADOW="$HOME/.claude/skills/$NAME"

echo "Installing $NAME"

if command -v claude >/dev/null 2>&1; then
  echo "  Claude Code — as a plugin"
  claude plugin marketplace add "$REPO" || true
  # The full <name>@<name> id is required.
  claude plugin install "$NAME@$NAME" || true
else
  echo "  claude CLI not found; skipping the plugin channel"
fi

if command -v npx >/dev/null 2>&1; then
  echo "  Other agents — via the skills CLI"
  npx --yes skills add "$REPO" --global --yes || true
else
  echo "  npx not found; skipping the skills-CLI channel"
fi

# The skills CLI recreates this copy on its own — often as a symlink — even when
# claude-code was never targeted. It shadows the plugin and serves a stale skill.
if [ -e "$SHADOW" ] || [ -L "$SHADOW" ]; then
  rm -rf "$SHADOW"
  echo "  pruned duplicate $SHADOW"
fi

echo
echo "Restart Claude Code, then run /agent-sync init in your project."
