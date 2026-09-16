# Bug fix

You own this task. Plan, review, verify. Every shipped line traces to
a run of the product, not a guess.

1. Reproduce it yourself. Skill **prove**, Hands. Do not hand the
   repro to the owner. Drive Latch if the Mac app is there, else
   the container path. Missing app and the repro needs their
   desktop: `playbooks/kit.md`.
2. Binary-search the cause. **how** on the subsystem. **why** if it
   looks like a regression (blame, `gh pr view`). Confirm the
   surviving mechanism with a run before you patch.
3. Plan the fix. Crossing a function boundary → **architect**. Cheap
   local test path → **tdd**. Else the closest executable check, and
   say why a new test is not worth it. One GitHub issue for this
   break (`playbooks/cards.md`) unless they already sent one. Skip
   a spec. One window.
4. Smallest patch the evidence justifies. Nothing more.
5. **prove** on the same surface. The original repro now passes.
   Inconclusive is not a pass.
6. **Opening a PR**. Then **review**, **babysit**, **blast-radius**,
   **merge** as in Feature.
