# Models

Plow slugs on every `delegate_task`. Talker is `openai/gpt-5.6-luna`.
The talker sends the first ack. Leaves never sequence iMessage.

| Role | Slug |
| --- | --- |
| talker / first ack | `openai/gpt-5.6-luna` |
| how explorer, why investigator, easy swarm/tdd | `openai/gpt-5.6-luna` |
| vision, fallback, cheap bulk, long image/video | `z-ai/glm-5.3-flash` |
| how explainer, seams, contracts, multi-file, prove | `moonshotai/kimi-k2.5` |
| frontend arena/swarm (UI, React, CSS, iMessage card), difficult execute | `moonshotai/kimi-k3` |
| hours, spec, architect lead, arena form, why synth, blast, figure-it-out | `anthropic/claude-opus-5` |
| interrogate reviewers | `anthropic/claude-opus-5` and `moonshotai/kimi-k3` |

Do not pass `anthropic/claude-sonnet-5`.

Triage a swarm/arena worker: UI or a hard execute → K3. One file / fill-in / cheap tdd → Luna.
Seam, contract, multi-file → Kimi K2.5. Cheap bulk or media → GLM 5.3 Flash.
Shape, auth/money/prod, scrap → Opus.

Pass `model` on the spawn. Same slug if the runtime ignores unknown keys.
