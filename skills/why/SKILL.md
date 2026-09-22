---
name: why
description: Backstage for Zoen. Why the code is shaped this way. Blame, merge commits, cited tradeoffs. Invoked by zoen after ack. Use how for runtime behavior.
---

# Why

Zoen is the talker. Read-only. Companion to how. Honest about known
vs inferred. Guessing is labeled a guess.

Run this when the work redefines ownership or layering, or the
question is motivation, a tradeoff, or a regression.

## Anchor

```sh
git blame -L <start>,<end> <file>
git log --follow -p -- <file>
git log --oneline -20 -- <file>
gh pr view <number> --json title,body,author,mergedAt,comments
```

Seed: paths, symbols, commits, PR numbers, linked issues.

## Evidence

Fan readonly `delegate_task` leaves in one lot, one source each that
exists. Investigators and synthesis: `anthropic/claude-sonnet-5`.

1. git + `gh` (always)
2. Linear (`issues.py linear`) when `LINEAR_API_KEY` is set
3. `watch.py snapshot` when Sentry/PostHog tokens exist

Document the null. Do not invent a source.

## Return

Cited tradeoffs. Known vs inferred. What not to treat as a day-one
constraint. JSON. No bubble.
