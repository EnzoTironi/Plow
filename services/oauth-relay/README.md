# Zoen OAuth callback relay

This Worker transports a short-lived authorization callback from the owner's phone
to the agent's outbound HTTPS connection. Hermes handles PKCE, provider tokens and
refresh. No Cloudflare credential is distributed with the agent image.

```sh
npm ci
npm test
npx wrangler login
npm run deploy
```

Set `zoen.oauth_relay_url` in `runtime/config.yaml` to the deployed base URL, then
build the agent. The provider's redirect URI is always `<base>/callback`. Existing
Plow instances need an image update, with their persistent home kept intact.

The default Worker name is `zoen-oauth-relay`; choose a different name for an
independent installation in the same Cloudflare account. Local development uses
`npm run dev` and `http://127.0.0.1:8791`. Tests use the real local Workers runtime
and an isolated temporary storage directory; they never contact a provider account.

The callback pages use the Zoen landing page's sky and avatar, bundled under
`public/` from `zoen.tironi.xyz/marketing/`. CSS and images are served from the
relay's own origin, with no scripts, analytics, external fonts or referrers.
`GET /` provides a neutral preview; callback success means the return was received,
not that Hermes has verified account access. Denial, expiry, replay and malformed
callbacks have their own page while retaining their protocol status codes.

## Protocol

| Request | Behavior |
| --- | --- |
| `POST /flows` | Register native OAuth `state` and an independent random `poll_token`. |
| `GET /callback` | Accept `state`, `code` or `error`, and optional `iss` from the provider. |
| `GET /flows/<sha256(state)>` | Authenticated polling; callback is retryable until acknowledged. |
| `POST /flows/<id>/ack` | Authenticated acknowledgement; remove callback and keep a consumed tombstone. |
| `DELETE /flows/<id>` | Authenticated cancellation; refuse subsequent callback delivery. |
| `GET /health` | Public liveness and protocol version. |

Polling, acknowledgement and cancellation use `Authorization: Bearer <poll_token>`.
The browser never sees that token. The agent registers state before disclosing its
authorization link. Random values require at least 256 bits of entropy. State is
the native SDK's responsibility; the adapter creates the independent poll token.
Only its hash is stored. Expiration is five minutes, checked on every request and
backed by a Durable Object alarm. There is no shared relay administrator key.

The native MCP callback transport never receives provider tokens or the PKCE
verifier. The optional Google broker below has a different credential boundary.
Request logging and
Workers observability are disabled; don't enable them when investigating production
OAuth callbacks. Reads and repeated identical callbacks are retryable; conflicting
callbacks and callbacks after consumption are refused. Platform storage deletion
is not a promise of cryptographic erasure from Cloudflare backups.

Anonymous registration is limited to 20 requests per IP per minute per Cloudflare
location, with bounded request bodies. This is not a global billing quota. A
dedicated stable domain and operational monitoring that records only aggregate
counts/statuses are appropriate before a wider launch.

See [the connector integration and validation notes](../../docs/CONNECTORS.md).

## Optional Google broker

Google web OAuth requires a confidential client secret. The separate
`/google/flows`, `/google/flows/<id>/exchange` and `/google/refresh` routes keep that
secret in Cloudflare, outside every public agent image. Google requires operator
secrets, an explicit audience mode, and enabled capabilities; `/google/config`
reports the actual configured state, `auth_mode`, and enabled
capabilities. Existing native MCP callbacks keep their original protocol.

Google exchange requires both the flow's poll capability and S256 verifier.
Refresh tokens are returned only inside authenticated AES-GCM handles, bound to
the OAuth client. The temporary exchange response is encrypted for retry until
acknowledgement or the five-minute expiry. The Worker does handle Google tokens
in memory during exchange/refresh; it does not fetch Google account contents.

Use [the Google setup and verification guide](../../docs/GOOGLE_AUTH.md) before
enabling any Google capability. A successful Worker deployment is not evidence
of Google verification or a working user account.

`GOOGLE_AUTH_MODE` must match Google's project audience: `testing` for enrolled
testers, `unverified` for a published beta with Google's warning and user cap, or
`verified` after the relevant scopes are approved. The flag only informs the
agent; it cannot change Google's restrictions. The repository enables the
implemented capabilities, but each login still requests only the chosen subset.

`/privacy` and `/terms` use operator-approved static copy from `src/legal.js` and
the same bundled design as the callback. Both are published on the custom domain;
no OAuth URL parameters are included in their HTML. The separate product landing
page is not modified by this repository.

Google token requests use `redirect: "manual"` and reject all redirect responses.
Cloudflare's runtime does not accept the Fetch `error` redirect mode. The test
entry exercises request construction in workerd as well as the Node unit tests;
only `src/worker.js` is deployed.
