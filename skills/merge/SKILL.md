---
name: merge
description: Backstage for Zoen. Land a PR. low risk and last prove green: gh pr merge. high risk: notify and wait. Invoked after blast-radius.
---

# Merge

Zoen is the talker. **blast-radius** first. Merge reads the last
**prove**, not the last comment.

`low` risk and last prove green: `gh pr merge`.
`high` risk: notify, wait. They approve → merge. A no is a stop.

High: auth, money, production, migration, public api, delete.

Two-line bubbles, then pictures and video, then the PR URL.

```sh
gh pr merge N
```

Do not merge from cron when NOW `risk:` is `high`.
Do not delete production, force-push shared history, or spend money
unless they asked. GitHub is `gh`. No Python wrapper.

High-risk merge waits.
