import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash, randomBytes } from "node:crypto";
import { configured, seal, unseal, exchangeGoogleFlow, refreshGoogle, googleRoute } from "../src/google.js";

const env = {
  GOOGLE_CLIENT_ID: "fixture.apps.googleusercontent.com", GOOGLE_CLIENT_SECRET: "fixture-app-secret",
  GOOGLE_ENCRYPTION_KEY: "ab".repeat(32), GOOGLE_REDIRECT_URI: "https://auth.example.com/callback",
  GOOGLE_ENABLED_CAPABILITIES: "identity,calendar_read",
  GOOGLE_AUTH_MODE: "testing",
};
const verifier = randomBytes(48).toString("base64url");
const challenge = createHash("sha256").update(verifier).digest("base64url");
const incoming = (code_verifier = verifier) => new Request("https://flow/google/exchange", {
  method: "POST", body: JSON.stringify({ code_verifier }),
});
const makeFlow = () => ({ provider: "google", challenge, status: "ready", callback: {
  state: "s".repeat(43), code: "fixture-auth-code", iss: "https://accounts.google.com",
} });
const tokenResponse = () => Response.json({ access_token: "fixture-access", refresh_token: "fixture-refresh",
  token_type: "Bearer", expires_in: 3600, scope: "openid email https://www.googleapis.com/auth/calendar.events.readonly" });

test("Google requires operator secrets, enabled capabilities and an explicit audience mode", async () => {
  assert.equal(configured({}), false);
  assert.equal(configured({ ...env, GOOGLE_ENABLED_CAPABILITIES: "" }), false);
  const result = await googleRoute(new Request("https://relay/google/config"), {});
  assert.deepEqual(await result.json(), { configured: false, capabilities: [], auth_mode: "disabled" });
  for (const mode of [undefined, "", "production", "unknown"]) {
    assert.equal(configured({ ...env, GOOGLE_AUTH_MODE: mode }), false);
  }
  for (const mode of ["testing", "unverified", "verified"]) {
    const config = { ...env, GOOGLE_AUTH_MODE: mode };
    assert.equal(configured(config), true);
    const result = await googleRoute(new Request("https://relay/google/config"), config);
    assert.deepEqual(await result.json(), { configured: true, capabilities: ["identity", "calendar_read"], auth_mode: mode });
  }
});

test("refresh handles are authenticated, encrypted, purpose-bound and client-bound", async () => {
  const payload = { refresh_token: "private-refresh" };
  const handle = await seal(payload, "refresh", env);
  assert.ok(!handle.includes(payload.refresh_token));
  assert.deepEqual(await unseal(handle, "refresh", env), payload);
  await assert.rejects(unseal(handle, "delivery", env));
  await assert.rejects(unseal(handle, "refresh", { ...env, GOOGLE_CLIENT_ID: "other.apps.googleusercontent.com" }));
  const [iv, cipher] = handle.split(".");
  await assert.rejects(unseal(iv + "." + (cipher[0] === "A" ? "B" : "A") + cipher.slice(1), "refresh", env));
});

test("wrong PKCE, provider, issuer and cancelled consent never reach Google's token endpoint", async () => {
  let calls = 0;
  const http = async () => { calls++; return tokenResponse(); };
  const ctx = { storage: { put: async () => {} } };
  assert.equal((await exchangeGoogleFlow(incoming("x".repeat(64)), env, ctx, makeFlow(), http)).status, 403);
  assert.equal((await exchangeGoogleFlow(incoming(), env, ctx, { ...makeFlow(), provider: "other" }, http)).status, 400);
  assert.equal((await exchangeGoogleFlow(incoming(), env, ctx, { ...makeFlow(), status: "cancelled" }, http)).status, 409);
  const wrongIssuer = makeFlow(); wrongIssuer.callback.iss = "https://evil.example";
  assert.equal((await exchangeGoogleFlow(incoming(), env, ctx, wrongIssuer, http)).status, 400);
  assert.equal(calls, 0);
});

test("code exchange is retryable with encrypted delivery and no app secret in agent credentials", async () => {
  let calls = 0, stored;
  const http = async (url, init) => {
    calls++;
    assert.equal(url, "https://oauth2.googleapis.com/token");
    assert.equal(init.redirect, "error");
    assert.equal(init.body.get("code_verifier"), verifier);
    assert.equal(init.body.get("client_secret"), env.GOOGLE_CLIENT_SECRET);
    assert.equal(init.body.get("redirect_uri"), env.GOOGLE_REDIRECT_URI);
    return tokenResponse();
  };
  const ctx = { storage: { put: async (key, value) => { stored = structuredClone(value); } } };
  const flow = makeFlow();
  const result = await (await exchangeGoogleFlow(incoming(), env, ctx, flow, http)).json();
  assert.equal(result.access_token, "fixture-access");
  assert.ok(result.refresh_handle);
  assert.equal(result.client_secret, undefined);
  assert.equal(result.refresh_token, undefined);
  assert.ok(!JSON.stringify(stored).includes("fixture-access"));
  assert.ok(!JSON.stringify(stored).includes("fixture-refresh"));
  assert.equal(stored.callback, undefined);
  assert.deepEqual(await (await exchangeGoogleFlow(incoming(), env, ctx, stored, http)).json(), result);
  assert.equal(calls, 1);
});

test("refresh survives a new process with the same operator key and preserves granted scopes", async () => {
  const refresh_handle = await seal({ refresh_token: "fixture-refresh", scopes: ["email"] }, "refresh", env);
  const result = await refreshGoogle({ refresh_handle }, { ...env }, async (url, init) => {
    assert.equal(init.body.get("refresh_token"), "fixture-refresh");
    assert.equal(init.body.get("grant_type"), "refresh_token");
    return Response.json({ access_token: "refreshed", token_type: "Bearer", expires_in: 3600 });
  });
  assert.equal(result.access_token, "refreshed");
  assert.deepEqual(result.scopes, ["email"]);
  assert.equal((await unseal(result.refresh_handle, "refresh", env)).refresh_token, "fixture-refresh");
  await assert.rejects(refreshGoogle({ refresh_handle }, env,
    async () => Response.json({ error: "invalid_grant", error_description: "secret text" }, { status: 400 })),
  { message: "google_reauthorization_required" });
});

test("temporary Google failures keep the authorization retryable without exposing provider errors", async () => {
  const flow = makeFlow();
  const ctx = { storage: { put: async () => {} } };
  const failed = await exchangeGoogleFlow(incoming(), env, ctx, flow,
    async () => Response.json({ error: "server_error", error_description: "private provider detail" }, { status: 503 }));
  assert.equal(failed.status, 503);
  assert.deepEqual(await failed.json(), { error: "google_exchange_unavailable" });
  assert.equal(flow.status, "ready");
  assert.equal((await exchangeGoogleFlow(incoming(), env, ctx, flow, async () => tokenResponse())).status, 200);
});
