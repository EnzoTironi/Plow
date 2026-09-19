# Zoen runtime

All interaction starts and returns to iMessage. The separate reference website is
not a runtime dependency. The existing voice, humor, casing and rhythm are retained.

## Reception

The Plow adapter still owns message acceptance, grouping, replay checkpoints and
execution. A Zoen observer starts typing and acknowledges accepted owner-DM input
after two seconds of silence. Continuous input is one burst. The target is a
status line within five seconds of the last message, including transport time.

This path does not await downloads, the main model, memory retrieval or a previous
task. It refreshes the recipient's membership (0.5 second budget) and bounds each
POST to 1.4 seconds. Local language detection has a 0.2-second budget and falls back
to the owner's previous language. A slow/unavailable provider can still miss the target: this is
not a demonstrated production SLA. The fast status uses the existing terse voice.
Tapbacks use the last message's explicit ID, with no reaction to ambiguous content;
thanks-only bursts get just a reaction. Commands remain with the native gateway.

`$HERMES_HOME/zoen/reception.db` records claims and outcomes. A claim written before
a send survives restart. An ambiguous send is not replayed; the actual user request
still runs. The channel prompt tells the model not to repeat the acknowledgement.
Input checkpoints are never advanced by an acknowledgement. The intro runs outside
the receive loop and no longer consumes the first real request.

Structured log events `received`, `status_accepted` and `reception` contain message
IDs, timestamps and timing, never message contents or credentials. Compare the
provider's `created_at`, local arrival and Plow's accepted send. Delivery to the
phone must be verified separately through the provider/real conversation.

## Accounts, work and memory

`zoen_connections` exposes `status` and `connect` for Google and Slack. The plugin
requires a live owner DM, refreshes membership and uses Plow's existing authority.
It creates a short-lived provider authorization link and reports account state
after consent. The CLI `connect.py` is also available to the instance operator and
for owner-authorized scheduled status checks. Neither returns bearer credentials.
The REST contracts are from [Plow's API schema](https://api.plow.co/openapi.json).

Google workspace operations still use the bundled Plow integration; some operations
depend on Latch and the owner's Mac. A connected account is not proof that all its
tools or scopes are available. This release does not supply independent Microsoft,
Notion or Drive OAuth clients. Additional MCP tools use Hermes' native catalog,
authorization and connection management, subject to each provider's setup.

Personal workflows explicitly enable and reuse native Hermes Kanban and cron. NOW.md is a summary, while
native tasks retain the original request, account, deadline, next action and result.
Software continues through the existing PR playbooks. The maintenance cron migrates
prompt, schedule and destination without deleting jobs or resetting volumes. Its
two-hour cadence is not used to implement timed reminders.

Memory search breaks ties in favor of recent facts. The context pack reads the
journal tail. `memory.py correct "old exact fact" "new fact"` and `forget "exact fact"`
update the local memory/context copies under a file lock. This does not erase chat
history, external documents or provider backups. Task/reminder changes are separate
actions that the personal workflow must verify.

The agent now includes Chromium and a pinned agent-browser, and enables the native
Hermes browser. Browser sessions are on the agent's computer; Mac cookies are not
inherited. Keep saved states private under HERMES_HOME and coordinate shared sessions.
Installation follows the [agent-browser backend documentation](https://agent-browser.dev/installation).

## Validation

From the repository:

```sh
PYTHONDONTWRITEBYTECODE=1 pytest -q -p no:cacheprovider
docker build --platform linux/amd64 -t zoen:personal-agent .
docker run --rm --user hermes --platform linux/amd64 --network none --read-only --tmpfs /tmp \
  -v "$PWD:/workspace:ro" --entrypoint /opt/hermes/.venv/bin/python \
  zoen:personal-agent -B /workspace/tests/integration_image.py
docker run --rm --user hermes --platform linux/amd64 --network none \
  -v "$PWD:/workspace:ro" --entrypoint /opt/hermes/.venv/bin/python \
  zoen:personal-agent -B /workspace/tests/browser_image.py
docker run --rm --user hermes --platform linux/amd64 --network none \
  -v "$PWD:/workspace:ro" --entrypoint /opt/hermes/.venv/bin/python \
  zoen:personal-agent -B /workspace/tests/tasks_image.py
docker run --rm --user hermes --platform linux/amd64 --network none \
  -v "$PWD:/workspace:ro" --entrypoint /opt/hermes/.venv/bin/python \
  zoen:personal-agent -B /workspace/tests/catalog_image.py
```

The image test loads the plugin installed in the image and runs the real pinned
Plow message grouping, recipient guard and handoff with a held
attachment, duplicate socket event and a loopback Plow API fixture. It checks
that acknowledgement precedes resolution and that the request is still handed off.
Connection tool tests cover owner/group admission and the schema contract, not a
real OAuth consent. The browser test navigates, snapshots and clicks a local fixture
through native Hermes tools. No real messages or external-account writes are sent.
The task test uses separate native CLI processes to recover two tasks, archive one
without changing the other, and migrate the maintenance cron without duplication.
The catalog test checks native plugin discovery and model-visible tools using the
real seeded Plow Chat configuration, including Kanban's required opt-in.

Local validation on 2026-09-19: 113 unit tests passed, as did all four image checks
above. The three-message burst was acknowledged about 2.1 seconds after its last
message against the loopback API, with its attachment still pending. This measures
the local runtime, not phone delivery or a real OAuth consent.

Ripwire's static scan is not a zero-finding result: it flags dynamic callbacks,
test-double duplication and recent churn, plus size/complexity warnings in the new
reception and memory code. These were reviewed alongside the runtime checks;
the scan itself still exits nonzero.

## Rollout

Build with `--build-arg ZOEN_REVISION=<git-commit>` and publish an immutable image tag.
Keep the previous digest. Update one instance through its existing provider's
administration, preserving HERMES_HOME and credentials. Verify its loaded plugin,
browser and a real iMessage burst, attachment, busy turn and reconnection before
updating the rest. Never use `down -v` or revoke/recreate an agent as an upgrade.

The installed plow-agents CLI creates agents but exposes no in-place image update.
Existing hosted instances need the provider's administrative update path. A
successful local build or a running old instance is not evidence of a deployed fix.

For an isolated phone test, the [official Plow CLI](https://github.com/plow-pbc/plow-agents)
supports `plow-agents deploy --local --line <free-test-line>` with this repository's
Compose file. This creates a new agent and credentials for that line. For a cloud
test, push the candidate image with `plow-agents image push <candidate-tag>`, then
use its printed immutable digest in `plow-agents deploy <image@sha256:…> --line
<free-test-line>`. Neither command upgrades an existing agent. Keep test credentials
out of Git/build contexts and never select an occupied line for this test.

The existing broad Hermes execution configuration is unchanged. Plow's account and
turn authority protects its tools, but this release does not introduce the separate
credential broker or granular executor policy discussed in the architectural plan.
Those are further security work, not properties guaranteed by prompting.
