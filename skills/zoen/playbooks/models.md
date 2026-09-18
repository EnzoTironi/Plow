# Models

Plow slugs on every `delegate_task`. Talker is `openai/gpt-5.6-luna`.
The talker sends the first ack. Leaves never sequence iMessage.

| Role | Slug |
| --- | --- |
| talker / first ack | `openai/gpt-5.6-luna` |
| how explorer, why investigator, easy swarm/tdd | `openai/gpt-5.6-luna` |
| frontend arena/swarm (UI, React, CSS, iMessage card) | `moonshotai/kimi-k3` |
| how explainer, difficult execute, prove | `anthropic/claude-sonnet-5` |
| hours, spec, architect lead, arena form, why synth, blast, figure-it-out | `anthropic/claude-opus-5` |
| interrogate reviewers | `anthropic/claude-opus-5` and `anthropic/claude-sonnet-5` |

Triage a swarm/arena worker: UI → K3. One file / fill-in / cheap tdd → Luna.
Seam, contract, multi-file → Sonnet. Shape, auth/money/prod, scrap → Opus.

Pass `model` on the spawn. Same slug if the runtime ignores unknown keys.
