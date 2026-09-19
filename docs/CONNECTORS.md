# Connectors on Plow: runtime validation

Current Google implementation: [independent Zoen OAuth and verification gates](GOOGLE_AUTH.md).
The first sections below preserve the original infrastructure audit; later sections
record the implemented native MCP flow. Google no longer routes through Plow in
this branch, and remains disabled until its own setup/review is complete.

Validated on 2026-09-19 against the existing `zoen:personal-agent` image, code
revision `1c9cdfb300db0424209d2fb6a7b3686507a7faa7`. The installed runtime is
Hermes 0.21.2 with MCP SDK 2.0.0. Tests used separate, disposable Docker containers
with temporary homes, not the running iMessage agent's credentials or home.

The native Hermes MCP client is the implementation to reuse. Zoen needs a small
iMessage connection flow and, for browser OAuth, a callback relay operated by us.
The user requires configuration through this repository without changes to Plow's
hosting infrastructure. Instances will retrieve callbacks using outbound HTTPS;
they will not need a public listener or host administration. Hermes already supplies
discovery, authorization, token storage, refresh and tool dispatch. The relay and
iMessage adapter are proposed work, not implemented features.

## Three different connection paths

| Path | What it provides | What this deployment still needs |
| --- | --- | --- |
| Plow integrations | Existing Google/Slack lifecycle and Plow/Latch tools | The local agent's status calls returned 403 for missing `gmail:status` and `slack:status`. Account state remains unknown. |
| Native Hermes MCP | Vendor HTTP servers or locally installed stdio servers | A configured server, its required authorization, and an iMessage setup adapter. Public servers can work immediately. |
| Nous-managed connectors | Nous account connections, discovery and remote tools; messaging receives a `connect_url` | A Nous identity with the applicable connector entitlement. The installed runtime reports `connectors_available() == False`. |

The Plow bearer does not authorize Nous or third-party MCP services. The installed
Nous client reads its own identity separately from inference configuration; using
Plow for Luna does not itself provide that identity. The availability code includes
guest/free identity handling, so a paid subscription is not established as a universal
requirement. Actual eligibility must come from Nous. Each user's deployment would
need its own authorized identity, rather than the operator's shared account.

In this installed version, `manage_connections` handles Nous-managed connections;
`setup_mcp` belongs to the desktop toolset and requires its UI callback. The latest
online documentation describes a unified tool, but still says messaging cannot run
its MCP setup card. Neither version makes an iMessage OAuth flow automatic.
See the [Hermes connections reference](https://hermes-agent.nousresearch.com/docs/reference/tools-reference#connections-toolset).

The installed catalog has 65 entries: 54 declare OAuth, ten require no account,
and one uses an API key. Relevant OAuth candidates include Notion, Todoist, Dropbox,
Calendly, Canva, Strava, Airtable, Asana, ClickUp, Monday, Miro, Craft, Figma, Linear,
GitLab, Atlassian, Vercel and Supabase. These are catalog declarations, not completed
account-login tests. GitHub CLI and Microsoft Graph authorization are additional
integration paths; they are not implied by this catalog or by Microsoft Learn MCP.

## What actually passed

| Probe | Result and boundary |
| --- | --- |
| Public Microsoft Learn MCP | Native connection, tool discovery and a real `microsoft_docs_search` call passed. This searches documentation; it does not connect Outlook or a Microsoft account. |
| Native registry integration | `discover_mcp_tools()` produced `mcp__microsoft_learn__microsoft_docs_search`; `registry.get_definitions()` exposed it and `registry.dispatch()` completed the real read. No model inference was used in this probe. |
| Tool filtering | `tools.include: [microsoft_docs_search]` exposed exactly one tool, excluding the other two advertised tools. |
| DeepWiki MCP | Native connection and discovery of its three tools passed. No DeepWiki tool execution was tested. |
| Plow boot reconciliation | The actual image's `plow-init.configure()` ran twice against a temporary seeded configuration and preserved an extra MCP entry. This tests configuration reconciliation, not a hosted VM restart. |
| Native credential storage | A synthetic token reopened from the same home, was absent in another home, and was stored with mode 0600. No real token refresh or account isolation boundary was exercised. |
| Native headless OAuth bridge | The installed bridge published an authorization URL and delivered a synthetic callback through native handlers, rejecting wrong state and duplicate delivery. No browser, provider consent or network was involved. |

The network probes used the endpoints from the image's own catalog:
`https://learn.microsoft.com/api/mcp` and `https://mcp.deepwiki.com/mcp`.
The registry probe used the real Hermes configuration loader, MCP client, schema
registration and execution handler, without a replacement connector implementation.

## OAuth from a phone

The normal native callback is `http://127.0.0.1:27890/callback`. On the user's phone,
that address refers to the phone, not the agent's cloud machine. Sending the initial
authorization link alone does not solve the return trip.

Hermes already supports a configured HTTPS `oauth.redirect_uri`, device-code login
when the provider advertises it, and a callback bridge that can be reused by another
surface. In this image, `tools/mcp_dashboard_oauth.py` provides
`DashboardOAuthFlow`: publish the authorization URL, await authorization, deliver a
validated callback, and track completion. `tools/mcp_oauth.py` integrates that object
with its native redirect and callback handlers. With this bridge active, Hermes
does not reserve a loopback callback port.

The bridge's name does not require deploying the dashboard: it is a Python object
whose integration with the native handlers passed the synthetic probe. Wiring it
to iMessage and an HTTPS callback endpoint is proposed work, not a completed login.
These are internal Hermes interfaces, so image upgrades need an integration test.

Read-only checks of the providers' public authorization metadata found:

| Catalog service | Device login evidence | Implication for this proposal |
| --- | --- | --- |
| Notion | No device authorization endpoint advertised | Use its browser authorization flow with a reachable callback. |
| Todoist | Authorization-code and refresh grants; no device endpoint | Same browser flow. |
| Linear | No device authorization endpoint advertised | Same browser flow. |
| Dropbox | Advertises `device_code`, but no device endpoint | Insufficient metadata for native device login; do not promise it. |
| Vercel | Advertises the standard device grant, device endpoint and registration endpoint; the installed Hermes `_discover()` accepted them in a disposable container | A candidate for a native device-flow pilot. Client registration, consent and authenticated tool execution remain untested. |

Todoist and Dropbox returned the protected-resource metadata location in their
unauthenticated MCP response. Their authorization-server metadata was then read
from [Todoist](https://todoist.com/.well-known/oauth-authorization-server) and
[Dropbox](https://www.dropbox.com/.well-known/oauth-authorization-server).
The equivalent public metadata was inspected for
[Notion](https://mcp.notion.com/.well-known/oauth-authorization-server) and
[Linear](https://mcp.linear.app/.well-known/oauth-authorization-server).
No OAuth client was registered and no consent was requested. Advertised registration
support does not prove that a provider will accept our eventual callback URL.

Vercel's MCP challenge points to its protected-resource metadata, which selects
[Vercel's authorization server](https://vercel.com/.well-known/oauth-authorization-server).
The successful native device discovery was read-only and started no login.

Device-code support alone does not guarantee a working connector. The installed
Hermes device path also requires discoverable metadata, a usable registered client
(or accepted dynamic registration), compatible token responses, and access to the
requested resource. The provider must permit the grant and scopes for that account.
[GitHub requires enabling device flow for the app](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps#device-flow).
[Microsoft supports it](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-device-code),
but [organization policies can block it](https://learn.microsoft.com/en-us/entra/identity/conditional-access/concept-authentication-flows).
[Google limits device-flow scopes](https://developers.google.com/identity/protocols/oauth2/limited-input-device#allowedscopes)
to identity, selected Drive access and YouTube; Gmail and Calendar are not on that
list. A provider's CLI supporting device login also does not prove that its MCP
accepts the same token.

The [native MCP guide](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp)
documents the supported remote-login options. Its optional remote OAuth skill is a
manual fallback involving token-file handling; it is not an automatic iMessage login
service. The native callback bridge is the better implementation boundary here.

## Hosting without changes to Plow infrastructure

Plow boots the same OCI image through `/init` locally in Docker and remotely in an
exe.dev microVM. The repository already persists `/var/lib/hermes` as `HERMES_HOME`.
Native MCP configuration and token files belong in that home, not in the image.
See the [Plow base image's infrastructure contract](https://github.com/plow-pbc/plow-hermes-agent).

Remote MCP calls are outbound HTTPS. They do not need a Plow connector endpoint or
an inbound port. The successful local image tests establish runtime compatibility;
the hosted VM's egress and DNS still need a live check.

Browser OAuth needs a stable HTTPS callback, but that address can belong to a
separate service we operate. The agent can retrieve the result over outbound HTTPS
on port 443. The provisioned
`PLOW_API_BASE=https://plow-<agent_uid>.int.exe.xyz` is an outbound integration proxy
that injects Plow authorization. It has no role in our callback transport.

The implemented service is a Cloudflare Worker with a short-lived Durable Object per
pending login. Source, local tests and deployment configuration are in
[`services/oauth-relay`](../services/oauth-relay/). The current deployment is
`https://zoen-oauth-relay.agenttironi.workers.dev`, with `/callback` as the stable
redirect URI and `/health` as its public health check.
A [workers.dev endpoint](https://developers.cloudflare.com/workers/configuration/routing/workers-dev/)
is sufficient for an initial test if the provider accepts it; production should use
a stable dedicated domain controlled by us. This requires our Cloudflare deployment,
not a website account or infrastructure access from each Zoen user.

The callback URI remains stable across users and sessions. After Hermes creates its
authorization URL, the adapter registers the opaque OAuth state and a separate
unguessable retrieval secret with the relay before sending the URL through iMessage.
The callback is correlated to that pending state. Only the initiating agent can
retrieve and acknowledge the result using its retrieval secret; knowing the state
from the browser URL does not authorize retrieval.

The relay temporarily holds the authorization code, state, issuer and error fields.
It preserves those fields for native OAuth validation, does not log requests, and
expires abandoned flows after five minutes. Hermes retains the PKCE verifier and performs token exchange
directly with the provider. Access tokens, refresh tokens and OAuth client secrets
remain in the instance's native storage. The relay does not act as an OAuth provider
or credential vault, and the public image contains no shared relay administration
secret or Cloudflare API token.

[Durable Objects provide transactional, strongly consistent storage](https://developers.cloudflare.com/durable-objects/best-practices/access-durable-objects-storage/)
for callback delivery, acknowledgement and expiry checks. Reads are retryable until
acknowledged so a lost HTTP response cannot discard the only callback. Duplicate
identical callbacks are idempotent; conflicting callbacks are refused. Creation is
limited to 20 requests per IP per minute per Cloudflare location. Registration
bodies and callback queries are size-limited. This is an abuse limit, not a global
quota, and shared IPs can hit it. Worker observability is disabled. Storage expiry
and deletion do not promise erasure from Cloudflare's underlying backups.

The agent image contains the relay client and its public base URL. Existing
instances still need our normal image update path, but no Plow firewall, public port,
DNS, SSH or provisioning changes are part of this design. Outbound reachability to
the chosen relay and a full hosted login remain to be tested. Providers requiring
a pre-registered OAuth application also need client configuration in their own
console; a relay does not remove that requirement.

## Implemented iMessage experience

1. The owner asks to connect a service or requests a task that needs it.
2. Zoen chooses a catalog entry and explains the requested access in the private chat.
3. A background operation starts native authorization and sends its link through
   iMessage. The user approves on the provider's page in their phone browser.
4. The public callback reaches our relay; the agent retrieves it over outbound
   HTTPS and delivers it to Hermes. The iMessage adapter currently supports browser
   OAuth. Native device login still prints its verification code to the terminal;
   delivering that code in iMessage is a separate integration, not implemented here.
5. Zoen reloads tools, verifies the account and a small real read, and resumes the
   saved task in the same conversation.

No separate Zoen website or user dashboard is needed. `zoen_connections` provides
`catalog` (with an optional search query), `connect`, `status` and `cancel` in the
owner's private chat. The catalog shows native entries, Zoen additions and existing
Plow connections. Remote HTTPS OAuth and public services with no installer or
required environment setup can be activated. Operator/local entries are listed
with their limitations. Arbitrary URLs and conflicting existing configurations fail
closed. Catalog presence is not a provider compatibility guarantee. The complete
[integration inventory](INTEGRATIONS.md) records the service-by-service evidence.

Public services are probed before their configuration is saved, then registered
through native discovery and announced through the same guarded event queue. They
do not create a personal-account login. Treg's official catalog MCP is a native
manifest addition; its five selected tools expose the external API catalog without
installing its CLI or transferring local credentials. Paid calls require a budget
authorized for the owner's task, even when the operation only reads data.

Login runs in a background task. Its link and completion return through Plow's
normal event queue with a freshly checked owner-only DM. The model writes the
iMessage text in Zoen's voice. No fixed status sentence or alternate send path was
added. The plugin registers just the selected connector; the native between-turn
tool refresh updates the cached agent without resetting the conversation. Existing
live connections are reconnected after a successful reauthorization.

Each native OAuth attempt runs in a private temporary Hermes home. Only after native
authorization and tool discovery succeed are native credential files atomically
written to the real home and its configuration saved. A failed or cancelled login
leaves the original connection untouched. This addresses a pinned-runtime rollback
issue: `restore(only_if_absent=True)` skips restoration when new client metadata
exists, even if the original access token has already been removed. A concurrent
change to the original credential files causes the staged commit to fail closed.
Pending logins must be started again after a gateway restart. Saved credentials
persist in the existing volume. Cancel is not a provider-side revocation operation.

The pinned Hermes dashboard also extends only its outer OAuth timeout, while the
MCP transport's `initialize()` still times out after 60 seconds. Real local Todoist
and Notion attempts hit that timeout while consent was in progress. The staged
authorization now gives that inner handshake 330 seconds, covering the relay's
five-minute consent window. The saved connector retains its normal connection
timeout. Status advances from consent to code exchange and verification; a generic
failure no longer suggests a provider configuration problem without evidence.

Keep authorization off the reception path so it cannot hold typing, reactions or
status lines. Add only the selected user's connectors and relevant tools. Native
tool filters and lazy connection/schema caching can limit startup work, but their
effect on Zoen's message latency has not been benchmarked. A cached token's 0600
permissions do not isolate it from the agent process that owns it; the existing
broad execution permissions remain a separate limitation.

Todoist and Notion are the initial personal-service candidates for native MCP,
our callback relay and this iMessage adapter. Slack remains on Plow; Google now
uses the independent implementation described in [Google auth](GOOGLE_AUTH.md). Evaluate Nous-managed
connections if a per-user identity is eligible: that path may remove the need to
host callbacks for the services it covers.

Before calling this ready for users, one hosted instance must complete phone consent,
a real account read, token reuse after restart and reconnection after revocation.
Local tests do not establish hosted Plow egress. Real account consent has been
validated only for the providers recorded below.

## Operator setup (no Plow infrastructure changes)

The shipped image uses the public relay URL in `runtime/config.yaml` under
`zoen.oauth_relay_url`. Users only ask Zoen to connect a service and authorize on the
provider's page. They do not need Cloudflare accounts or new Plow configuration.

To operate a separate relay, deploy from your own Cloudflare account:

```sh
cd services/oauth-relay
npm ci
npm test
npx wrangler login
npm run deploy
```

Use a distinct Worker name when sharing an account. Update `zoen.oauth_relay_url`
in the image, or set `ZOEN_OAUTH_RELAY_URL` in an operator-controlled runtime. Do not
put Cloudflare credentials in the agent image or share them with users. Preserve
the `agent-home` volume when updating the local agent; do not use `down -v`.

Providers allowing dynamic client registration need no separately provisioned
client secret. Where a provider requires a pre-registered client, use Hermes'
existing `mcp_servers.<name>.oauth` configuration and register the exact stable
`<relay>/callback` URI with that provider. Existing native tool filters and OAuth
options are preserved. Secret environment references are resolved in the owner's
scope before staging; the real configuration retains the references. Never commit
client secrets to this public repository. This relay does not supply provider app
approval or a way to distribute confidential client secrets to Plow instances.

## Reproducible validation

`npm test` in `services/oauth-relay` exercises the real local Workers runtime:
flow isolation, authenticated polling, wrong/duplicate state, idempotent callbacks,
conflicting replay, acknowledgement, cancellation, denial, bounds and expiration.
It also checks that branded callback pages never reflect authorization parameters
and load only bundled assets. Desktop and 390px mobile layouts were inspected.

The image integration exercises the deployed relay and the real pinned Hermes/MCP
SDK against a loopback OAuth/MCP fixture. It uses no real account credentials:

```sh
docker run --rm --platform linux/amd64 \
  --entrypoint /opt/hermes/.venv/bin/python \
  -e ZOEN_OAUTH_RELAY_URL=https://zoen-oauth-relay.agenttironi.workers.dev \
  -v "$PWD:/workspace:ro" zoen:connectors /workspace/tests/integration_oauth.py
```

The companion `tests/integration_image.py` checks the real plugin registration,
catalog routing, rejection of arbitrary URLs, fresh owner-DM permission checks and
Plow event delivery through the native processing lifecycle, alongside the existing
reception and duplicate-message checks. It also exercises public-service activation
through a native MCP fixture, rejects empty tool lists before saving configuration,
and checks the Treg manifest's selected tools. The OAuth fixture delays consent past its
one-second normal handshake timeout, checks PKCE and issuer validation, invokes a
native read tool, and renews an expired token in a fresh process. Denial, cancellation
and issuer mismatch preserve any previously connected credentials.

On 2026-09-19, the local suite passed 126 Python tests, five Worker tests and both
image integrations. The branded Worker was deployed, and the corrected image was
installed in the local iMessage test container with the persistent home preserved.
After that fix, real Notion consent completed from the iMessage link. The running
agent loaded 49 native Notion tools, verified the owner's identity through
`notion_get_users`, and confirmed the connection in the same conversation. A fresh
Python process reused the persisted token and read the same account without a new
login; the same read passed again after the expanded-catalog container update.
One initial page-list read failed because the model supplied an empty cursor;
the agent recovered with the identity read. No Notion writes were made. Todoist
consent after the fix and hosted Plow rollout remain unvalidated.

Treg also completed real consent from iMessage. The agent read `balance` and
`catalog_search`, then confirmed the connection through `plow_send_sequence`.
A fresh process reused the token, verified the same identity/team and retrieved
three catalog matches for `web search`. The agent's initial verification query
matched no endpoints; the account read still succeeded. No `catalog_call_read` or
`catalog_call_write` was invoked, and no provider calls were purchased.
