---
name: figure-it-out
description: Backstage for Zoen. When no playbook fits. Frame a falsifiable done, rigor, riskiest-unknown-first. Write that list on NOW.md, then run it. Do not invent a new Zoen script.
---

# Figure it out

Zoen already acked. When Feature, Bug fix, and Investigation do not
fit (big migration, multi-hour, unknown), design the run first.
Spawn this lead on `anthropic/claude-opus-5`.

Do not invent a new Zoen script.

## Frame

Do not start until you can state:

- Falsifiable done predicate
- Scope, rough units, blockers
- Rigor, biased high on one-way doors. Reversible low-stakes get less.
  Rigor is gates and artifacts, not try harder

Write that on NOW.md. Continue. A multi-hour run earns one two-line
checkpoint, then work.

## Design

Atomic units. Riskiest-unknown-first. Scaffold and the check before
the feature. **architect** for one-way-door shape. Skip it for
mechanical work whose shape is already concrete. Fan only across
seams. Each worker its own worktree.

That list is the playbook. Multi-turn: spec then vertical GitHub
issues per zoen `playbooks/spec.md` and `playbooks/cards.md`. One
turn: skip the spec. Common domain: **find-skills** (silent
`npx skills use`). Then run it.

## Loop

Each unit is an experiment. Smallest change. Measure on the real
artifact. Keep if it advanced. Revert if it did not. Verify each
unit before the next. Inconclusive is not a pass.

## Hand back

**prove** against the Frame predicate. Encode a recurring correction
as a gate, a lint, a check, or a MEMORY.md line. Two-line notify
plus pictures.
