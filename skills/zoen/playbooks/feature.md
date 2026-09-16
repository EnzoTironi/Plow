# Feature

You own the design. Plan, review, verify. Delegate implementation.
Stay the talker.

Skip hours when they already named the work. Skip how when greenfield.

1. **hours** only if they are lost. A named ask skips.
2. **how** over the affected subsystem. Ownership or layering changes:
   **why** as well.
3. **architect**. It runs **arena**, then **interrogate** on the
   winner. Skipping stays as `architect skipped: <reason>`. Do not
   fold the shape into the first patch. Known stack (web, test,
   deploy, docs): **find-skills** (silent `npx skills use`). Empty
   is a skip, not a stall.
4. Spec (`playbooks/spec.md`) when the work spans more than one
   turn. One GitHub issue: problem, solution, stories, decisions,
   seams, out of scope. Skip if it fits one window. Do not interview
   again.
5. Cards (`playbooks/cards.md`). Vertical slices under the spec:
   `--parent`, `--blocked-by`, demo path, acceptance that fails at
   HEAD. Skip a list if one window: one issue or go to execute.
   Notify with the issue URLs. Do not wait.
6. Triage. Riskiest-unknown-first. Stamp NOW `risk:` `low` or `high`.
   High: auth, money, production, migration, public api, delete.
7. Plan. Work the frontier (blockers done). Scaffold and the
   user-path check before the feature.
8. Review the plan. Attack the plan, not the idea. A card without a
   demo path or a check that is already green at HEAD is not a card.
   Reject and rewrite.
9. **swarm** the cards that do not share mutable state. **tdd** on
   each cheap check, only at the spec's seams. You review the
   **diff**, not the worker summary. Workers never ship. Prove fails
   → execute again, cap 3, then notify once.
10. Pattern of workarounds → **architect** Scrap. Do not bolt.
11. **prove**. After execute, before the PR.
12. **Opening a PR** (`playbooks/opening-a-pr.md`).
13. **review** on the PR. Fix `act`. **prove** again after every fix.
14. **babysit** comments and checks. Same: patch, then **prove**.
15. **blast-radius**, then **merge**. Close tickets, then the spec.

Continue. A no later is a re-map, not a sales pitch.
