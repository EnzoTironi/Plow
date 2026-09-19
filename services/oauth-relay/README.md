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

No access tokens, refresh tokens or PKCE verifier belong here. Request logging and
Workers observability are disabled; don't enable them when investigating production
OAuth callbacks. Reads and repeated identical callbacks are retryable; conflicting
callbacks and callbacks after consumption are refused. Platform storage deletion
is not a promise of cryptographic erasure from Cloudflare backups.

Anonymous registration is limited to 20 requests per IP per minute per Cloudflare
location, with bounded request bodies. This is not a global billing quota. A
dedicated stable domain and operational monitoring that records only aggregate
counts/statuses are appropriate before a wider launch.

See [the connector integration and validation notes](../../docs/CONNECTORS.md).
