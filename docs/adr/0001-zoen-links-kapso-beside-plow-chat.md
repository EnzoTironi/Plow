# Zoen links its own WhatsApp line beside plow_chat

Zoen cannot change Plow. WhatsApp stays, on Kapso, which Zoen owns. The link into Plow is the owner binding from `GET /v1/agents/me` and the Hermes turn. iMessage stays on `plow_chat`. The WhatsApp adapter does not replace that adapter's methods.

## Status

accepted

## Considered options

- Drop WhatsApp until Plow ships a provider. Rejected: the line is required, and Plow is not ours to extend.
- Inject a WhatsApp burst into the iMessage owner DM by wrapping `plow_chat`. Rejected: that pin moves without us, and a reply can fall onto iMessage.
- Make `zoen_connections` the whole variant interface. Rejected: an ordinary burst then has no line seam.
- Put a `Turn` module in front of Hermes. Rejected: Hermes already runs the turn.
- Put ports in front of the kit and the playbooks. Rejected: both are in-process, so a port there is a hypothetical seam.

## Consequences

- Two line adapters. iMessage calls the `plow_chat` send as it stands. WhatsApp is our relay plus Kapso. Sessions stay separate. Persona and memory stay shared.
- `zoen_connections` is the only connector entry: `catalog`, `status`, `connect`, `cancel`. Google is Zoen's broker. Slack is Plow's grant. Every other connector is the Hermes catalog. Tests use an in-memory adapter. Authority is the binding, which covers a WhatsApp session on the bound phone.
- The owner name is written only by `plow_name_contact`.
- Persona is `persona.md`, under the composed cap. The base persona stays.
- The kit stays. An index leads a turn from a playbook to one leaf. A playbook returns stdout and an exit code.
- The variant does not ship a config overlay. `HERMES_MODEL` and `HERMES_YOLO_MODE` are the model and approval knobs. Naming the Zoen plugin under `plugins.enabled` is the one config add. No `sitecustomize`.
- A fast opening, if it stays, is one extra send on the same line. It is not its own module.
