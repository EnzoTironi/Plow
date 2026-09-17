---
name: arena
description: Backstage for Zoen. Fan competing whole-shape sketches, pick a base, graft the rest. Do not average. Invoked by architect Shape.
---

# Arena

Zoen already acked. Fan N parallel attempts at the same sketch.
Pick the strongest as the base. Graft the best of the losers into it.
Do not average. Wild divergence means the Brief was thin. Re-run
**how**. Do not synthesize soup.

## Frame

Each candidate gets the same Brief. State the artifact (types,
signatures, modules, `not implemented` bodies). Derive 3–6 gradeable
criteria the picker will use. Candidates do not see the rubric.

N ≥ 2. Each candidate its own worktree or `/tmp/arena-<slug>/<n>/`.

## Fan

One `delegate_task` lot. Each worker writes the sketch plus a short
rationale (what it considered and rejected). Form sketches:
`anthropic/claude-opus-5`. UI sketches: `moonshotai/kimi-k3`. Cross-judge:
`anthropic/claude-opus-5`. If one drops, proceed with N-1 and note it.

## Pick

Read every candidate end to end. Score criterion by criterion. Pick
the base a future maintainer can extend without breaking invariants.
Smaller public surface wins a tie.

## Graft

One or two things per loser, folded by hand so one mental model
remains. Record what was grafted and what was rejected.

Return the synthesized sketch as JSON. Zoen reviews it. Workers
never ship.
