# Independent Google authorization

Zoen's Google connector uses our OAuth app and HTTPS Worker. No Plow Google
connector, owner Mac, inbound VM port, or change to Plow hosting is needed.
Hermes' bundled Google API command implementations are reused through
`/opt/plow/zoen/google_workspace.py`; their legacy OAuth setup is not invoked.

## Release status — September 19, 2026

The implementation and provider-simulated tests are in this branch. Real Google
account consent and warning-free public authorization have **not** been verified.
Google remains disabled until operator configuration and the applicable Google
verification are complete. The agent reports that state instead of offering a
broken login link or reverting to Plow.

The existing Google Cloud project `zoen-506921` was inspected in the owner's
Console. It is External / Testing, with two existing web clients belonging to the
other application. Branding has a name and support contacts, but no homepage,
privacy-policy URL or logo. The declared permissions include broad Calendar,
Tasks, Contacts, Sheets, Docs, Drive and Gmail scopes. Those existing clients and
permissions were preserved.

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

`GOOGLE_ENABLED_CAPABILITIES` is an explicit comma-separated allowlist, empty by
default. Enable only capabilities ready for the intended audience. Tests can use
Google's configured test users; that does not remove the unverified warning or
make the app production-ready. `identity` requests only OpenID and email. Calendar,
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
3. Finalize the actual Google data-handling policy: agent memory/history retention,
   deletion process, hosting and configured model processors, restricted-data
   Limited Use and no model-training commitments. Do not submit claims that have
   not been verified with the relevant providers.
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
suppress all of them. Never instruct users to click through an unverified warning
as the production onboarding experience.

Primary references:

- [Google brand verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/brand-verification)
- [Sensitive-scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification)
- [Restricted-scope verification and security assessments](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification)
- [Gmail scope classifications](https://developers.google.com/workspace/gmail/api/auth/scopes)
- [Drive per-file access](https://developers.google.com/workspace/drive/api/guides/api-specific-auth)

Google's remote Workspace MCP servers were also reviewed. They currently require
Developer Preview membership and a developer-owned OAuth client; they do not
remove these verification requirements or provide universal account access.
