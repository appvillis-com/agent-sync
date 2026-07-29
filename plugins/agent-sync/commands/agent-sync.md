---
description: Coordinate concurrent agents — initialise the shared knowledge store, check status, claim a task, reserve an id, or regenerate the board.
argument-hint: "[init|status|claim <KEY>|release <KEY>|reserve <REG>|board]"
---

Invoke the `agent-sync` skill.

Arguments: $ARGUMENTS

If no arguments were given, run the skill's default entry: check whether the
project is initialised, and if it is not, **ask the operator where coordination
state should live before doing anything else** — a knowledge cloud (and then its
instance URL) or local files. Never guess that answer.

If the project is already initialised, report status and name exactly one next
action.
