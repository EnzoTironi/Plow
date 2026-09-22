# Models

Every turn and every `delegate_task` uses `anthropic/claude-sonnet-5`.
Talker, leaves, vision, fallback, swarm, arena, review, and heavy
work are the same slug. The talker sends the first ack. Leaves never
sequence iMessage.

Do not pass Luna, Opus, Kimi, or GLM.

Pass `model` on the spawn. Same slug if the runtime ignores unknown keys.
