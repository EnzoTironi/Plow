# Spec

Synthesize what is already decided. Do not interview again. Publish
one GitHub issue that is the decision record. Tickets hang off it.

GitHub is `gh`. Do not wait for a yes to open.

Skip this playbook when the whole change fits one turn. Go to
execute, or one issue via `playbooks/cards.md`. A spec exists because
context ends. One-turn work does not need it.

## Seams first

Before any prose, name the seams the feature will be tested at.
Prefer seams that already exist. Take the highest seam. Ideal
number across the change is one. New seams only at the highest
point you can.

Two-line notify of the seams, then write. A no is a stop and a
re-map, not a sales pitch.

**tdd** and **prove** only at those seams. A seam nobody named
shows up as a **review** finding.

## Write, then publish

Explore the repo if you have not. Use their nouns, not generic
product language. Respect decisions already in MEMORY.md and the
repo. Inventing a decision to fill a section is a defect.

```text
## Problem
from their side

## Solution
from their side

## Stories
numbered. each: as a <who>, I want <what>, so that <why>
cover the feature. do not pad

## Decisions
modules, interfaces, schema, contracts, what you refused
no file paths, no line numbers
exception: a prototype snippet that encodes a state machine,
reducer, schema, or type. trim to the decision

## Tests
external behavior only. which seams. prior art in the repo

## Out of scope
the things you refused. empty is a defect

## Notes
anything left
```

```sh
gh issue create --title "..." --body "..."
```

That issue is the spec. Stamp NOW `spec: N`. Do not close it when
child tickets open. Close it when the work has shipped.

Do not apply a ready-for-agent label that would make cron treat
the spec as a card to implement. The spec is the parent, not a
work order.

## Notify

Two-line bubbles, then the spec URL in its own bubble. Never say
spec, card, kanban, or Hermes.
