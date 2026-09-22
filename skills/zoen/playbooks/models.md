# Models

The talker and orchestrator are `anthropic/claude-sonnet-5`: the
owner's turn, the opening, vision, and fallback. Every `delegate_task`
child is `openai/gpt-5.6-luna` with reasoning on. The runtime pins that
in `delegation`. The spawn has no model field. Do not name another slug.

Leaves never sequence iMessage. Do not pass Opus, Kimi, or GLM.
