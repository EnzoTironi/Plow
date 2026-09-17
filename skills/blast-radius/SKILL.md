---
name: blast-radius
description: Backstage for Zoen. The one fact this change is safe because of. Prove it by running code. Invoked before merge. Do not write it up as settled if you did not run it.
---

# Blast radius

Zoen already acked. What the change breaks somewhere else, before it
ships. Listing callers is not the job. Grep those in a second. The
job is the breakage grep will not show. High-risk / critical:
`anthropic/claude-opus-5`.

Companion to how and why.

## Don't trust the writeup

Find the one or two facts the whole thing depends on. Prove them by
running code.

For each fact, get as far down this list as is cheap, and say where
it stopped.

1. You said so. Worthless on its own.
2. You pointed at the line. A real `file:line`.
3. You showed the bad case cannot happen.
4. You ran it. A script or test that calls the real code and fails
   loud if you are wrong.
5. You reproduced it in the running app.

Any safety fact you cannot get to step 4, say so. Unrun is unproven.
Do not write it up as settled.

## Steps

1. Read the change, including what the diff does not spell out.
2. The one fact it is safe because of. Spend time here.
3. Look where grep stops: library source, pinned version, when things
   run, JSON a wire returns, a DB column, another language on the
   same bytes.
4. Real chance and real cost. Keep confirmed risks. List cleared ones
   separately.
5. Prove the one fact. Paste what ran.
6. Wide change: **interrogate** the same question, merge the answers.

## Return

What it does. The one fact (proven or unproven). Risks. Cleared.
Cheapest check that would catch the real bug. JSON to zoen.
