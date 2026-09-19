# Integration inventory

Snapshot: 2026-09-19, Hermes 0.21.2 plus the Zoen Treg manifest.

The iMessage catalog exposes 68 entries: 55 remote OAuth services, 9 public HTTPS services, two existing Plow connections and two entries requiring operator/local setup.

Only a service selected for the owner's task is enabled. Listing a service does not install software, authorize an account or preload its tools. `zoen_connections` supports `catalog` with an optional `query`, `connect`, `status` and `cancel`.

Notion has completed real phone consent, an identity read and token reuse in a fresh process. The public services below passed native MCP handshake/tool discovery from the image; that does not validate every search or operation. Other account providers still require their own real consent and operation tests.

## Treg

The official `https://treg.to/mcp/v2/` surface uses the same native Hermes OAuth flow and our callback relay. Live preflight passed discovery, dynamic registration, S256 PKCE and the V2 resource audience. Real iMessage consent then completed: Zoen read the selected identity/team with `balance` and queried the catalog. A fresh process reused the saved token, read the same identity/team and found three catalog results for `web search`. The identity/team read also passed after the container was recreated. No provider calls were purchased.

Five Treg tools are enabled after consent: `catalog_search`, `catalog_get`, `catalog_call_read`, `catalog_call_write` and `balance`. Hermes also registers its four standard resource/prompt utilities; feedback, review and catalog-request tools were confirmed absent from discovery. The selected Treg tools expose the curated API catalog on demand. This is not automatic authorization to the owner's Gmail, Slack or other personal accounts. Verify the selected Treg identity/team with `balance` and browse the catalog before executing a provider call.

A read can cost credits. Zoen must inspect the current endpoint/overflow price and use an explicit budget for the task before paid calls. No automatic top-ups, shared operator token, local key uploads, CLI installation or imported remote skills are configured. The V2 surface also avoids arbitrary team-owned tool execution. Feedback/review/request tools are excluded by the manifest.

Sources: [Treg architecture](https://github.com/superdesigndev/treg/blob/main/docs/context/architecture/mcp-oauth.md), [Treg resource metadata](https://treg.to/.well-known/oauth-protected-resource/mcp/v2).

## Catalog

| Service | Setup | Validation in this checkout |
| --- | --- | --- |
| [airtable](https://support.airtable.com/articles/9897799762-using-the-airtable-mcp-server) | OAuth via iMessage | Catalog routing available; account not tested |
| [algolia](https://www.algolia.com/doc/guides/model-context-protocol/productivity-mcp) | OAuth via iMessage | Catalog routing available; account not tested |
| [alltrails](https://www.alltrails.com/mcp) | Public HTTPS | Live tool discovery passed (5 tools) |
| [amplitude](https://amplitude.com/docs/amplitude-ai/amplitude-mcp) | OAuth via iMessage | Catalog routing available; account not tested |
| [asana](https://developers.asana.com/docs/using-asanas-mcp-server) | OAuth via iMessage | Catalog routing available; account not tested |
| [atlassian](https://support.atlassian.com/rovo/docs/getting-started-with-the-atlassian-remote-mcp-server/) | OAuth via iMessage | Catalog routing available; account not tested |
| [attio](https://attio.com/help/apps/other-apps/using-the-attio-mcp-server) | OAuth via iMessage | Catalog routing available; account not tested |
| [aws-knowledge](https://awslabs.github.io/mcp/servers/aws-knowledge-mcp-server/) | Public HTTPS | Live tool discovery passed (5 tools) |
| [betterstack](https://betterstack.com/docs/getting-started/integrations/mcp/) | OAuth via iMessage | Catalog routing available; account not tested |
| [buildkite](https://buildkite.com/docs/apis/mcp-server) | OAuth via iMessage | Catalog routing available; account not tested |
| [calendly](https://developer.calendly.com/calendly-mcp-server) | OAuth via iMessage | Catalog routing available; account not tested |
| [canva](https://www.canva.dev/docs/mcp/) | OAuth via iMessage | Catalog routing available; account not tested |
| [circleci](https://circleci.com/docs/guides/toolkit/circleci-mcp-overview/) | OAuth via iMessage | Catalog routing available; account not tested |
| [clickup](https://developer.clickup.com/docs/connect-an-ai-assistant-to-clickups-mcp-server) | OAuth via iMessage | Catalog routing available; account not tested |
| [close](https://help.close.com/docs/mcp-server) | OAuth via iMessage | Catalog routing available; account not tested |
| [cloudflare](https://developers.cloudflare.com/agents/model-context-protocol/cloudflare/servers-for-cloudflare/) | OAuth via iMessage | Catalog routing available; account not tested |
| [cloudinary](https://cloudinary.com/documentation/cloudinary_llm_mcp) | OAuth via iMessage | Catalog routing available; account not tested |
| [comfy-cloud](https://docs.comfy.org/agent-tools/cloud) | OAuth via iMessage | Catalog routing available; account not tested |
| [context7](https://context7.com/docs/resources/all-clients) | Public HTTPS | Live tool discovery passed (2 tools) |
| [craft](https://support.craft.do/hc/en-us/articles/29455875123101) | OAuth via iMessage | Catalog routing available; account not tested |
| [datadog](https://docs.datadoghq.com/bits_ai/mcp_server/) | OAuth via iMessage | Catalog routing available; account not tested |
| [deepwiki](https://docs.devin.ai/work-with-devin/deepwiki-mcp) | Public HTTPS | Live tool discovery passed (3 tools) |
| [dropbox](https://help.dropbox.com/integrations/connect-dropbox-mcp-server) | OAuth via iMessage | Catalog routing available; account not tested |
| [figma](https://developers.figma.com/docs/figma-mcp-server/remote-server-installation/) | OAuth via iMessage | Catalog routing available; account not tested |
| [fireflies](https://docs.fireflies.ai/getting-started/mcp-configuration) | OAuth via iMessage | Catalog routing available; account not tested |
| [gamma](https://developers.gamma.app/docs/gamma-mcp-server) | OAuth via iMessage | Catalog routing available; account not tested |
| [gitlab](https://docs.gitlab.com/user/model_context_protocol/mcp_server/) | OAuth via iMessage | Catalog routing available; account not tested |
| [globalping](https://github.com/jsdelivr/globalping-mcp-server) | OAuth via iMessage | Catalog routing available; account not tested |
| google | Existing Plow connection | Local credential lacks Plow status permission; account unknown |
| [grafana](https://grafana.com/docs/grafana-cloud/ai-tools/mcp-servers/cloud-mcp/) | OAuth via iMessage | Catalog routing available; account not tested |
| [hugging_face](https://huggingface.co/docs/hub/agents-mcp) | OAuth via iMessage | Catalog routing available; account not tested |
| [indeed](https://docs.indeed.com/indeed-mcp) | OAuth via iMessage | Catalog routing available; account not tested |
| [intercom](https://developers.intercom.com/docs/guides/mcp) | OAuth via iMessage | Catalog routing available; account not tested |
| [kiwi](https://www.kiwi.com/stories/kiwi-mcp-connector/) | Public HTTPS | Live tool discovery passed (2 tools) |
| [klaviyo](https://developers.klaviyo.com/en/docs/klaviyo_mcp_server) | OAuth via iMessage | Catalog routing available; account not tested |
| [linear](https://linear.app/docs/mcp) | OAuth via iMessage | Catalog routing available; account not tested |
| [microsoft-learn](https://learn.microsoft.com/en-us/training/support/mcp-get-started) | Public HTTPS | Live tool discovery passed (3 tools) |
| [miro](https://developers.miro.com/docs/connecting-to-miro-mcp) | OAuth via iMessage | Catalog routing available; account not tested |
| [mixpanel](https://docs.mixpanel.com/docs/mcp) | OAuth via iMessage | Catalog routing available; account not tested |
| [monday](https://developer.monday.com/apps/docs/mondaycom-mcp-integration) | OAuth via iMessage | Catalog routing available; account not tested |
| [motherduck](https://motherduck.com/docs/key-tasks/ai-and-motherduck/mcp-setup/) | OAuth via iMessage | Catalog routing available; account not tested |
| [n8n](https://github.com/CyberSamuraiX/hermes-n8n-mcp) | Operator setup | Listed with limitation; not activated by the iMessage tool |
| [neon](https://neon.com/docs/ai/neon-mcp-server) | OAuth via iMessage | Catalog routing available; account not tested |
| [netlify](https://docs.netlify.com/build/build-with-ai/agent-setup-guides/agent-setup-overview/) | OAuth via iMessage | Catalog routing available; account not tested |
| [notion](https://developers.notion.com/docs/mcp) | OAuth via iMessage | Real consent, account read and fresh-process reuse passed |
| [paypal](https://developer.paypal.com/tools/mcp-server/) | OAuth via iMessage | Catalog routing available; account not tested |
| [plaid](https://plaid.com/docs/resources/mcp/) | OAuth via iMessage | Catalog routing available; account not tested |
| [postman](https://learning.postman.com/docs/reference/postman-api/postman-mcp-server/postman-mcp-remote-server/) | OAuth via iMessage | Catalog routing available; account not tested |
| [prisma-postgres](https://www.prisma.io/docs/postgres/integrations/mcp-server) | OAuth via iMessage | Catalog routing available; account not tested |
| [railway](https://docs.railway.com/guides/mcp-server) | OAuth via iMessage | Catalog routing available; account not tested |
| [robinhood](https://robinhood.com/us/en/support/articles/agentic-trading-overview/) | OAuth via iMessage | Catalog routing available; account not tested |
| [semgrep](https://semgrep.dev/docs/mcp) | OAuth via iMessage | Catalog routing available; account not tested |
| [sentry](https://docs.sentry.io/product/sentry-mcp/) | OAuth via iMessage | Catalog routing available; account not tested |
| slack | Existing Plow connection | Local credential lacks Plow status permission; account unknown |
| [square](https://developer.squareup.com/docs/mcp) | OAuth via iMessage | Catalog routing available; account not tested |
| [strava](https://support.strava.com/en-us/articles/15401531-strava-mcp-connector) | OAuth via iMessage | Catalog routing available; account not tested |
| [stripe](https://docs.stripe.com/mcp) | OAuth via iMessage | Catalog routing available; account not tested |
| [supabase](https://supabase.com/docs/guides/ai-tools/mcp) | OAuth via iMessage | Catalog routing available; account not tested |
| [todoist](https://www.todoist.com/help/articles/todoist-mcp-server) | OAuth via iMessage | Catalog routing available; account not tested |
| [treg](https://github.com/superdesigndev/treg/blob/main/docs/context/architecture/mcp-oauth.md) | OAuth via iMessage | Real consent, identity/team read, catalog query and fresh-process reuse passed; no paid calls |
| [trivago](https://mcp.trivago.com/mcp) | Public HTTPS | Live tool discovery passed (3 tools) |
| [twelve-data](https://twelvedata.com/docs) | OAuth via iMessage | Catalog routing available; account not tested |
| [twilio-docs](https://www.twilio.com/docs/ai/mcp) | Public HTTPS | Live tool discovery passed (2 tools) |
| [unreal-engine](https://dev.epicgames.com/documentation/unreal-engine/unreal-mcp-in-unreal-editor) | Local application | Listed with limitation; not activated by the iMessage tool |
| [vercel](https://vercel.com/docs/mcp) | OAuth via iMessage | Catalog routing available; account not tested |
| [webflow](https://developers.webflow.com/mcp/reference/getting-started) | OAuth via iMessage | Catalog routing available; account not tested |
| [wolfram](https://www.wolfram.com/agent-tools/) | Public HTTPS | Live tool discovery passed (3 tools) |
| [wordpress-com](https://developer.wordpress.com/docs/mcp/) | OAuth via iMessage | Catalog routing available; account not tested |

## Extending the image

The standard catalog remains owned by the pinned Hermes runtime. Zoen additions are native manifests in `image/optional-mcps/`, copied into the image's catalog without patching Hermes. Add only reviewed provider endpoints and use native tool filters; arbitrary URLs, installers and credential headers are not accepted from chat. Existing per-account OAuth options and tool filters are preserved.

Device-code-only, API-key and local application setups are not made universally compatible by an HTTPS callback relay. They need a service-specific setup path. The current phone flow supports browser OAuth plus public remote MCP; the inventory labels the unsupported setup cases.

See [runtime validation](CONNECTORS.md) for the real-account evidence, security boundaries and hosted-Plow limitations.
