---
name: tdd
description: Backstage for Zoen. Fail a cheap check first, then fill it in. Skip when a new test would be expensive, fake, or unclear. Invoked per card on Execute and on bug-fix.
---

# TDD

Zoen is the talker. Make the broken behavior executable before
changing production code. Prefer no new test over a bad test.
Fill-in and seams: `anthropic/claude-sonnet-5`.

Do not force a test when it would need a broad harness, brittle
mocks, slow end-to-end infra, production-only state, or large
unrelated fixtures. Then the closest executable path, and say why.

## Steps

1. Understand the break. Intended vs current, smallest repro.
2. Narrowest executable check. Existing test for that path first.
   Else the user-path the card named.
3. Write the failing check first. Encodes intended behavior, not
   the current implementation.
4. Watch it fail for the right reason. Wrong fail or a pass → fix
   the check before production code.
5. Smallest fill-in that preserves nearby contracts.
6. Watch it pass.
7. Nearby validation (adjacent tests, typecheck, the user-path).

Do not close a card until that check is green.

## Guardrails

Do not change tests to match a wrong implementation. Do not weaken
assertions unless the expected behavior changed. Keep the check
focused on this break.
