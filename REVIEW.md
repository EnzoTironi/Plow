# Review instructions: Zoen

Repo-specific reviewer policy. The README owns the product prose and the
variant contract; this file does not repeat them. Flag drift between that prose
and the code, in either direction.

## What this repo is

**One agent**: Zoen, a personal agent over iMessage (and WhatsApp through its own
relay), built as a variant of `plow-pbc/plow-hermes-agent`. It is the persona
(`runtime/persona.md`), the first-run ritual (`runtime/bootstrap.md`), the
`zoen-face` plugin, the skills, a few s6 services, and the OAuth/WhatsApp relay
in `services/oauth-relay`. Boot, identity, the Plow Chat plugin and the usage
reporter belong to the base.

**Stage:** pre-PMF, one builder, about forty installs on Plow's cloud. It reads
the owner's mail and calendar when connected, sends in their name after a yes,
and talks to people in groups. A credential, a phone number, a chat id or a real
person's data anywhere in the tracked tree is blocking, `tests/fixtures/`
included.

## Blocking checks

- **Approvals stay real.** No `HERMES_YOLO_MODE`, no sudo for `hermes`, and the
  quiet layer never drops a message the gateway marks `is_approval_prompt`.
  `approvals.mode: off` covers only commands in Zoen's own VM; re-check that on
  every Hermes bump (newer Hermes also lets it through plugin gates).
- **The base persona is inherited.** Nothing COPYs over
  `/opt/hermes/plow-seed/SOUL.md`; `image/zoen-soul.py` changes only its listed
  passages, and `tests/test_persona.py` keeps the composed identity under 16k
  characters and clean of Hermes' injection scanner.
- **Unit tests stay offline.** `tests/conftest.py` fails a test that reaches the
  network; never weaken it to make a test pass.
- **Cost scales with the fleet.** A timer, poll or retry runs on every install.
  Block one that wakes the model or calls Plow without a reason that changed
  (see `floor_monitor.py`, `_pairing_pause`).
- **Pins are the supply chain.** `FROM` carries tag and digest; downloads carry a
  version and sha256; `install.sh` fetches `plow-agents` by commit. Bumping a pin
  to a new immutable revision is ordinary work.

## Contrast pairs

| DON'T flag (by design) | DO flag (real finding) |
|---|---|
| Behavior specific to Zoen's voice: lowercase, short stacked bubbles, no periods. That is the product. | A rule restated from the base `SOUL.md` or the `plow_chat` plugin's per-turn prompt: one owner per rule. |
| `zoen_imessage` replacing `plow_send_sequence` for the model. | A prompt that names a tool no one registers (`tests/test_tool_names.py` should catch it). |
| Engineering principle skills a child reads in full. | A new always-loaded skill without a reason it earns its place in every prompt. |
| Persona text in English while replies follow the owner's language. | A user-facing doc or script message that is not English. |

**Update cadence:** edit this when the stage changes.
