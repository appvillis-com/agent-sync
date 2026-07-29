---
description: Coordinate concurrent agents — initialise the shared knowledge store, check status, claim a task, reserve an id, or regenerate the board.
argument-hint: "[init|status|claim <KEY>|release <KEY>|reserve <REG>|board|finish]"
---

Invoke the `agent-sync` skill.

Arguments: $ARGUMENTS

If no arguments were given, run the skill's default entry: check whether the
project is initialised, and if it is not, **ask the operator where coordination
state should live before doing anything else** — a knowledge cloud (and then its
instance URL) or local files. Never guess that answer.

If the project is already initialised, report status and name exactly one next
action.

With `finish`, run the end-of-work check instead: every repository clean, pushed and pointed at,
and no lease left held. In a project of git submodules that is the one failure nobody sees — the
submodule is pushed and the parent still points at the commit before the work.
