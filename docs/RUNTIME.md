# Zoen runtime

All interaction starts and returns to iMessage. The separate reference website is
not a runtime dependency. The existing voice, humor, casing and rhythm are retained.

## Reception

The Plow adapter still owns message acceptance, grouping, replay checkpoints and
execution. A Zoen observer starts typing and acknowledges accepted owner-DM input
after two seconds of silence. Continuous input is one burst. The target is a
status line within five seconds of the last message, including transport time.

This path does not await downloads, the main model, memory retrieval or a previous
task. It refreshes the recipient's membership during the burst's quiet window,
restarting that read on each new message. Reads and POSTs each have a three-second
timeout. During the same window, a short model call writes a contextual opening
using the existing persona, the owner's voice preferences, the whole burst and
the last three openings. `zoen.reception_model` selects that model (Luna by
default, with reasoning disabled for this short opening). A generation can take up to six seconds;
superseded drafts are cancelled. There is no fixed phrase or template rotation.
If generation fails, only the reaction is attempted and the main turn writes its
own opening. Reactions do not wait for generation. A slow/unavailable provider can
still miss the five-second target: this is not a demonstrated production SLA.
Generation and delivery share the burst's HTTP session to avoid an extra TLS setup.
Tapbacks use the last message's explicit ID, with no reaction to ambiguous content;
thanks-only bursts get just a reaction. Commands remain with the native gateway.

`$HERMES_HOME/zoen/reception.db` records claims and outcomes. A claim written before
a send survives restart. An ambiguous send is not replayed; the actual user request
still runs. The channel prompt tells the model not to repeat the acknowledgement.
Input checkpoints are never advanced by an acknowledgement. The intro runs outside
the receive loop and no longer consumes the first real request. Synthetic Plow
setup events cannot trigger a competing intro or perform synchronous network I/O.

Structured log events `received`, `status_accepted`, `reaction_accepted`,
`receipt_result` and `reception` contain message
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

The real local agent's credential returned HTTP 403 for both status endpoints on
2026-09-19: missing `gmail:status` and `slack:status` access. That is unknown account
state, not a disconnected account. The tool marks 401/403 as non-retryable and
explains that the instance operator must fix Plow connector access. It must not
start OAuth or recommend waiting as a solution to this permission error. No real
OAuth consent or connected-account operation has been validated yet.

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

Initial validation on 2026-09-19: 113 unit tests passed, as did all four image checks
above. Follow-up reception fixes pass 126 unit tests and the image integration and
catalog checks. The loopback API now includes
an 800ms membership read and a model endpoint; it verifies a single contextual
opening and last-message reaction while an attachment remains pending.

Real iMessage tests used an isolated local agent on the Aspen test line, preserving
its volume across rebuilds. They exposed a setup/first-inbound race that sent two
copies of the introduction and contact card, and a 500ms permission timeout shorter
than real Plow reads (0.96–2.49s). The setup handler can no longer send an intro;
regression tests verify that it performs no network calls and the first real
request remains intact. Fresh first-contact delivery has not been retested on a
second empty volume. Warm requests, a three-message burst and a thanks-only reply
were verified through the Plow API and the actual Messages conversation.

Luna with reasoning disabled generated two short openings in 1.93s and 2.04s;
Sonnet generated the same workloads in 1.83s and 2.27s. This small sample supports
similar speed, not a claim that Luna is always faster. The
[OpenRouter model catalog](https://openrouter.ai/api/v1/models) listed Luna at
$0.20/M input and $1.20/M output tokens, versus Sonnet at $2/M and $10/M, for the
short-context pricing tier on 2026-09-19. These are catalog rates, not a guarantee
of Plow billing. Luna is the main and reception default; only reception explicitly
disables reasoning. The vision auxiliary remains Sonnet.

With Luna and a reused HTTP session, live measurements were:

| Request | Generation | Last Messages send → Plow accepted status | Result |
| --- | ---: | ---: | --- |
| Desk routine, one message | 3.67s | 6.303s | Contextual status and reaction delivered; missed target |
| Google/Slack status, three-message burst | 2.45s | 4.152s | One contextual status and reaction on the last message |

The connector opening was “vou conferir o estado das conexões do Google e do Slack,
sem iniciar login”, visible in Messages. These are send-to-accept measurements;
the exact arrival time on the phone was not instrumented. The first-ever cold
message also waited about 34 seconds for the upstream `plow-init` home-chat startup
path before reaching the adapter. The five-second end-to-end target is therefore
not consistently met, especially on cold startup or delayed provider transport.

Ripwire's static scan is not a zero-finding result: it flags dynamic callbacks,
test-double duplication and recent churn, plus size/complexity warnings in the new
reception, connector error handling and memory code. These were reviewed alongside the runtime checks;
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
