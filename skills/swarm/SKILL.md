---
name: swarm
description: Backstage for Zoen. Fan cards as one lot, drain, one report. Each worker its own worktree. Parent reviews the diff. Invoked by zoen Execute.
---

# Swarm

Zoen is the talker. Fan N parallel workers. Parent drains,
aggregates, returns one report. You review the **diff**, not the
worker's summary. Workers never ship.

## Frame

Done predicate. Shape: partition into slices, or race the same brief,
or mix. N is total workers. Each writer gets its own worktree.

Do not fan cards that share mutable state. Those serialize.

## Fan

One `delegate_task` lot. Every brief stands alone: goal, slice, how
to verify, what to report (`PASS` | `ISSUES` | `BLOCKED` plus
evidence). Model: `openai/gpt-5.6-luna` for every slice.
If a worker drops, proceed with N-1 and note it.

## Aggregate

Every required slice needs a result. Do not paste raw dumps. Compact
table, one-line evidenced issues, gaps.

Workers do not Latch. Workers do not `gh pr merge`.
