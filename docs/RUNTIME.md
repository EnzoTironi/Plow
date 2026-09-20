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
default, with reasoning disabled). The model selects both a contextual line and
an appropriate tapback, using the previous six inbound messages for context.
Generation is bounded to 3.2 seconds; POST timeouts use the remainder of the
five-second budget measured from the last received message. Superseded drafts
are cancelled. There is no fixed phrase or keyword-selected reaction.
If generation fails, reception does not invent an acknowledgement. The main turn
runs independently and delivers its result. Reception never holds the handoff;
a fast final answer suppresses an opening that has not yet been posted.
The budget cannot guarantee Plow transport or phone delivery within five seconds.
Generation and delivery share the burst's HTTP session to avoid an extra TLS setup.
Tapbacks use the last message's explicit ID, with no reaction to ambiguous content;
thanks-only bursts get just a reaction. Commands remain with the native gateway.

`$HERMES_HOME/zoen/reception.db` records separate claims and outcomes for the line
and the reaction. Existing records migrate as uncertain, preventing replay.
A claim written before a send survives restart. An ambiguous effect is not
replayed; the actual user request still runs. The channel prompt reports both
outcomes and tells the model not to repeat reception.
Input checkpoints are never advanced by an acknowledgement. The intro runs outside
the receive loop and no longer consumes the first real request. Synthetic Plow
setup events cannot trigger a competing intro or perform synchronous network I/O.

Normal final text and media use Plow's native delivery, authorization and duplicate
guards. `plow_send_sequence` accepts `purpose: progress` for updates that must not
complete the answer, and `purpose: answer` (the default) for a delivered final.
The Zoen persona, skill and Plow channel instruction use the same contract.
Internal connector events do not trigger another opening. Their handoff checks
admission and retries a rejected queue admission before reporting a failure.

Structured log events `received`, `status_accepted`, `reaction_accepted`,
`receipt_result` and `reception` contain message
IDs, timestamps and timing, never message contents or credentials. Compare the
provider's `created_at`, local arrival and Plow's accepted send. Delivery to the
phone must be verified separately through the provider/real conversation.

## Accounts, work and memory

On first contact, `zoen_owner_profile` checks whether the owner already has a
name. If not, it reserves one optional question about what to call them. A name
already supplied in the conversation or memory skips the question. The chosen
name is remembered and saved to the owner's Plow profile automatically, without
a second confirmation. A fresh read must match before the tool reports success.
A skipped question or failed save does not block the task or restart onboarding.
The name state persists under `$HERMES_HOME/zoen/owner-profile.sqlite3`.

Agent Index resolves the user's public name from Plow's owner profile; changing
chat memory alone is insufficient. The agent page's `AGENT_NAME` is still Zoen,
and each installation keeps its existing `install_id`. Onboarding does not
register another install or change token reporting. Native Plow contact naming
and passive capture remain unchanged.

`zoen_connections` requires a current private owner DM. Google now uses Zoen's
independent OAuth broker and the bundled Hermes API commands through
`google_workspace.py`; it does not use Plow's Google connection or the owner's Mac.
Its configured beta is External / In production, with Google's unverified-app
notice and user cap. Permissions are requested for the current task and still
require the owner's consent. See [Google auth](GOOGLE_AUTH.md) for live setup
evidence and the remaining real-account and verification checks.

Repeated Google connect requests verify and reuse a saved grant when its scopes
cover the requested capabilities. The Worker publishes the canonical scope map.
Additional scopes, revoked access or an explicit account switch may need consent;
a transient network failure does not start another login. Account state and the
latest authorization attempt are separate fields.

The delivery repair passed 148 Python tests and 16 Worker tests. Image integration
uses the pinned Hermes/Plow adapter and actual HTTP sends to loopback fixtures:
ordinary final text reaches the transport, progress leaves the final deliverable,
and a delivered answer sequence suppresses duplicate prose. Rejected connection
queue admission is retried. Google integration verifies saved-grant reuse without
creating a consent flow and preserves account status after a failed attempt.
Reception reached the fixture transport about 2.04 seconds after the burst; this
is a controlled measurement, not a real-phone delivery guarantee.

Worker version `73006773-131e-4d2e-a112-8f4f5d9b318b` publishes the canonical scope
map. The built agent image successfully fetched all 12 capabilities from the live
endpoint using its actual HTTP client. App secrets and the encryption key were
preserved. Applying the agent repair to the existing Aspen instance still needs
an in-place operator update: the public Plow CLI/API has no image-update operation
and the available SSH identity was rejected. Do not recreate that instance to
work around deployment access; it contains the owner's saved Google grant.

Slack retains Plow's existing connection lifecycle. Its local status call returned
403 for missing `slack:status` on 2026-09-19, so account state remains unknown. The
legacy Google path also returned 403 before it was replaced. Those errors were
permissions failures, not evidence of disconnected user accounts. The operator
CLI `connect.py` retains the legacy Plow interface for older installations; the
current agent routes Google exclusively to Zoen OAuth.

Other MCP services use Hermes' native catalog, authorization and token storage
through Zoen's HTTPS callback relay. Real Notion consent, identity verification and
token reuse in a fresh process have passed locally. Provider-specific setup and
availability still apply. Never equate cached credentials with a verified live read.

The [connector infrastructure validation](CONNECTORS.md) records native MCP execution
tests, the distinction from Nous-managed accounts, the deployed callback relay,
and the remaining hosted-instance validation.
The [integration inventory](INTEGRATIONS.md) lists available OAuth/public services,
the Treg catalog connection, and entries requiring separate operator setup.

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
disables reasoning. The vision auxiliary remains Sonnet. The main agent also has
a native Hermes fallback to Sonnet through the same Plow provider when Luna is
unavailable. This uses Sonnet's rates when activated. Live Treg validation exposed
temporary upstream Luna rate limits; a streamed Sonnet response through Plow was
verified before enabling the fallback. This cannot bypass an outage of Plow itself,
and the reception call still uses Luna.

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

A final check on code revision `1c9cdfb` also failed the latency target: Plow dated
the incoming message 19:47:23.112Z, while the reception observer saw it at
19:48:14.241Z (51.129s later). The native chat `_on_message` enqueue has no blocking
await before the observer; the delay precedes this custom reception path, but its
precise source was not instrumented. Reception generation then hit its six-second
timeout. The main request logged HTTP 504 from `api.plow.co/v1` and completed after
139s of main-turn time. Authenticated message reads also timed out intermittently.
The recovered turn called both connection status tools, received non-retryable
403s, and explained that access was refused without suggesting another retry or
starting login. This establishes error handling, not reliable provider latency.

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

On September 19, the owner-authorized Aspen test instance was retired and replaced
with a fresh cloud test instance, `19bcc834cb649a94cd900139e5234619`, on `ln_p2`.
It runs public image
`ghcr.io/enzotironi/zoen/all-in-one@sha256:d45804c773cb1fecb87ce04995e097edd63935013418e4f102c9ef96bc0b1c0a`
(code `50336eefdea5082aa9c0561f98915bb41fc59c85`). The Plow API reports `running`,
no failure code and a connected credential. A real iMessage request reached it
and received one introduction and contact card, followed by the independent
Google authorization link and unverified-beta notice. After the Worker token
exchange fix, real consent completed and the agent confirmed saved credentials,
identity verification, refresh in a fresh process and a minimal Calendar read.
Results were delivered with an explicit `plow_send_sequence` request; normal
Hermes output was dropped by that image's quiet filter. The follow-up repair
restores native final delivery and adds regression coverage. See
[Google auth](GOOGLE_AUTH.md) for the scope and limitations of this live test.
This was a fresh test deployment,
not an upgrade preserving the previous instance's memory. The other occupied
lines were not changed. The default Agent Index image remains pinned separately
in Plow's private registry and still needs its administrative update path.

The existing broad Hermes execution configuration is unchanged. Plow's account and
turn authority protects its tools. The Google OAuth broker keeps that app's secret
outside the image; a general credential broker and granular executor policy for
all tools remain further security work, not properties guaranteed by prompting.
