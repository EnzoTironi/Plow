---
name: interrogate
description: Backstage for Zoen. Adversarial review of a sketch or a diff. Synthesized verdict. Do not auto-apply. Invoked by zoen on Pick and on Review.
---

# Interrogate

Zoen is the talker. Fan readonly leaves on the same brief. The
signal is independent reads, different models if the runtime allows,
same prompt if it does not. Deliverable is a synthesized verdict.
Do NOT auto-apply.

## Scope

Diff, files, or the architect sketch. On a feature branch:
`git diff` against the base. Package enough surrounding files to
understand the change.

## Intent

One paragraph from the Brief, commits, or PR body. Then spawn.

## Fan

One `delegate_task` lot. Same schema from every leaf. Reviewers:
`anthropic/claude-opus-5` and `moonshotai/kimi-k3`. Critical
auth/money/prod: Opus is lead.

```text
file, line, severity (critical|high|medium|low),
verdict (act|consider|noted|dismissed), evidence, rule
```

Wide change: specialist leaves in one batch (security, infra, data).

## Lead

You are lead, not an average. Consensus of 2+ leaves weighs more.
No evidence in the file → `dismissed`. Lone-model findings still
get read, less weight. Disagreement is useful.

- **act**: would block a real PR
- **consider**: real, cost may not be worth it now
- **noted**: valid, not actionable
- **dismissed**: no evidence, or noise

Return the verdict JSON. Zoen decides what to patch.
