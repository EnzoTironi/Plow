---
name: review
description: Backstage for Zoen. Scanners plus interrogate plus the picture-map on a diff. Fix act on the PR. Invoked after Opening a PR and from babysit. Does not merge.
---

# Review

Zoen already acked. Code and comments. You are lead.

`python3 /opt/plow/zoen/bundle.py` on the diff. Then **interrogate**
(Opus + Sonnet reviewers).

Same finding schema:

```text
file, line, severity (critical|high|medium|low),
verdict (act|consider|noted|dismissed), evidence, rule
```

Picture: you write `.pr-lens/graph.json` from the diff (prompt, not a
thinking key). Then `python3 /opt/plow/zoen/lens.py push --repo …`.
Bubble **only** `view_url`. Never `#w=`. Put the same `zoen-review/`
files in the PR body and on iMessage.

Fix `act` on the PR. Do not wait for a yes to comment. After a patch,
**prove** again.

Do not merge from here. That is skill merge.
