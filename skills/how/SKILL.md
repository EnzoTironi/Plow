---
name: how
description: Backstage for Zoen. How the system works, enough to change it. Read-only map. Invoked by zoen after ack. Use why for motivation.
---

# How

Zoen already acked. Read-only. Return JSON, not a bubble.

Listing files is not mapping. Produce a traced model: owners, edges,
data shapes, what not to touch.

## Complexity

- **Simple** (one module, one function): one `delegate_task` leaf.
  Explore and explain in a single pass.
- **Complex** (several files or services): 2–4 angles in one
  `delegate_task` lot, then one synthesis leaf.
- When in doubt, simple.

Leaves are readonly. They do not Latch. They do not ship.

## Return

Overview, Key Concepts, How It Works, Where Things Live, Gotchas.
Drop a section that does not apply.

Skip only when greenfield with no surrounding system. Then return
`{skipped: "greenfield"}`.
