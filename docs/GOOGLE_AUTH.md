# Independent Google authorization

Zoen's Google connector uses our OAuth app and HTTPS Worker. No Plow Google
connector, owner Mac, inbound VM port, or change to Plow hosting is needed.
Hermes' bundled Google API command implementations are reused through
`/opt/plow/zoen/google_workspace.py`; their legacy OAuth setup is not invoked.

## Release status — September 19, 2026

The implementation and provider-simulated tests are in this branch. Real Google
account consent and warning-free public authorization have **not** been verified.
The beta configuration enables the implemented capabilities, with explicit
audience reporting. Google verification is still required to remove the warning
and lift the unverified-app cap; it is not a prerequisite for a consented beta.
The live `/google/config` response is authoritative for the deployed broker.

The dedicated **Zoen iMessage** web client was created in `zoen-506921`, with
`https://auth.zoen.tironi.xyz/callback` as its only redirect. Its client ID,
client secret and a stable encryption key are configured as Worker secrets.
The temporary downloaded credential file was removed after configuration; no
secret is included in this repository or the image. The custom hostname's
HTTPS endpoint was checked with certificate validation enabled. The Worker uses
`unverified`, matching the Google Console's External / In production state.

The existing Google Cloud project `zoen-506921` was inspected in the owner's
Console. Its public beta was published with the owner's approval on September 19.
No tester enrollment is required; the unverified-app warning, normally 100-user
lifetime cap, and Google account/admin restrictions still apply. Publication is
not verification. Branding links to the product homepage and the approved public
policies at `https://auth.zoen.tironi.xyz/privacy` and
`https://auth.zoen.tironi.xyz/terms`, with `enzo@zoen.space` as their contact.
The nine narrower Calendar, Gmail, Drive, Docs and Sheets scopes used by the agent
were added to the project's declared permissions. Existing clients and their
broader Calendar, Tasks, Contacts, Sheets, Docs, Drive and Gmail permissions were
preserved. A live broker registration for all 12 implemented capabilities checked
the client ID, exact redirect, S256 challenge and mode; the test flow was cancelled.
The fresh Aspen cloud instance runs image `release-50336ee`. A real iMessage request
received a Google authorization link for **Zoen iMessage**, returning to the custom
Zoen domain, together with the unverified-beta notice. Real-account verification
is pending a completed consent after the fix below; no Google data was read or
changed in that test.

The first cloud attempt exposed a Cloudflare runtime incompatibility: token
requests used `redirect: "error"`, which workerd rejects before contacting Google.
The deployed fix uses `manual` and explicitly rejects redirect responses, keeping
the app secret at Google's token endpoint. Permanent OAuth failures also have
allowlisted error codes rather than being reported as transient failures. Sixteen
Worker tests pass, including a token-request construction test inside workerd and
redirect-rejection coverage. After deployment, a separate synthetic-code probe
reached Google and received the expected `google_reauthorization_required` (400),
instead of the previous 503. That probe's flow was cancelled. This verifies the
transport correction, not a real account grant.

## Flow and credential boundary

1. The owner's private iMessage request selects the needed capabilities.
2. The agent creates random state, a private poll capability and S256 PKCE. It
   registers the flow with the Worker before sending the Google consent link.
3. Google returns the code to `https://auth.zoen.tironi.xyz/callback`.
4. Only the originating instance can poll and exchange it. The Worker requires
   both the poll capability and the original PKCE verifier, then sends the code,
   verifier, registered redirect and private app secret to Google's token endpoint.
5. The Worker returns an access token and an authenticated AES-GCM envelope
   containing the refresh token. Neither the app secret nor raw refresh token is
   distributed in the public image. The encryption key is also a Worker secret.
6. The agent verifies the Google identity and saves credentials atomically at mode
   `0600` in its persistent Hermes home. A denied or failed login preserves the
   previous account. Concurrent changes win over an older pending login. Adding
   permissions cannot silently replace a different connected account.
7. API requests go directly from the agent to Google. Refresh goes through the
   Worker using the opaque refresh handle. The Worker does not read Gmail, events
   or Drive contents. API outputs used in conversation enter the agent's context.

The callback flow expires after five minutes. A successful exchange response is
encrypted in the same expiring record so a lost HTTP response can be recovered
without redeeming the code twice. Acknowledgement/cancellation removes that
delivery record. AES-GCM envelopes are bound to their purpose and OAuth client.
Worker request logging/observability remain disabled. This is not a promise of
erasure from provider backups. Protect and back up the encryption key; replacing
it invalidates saved refresh handles. Google consent can be revoked from the
owner's Google Account third-party connections.

## Operator configuration

Create a separate web OAuth client, named **Zoen iMessage**, in the Zoen project.
Preserve the clients used by the other application. Register exactly:

```text
https://auth.zoen.tironi.xyz/callback
```

Do not distribute the client secret in Docker, Compose, source control, iMessage
or screenshots. Configure these through Cloudflare's secrets interface:

- `GOOGLE_CLIENT_ID`: the new web client ID.
- `GOOGLE_CLIENT_SECRET`: its private client secret.
- `GOOGLE_ENCRYPTION_KEY`: a stable, randomly generated 32-byte key encoded as
  64 lowercase hexadecimal characters.

`GOOGLE_REDIRECT_URI` is checked into the Worker configuration. The runtime's
`zoen.google_relay_url` points to the same Worker, independently of
`zoen.oauth_relay_url` used by native MCP. A private operator override is available
as `ZOEN_GOOGLE_RELAY_URL`. Cloud instances need only outbound HTTPS and their
existing persistent volume.

`GOOGLE_ENABLED_CAPABILITIES` is an explicit comma-separated allowlist. The beta
configuration includes all implemented capabilities; missing app secrets or an
unknown `GOOGLE_AUTH_MODE` still disable Google. Keep the mode aligned with the
Google project's real configuration:

- `testing`: registered test users only for Workspace scopes. Their grants and
  refresh tokens expire after seven days and need renewed consent.
- `unverified`: an External project published to Production without scope
  verification. No tester enrollment is needed, but Google's unverified-app
  notice, normally 100-user lifetime cap, and account/admin restrictions apply.
- `verified`: use only after Google has approved the actual requested scopes.
  Changing this flag does not obtain approval or bypass Google's enforcement.

Only `identity` requests OpenID and email, which have an exception to the testing
enrollment, warning, and seven-day limits. Calendar,
Gmail, Drive, Docs, Sheets and Contacts are requested incrementally for an actual
task. `drive_files` covers files created by this app; an existing-file Picker is
not implemented. `drive_read` is broader and restricted. There is no request for
full Gmail deletion, Drive-wide writes, or Google account administration.

## Removing the unverified-app warning correctly

Production status alone does not verify an application. Complete these gates:

1. Verify ownership of `tironi.xyz` in Search Console with a project owner/editor.
2. Publish an accurate app homepage and privacy policy on the same owned domain,
   link the policy from the homepage, and configure the matching OAuth branding.
   The existing `/welcome` page has no visible privacy link. The separate website
   has not been changed by this repository.
3. Keep the published data-handling policy aligned with the implementation: agent
   memory/history retention, deletion process, hosting and configured model
   processors, restricted-data Limited Use and no model-training commitments.
   Do not submit claims that have not been verified with the relevant providers.
4. Verify and publish the brand, then submit required scope justifications and an
   English demonstration of the actual working consent and features.
5. Complete sensitive-scope review. Gmail mailbox reading and broad Drive reading
   are restricted scopes; server-side storage/transmission can require a security
   assessment. Do not describe this as already approved or guaranteed.
6. Test the published app using an external Google account that is not a project
   test user, verify the intended account and one real operation, refresh the
   credential in a new process, and test revocation.

Keep the normal Google consent screen. Account security alerts and Workspace
administrator policies remain controlled by Google; the app cannot promise to
suppress all of them. For the expressly disclosed unverified beta, let the owner
review Google's notice and decide whether to authorize. Do not automate that
decision, bypass browser certificate warnings or account blocks, or describe
publication as verification.

Primary references:

- [Audience modes, testing expiry and user caps](https://support.google.com/cloud/answer/15549945)
- [Google brand verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/brand-verification)
- [Sensitive-scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification)
- [Restricted-scope verification and security assessments](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification)
- [Gmail scope classifications](https://developers.google.com/workspace/gmail/api/auth/scopes)
- [Drive per-file access](https://developers.google.com/workspace/drive/api/guides/api-specific-auth)

Google's remote Workspace MCP servers were also reviewed. They currently require
Developer Preview membership and a developer-owned OAuth client; they do not
remove these verification requirements or provide universal account access.
