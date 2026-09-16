# Cards

The owner has no Hermes kanban. iMessage is not a board. GitHub
issues are the board they can open. NOW.md is scratch for Zoen,
under 10 lines, not the backlog.

GitHub is `gh`. Do not write a Python wrapper. Do not wait for a
yes to open.

Skip a ticket list when the whole change fits one turn. One issue,
or go straight to execute and the PR.

```sh
gh issue create --title "..." --body "..."
gh issue create --parent N --blocked-by 12,15
gh issue edit N --add-sub-issue M
gh issue comment N --body "..."
gh issue close N
gh issue list --state open
```

`--parent` hangs a ticket under the spec issue. `--blocked-by`
is the native edge. Publish blockers first so the numbers exist.
Do not write "Blocked by" only in the body when `gh` can take
`--blocked-by`.

## Tracer bullets, not layers

Each ticket is a thin path through every layer the change needs
(schema, API, UI, tests). Vertical. Not "all the schema" then
"all the API".

A ticket without an answer to "what can I demo when this is
done?" is not a ticket. The answer is behavior, not a layer.
Rewrite, then create.

Each ticket is sized for one fresh turn. Prefactor first: make
the change easy, then make the easy change. Prefactor tickets
are at the front of the order.

## Fail at HEAD

Every acceptance line must be false on the commit the worker
starts from. Name the observation that would show it false.
Three defects:

- already true at the base commit
- only another ticket can make it true
- restates the ask instead of an artifact

## Wide refactor

One mechanical change whose blast radius is the whole tree
(rename a column, retype a shared symbol) is not a tracer
bullet. Sequence expand, then migrate in batches, then
contract. Each migrate ticket is blocked by expand. Contract
is blocked by every migrate. If a batch cannot stay green
alone, they share a branch and all block one prove ticket.

## Body

No file paths. No line numbers. Exception: a prototype snippet
that encodes a state machine, reducer, schema, or type.

```text
## Parent
spec issue N, or omit

## What to build
end-to-end behavior, their words, not a layer list

## Demo
what works when this lands

## Acceptance
- [ ] criterion that is false at HEAD
- [ ] criterion that this ticket owns

## Blocked by
none, or the issue numbers
```

If they already sent a GitHub or Linear issue, that is the
ticket. Do not clone it. Comment there.

Linear is intake only unless MEMORY says Linear is their board.
Default board is GitHub.

## Order

Work the frontier: any ticket whose blockers are done. A linear
chain is top to bottom. Stamp NOW `spec: N` and `issues: 12,13`.
Do not paste full URLs into NOW.md.

Do not close or rewrite the spec while children are open.
PR open: comment the PR URL on the ticket, leave it open.
Prove green and merge: `gh issue close N` on that ticket.
Last ticket shipped: close the spec.

## Missing `gh` or login

`playbooks/kit.md`. Do not tell them to install `gh`. Keep units
on NOW.md.

## Notify

Two-line bubbles with the numbered slices (title, blocked by,
what it demos), then each new issue URL in its own bubble, same
as a PR URL. Never say card, ticket, kanban, floor, or Hermes.
A no later is a re-map, not a sales pitch.
