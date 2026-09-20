import { after, before, test } from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createHash, randomBytes } from "node:crypto";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { setTimeout as pause } from "node:timers/promises";

const base = "http://127.0.0.1:18791";
let process, folder;
before(async () => {
  folder = await mkdtemp(join(tmpdir(), "zoen-relay-"));
  process = spawn("node", ["node_modules/wrangler/bin/wrangler.js", "dev", "--local", "--ip", "127.0.0.1",
    "--port", "18791", "--persist-to", folder, "--var", "FLOW_TTL_SECONDS:3",
    "--var", "GOOGLE_CLIENT_ID:fixture.apps.googleusercontent.com", "--var", "GOOGLE_CLIENT_SECRET:fixture-secret",
    "--var", "GOOGLE_ENCRYPTION_KEY:" + "ab".repeat(32), "--var", "GOOGLE_REDIRECT_URI:https://auth.example.com/callback",
    "--var", "GOOGLE_ENABLED_CAPABILITIES:identity,calendar_read", "--var", "GOOGLE_AUTH_MODE:testing", "--log-level", "error"],
  { stdio: ["ignore", "ignore", "pipe"], env: { ...globalThis.process.env, WRANGLER_SEND_METRICS: "false" } });
  let errors = "";
  process.stderr.on("data", (data) => { errors += data; });
  for (let i = 0; i < 150; i++) {
    if (process.exitCode !== null) throw new Error(`Worker exited: ${errors}`);
    try { if ((await fetch(`${base}/health`)).ok) return; } catch {}
    await pause(100);
  }
  throw new Error(`Worker startup timeout: ${errors}`);
});
after(async () => {
  if (process && process.exitCode === null) {
    const exited = new Promise((resolve) => process.once("exit", resolve));
    process.kill("SIGTERM");
    await exited;
  }
  if (folder) await rm(folder, { recursive: true, force: true });
});

async function create() {
  const state = randomBytes(32).toString("base64url"), poll_token = randomBytes(32).toString("base64url");
  const id = createHash("sha256").update(state).digest("hex");
  const body = JSON.stringify({ state, poll_token });
  const headers = { Authorization: `Bearer ${poll_token}` };
  const result = await fetch(`${base}/flows`, { method: "POST", headers: { "Content-Type": "application/json" }, body });
  assert.equal(result.status, 201);
  return { state, id, body, headers, url: `${base}/flows/${id}` };
}
const callback = (flow, params = {}) => fetch(`${base}/callback?${new URLSearchParams({ state: flow.state, code: "test-code", ...params })}`);

test("isolates flows, keeps callback retryable until authenticated acknowledgment", async () => {
  const flow = await create(), other = await create();
  assert.equal((await fetch(flow.url)).status, 403);
  assert.equal((await fetch(flow.url, { headers: other.headers })).status, 403);
  assert.equal((await fetch(`${base}/callback?state=${flow.state}&code=x&state=${other.state}`)).status, 400);
  assert.equal((await callback({ state: randomBytes(32).toString("base64url") })).status, 410);
  assert.equal((await fetch(`${flow.url}/ack`, { method: "POST", headers: flow.headers })).status, 409);
  const result = await callback(flow, { iss: "https://issuer.example" });
  assert.equal(result.status, 200);
  assert.equal(result.headers.get("Referrer-Policy"), "no-referrer");
  assert.equal(result.headers.get("Cache-Control"), "no-store");
  const html = await result.text();
  assert.match(html, /Autorização recebida/);
  assert.ok(!html.includes(flow.state) && !html.includes("test-code"));
  assert.ok(!html.includes("https://issuer.example"));
  assert.match(result.headers.get("Content-Security-Policy"), /style-src 'self'; img-src 'self'/);
  const first = await (await fetch(flow.url, { headers: flow.headers })).json();
  assert.deepEqual(first, await (await fetch(flow.url, { headers: flow.headers })).json());
  assert.equal(first.callback.iss, "https://issuer.example");
  assert.equal((await callback(flow, { iss: "https://issuer.example" })).status, 200);
  assert.equal((await callback(flow, { code: "different-code" })).status, 409);
  assert.equal((await (await fetch(other.url, { headers: other.headers })).json()).status, "pending");
  for (let i = 0; i < 2; i++) assert.equal((await fetch(`${flow.url}/ack`, { method: "POST", headers: flow.headers })).status, 200);
  const consumed = await (await fetch(flow.url, { headers: flow.headers })).json();
  assert.deepEqual(consumed, { status: "consumed" });
  assert.equal((await callback(flow)).status, 409);
});

test("claim is idempotent, competing claim fails, cancellation prevents delivery", async () => {
  const flow = await create();
  const post = (body) => fetch(`${base}/flows`, { method: "POST", headers: { "Content-Type": "application/json" }, body });
  assert.equal((await post(flow.body)).status, 200);
  assert.equal((await post(JSON.stringify({ ...JSON.parse(flow.body), poll_token: randomBytes(32).toString("base64url") }))).status, 409);
  assert.equal((await fetch(flow.url, { method: "DELETE", headers: flow.headers })).status, 200);
  assert.equal((await callback(flow)).status, 409);
});

test("denial is delivered without untrusted error descriptions", async () => {
  const flow = await create();
  const result = await callback(flow, { code: "", error: "access_denied", error_description: "sensitive text" });
  assert.equal(result.status, 200);
  const html = await result.text();
  assert.match(html, /Autorização não concluída/);
  assert.ok(!html.includes("sensitive text"));
  const data = await (await fetch(flow.url, { headers: flow.headers })).json();
  assert.equal(data.callback.error, "access_denied");
  assert.equal(data.callback.error_description, undefined);
});

test("callback pages load only bundled assets and never reflect malformed input", async () => {
  for (const path of ["/style.css", "/sky-midnight.webp", "/zoen-avatar.webp"]) {
    assert.equal((await fetch(`${base}${path}`)).status, 200);
  }
  const result = await fetch(`${base}/callback?state=invalid&code=${encodeURIComponent('<script>alert(1)</script>')}`);
  assert.equal(result.status, 400);
  const html = await result.text();
  assert.ok(!html.includes("<script>"));
  assert.match(html, /Não deu para concluir/);
  assert.match(await (await fetch(base)).text(), /Suas conexões, com o Zoen/);
});

test("expires pending and completed flows, rejects oversized requests", async () => {
  const flow = await create();
  assert.equal((await fetch(`${base}/flows`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "x".repeat(4097) })).status, 400);
  await pause(3200);
  assert.equal((await fetch(flow.url, { headers: flow.headers })).status, 410);
  assert.equal((await callback(flow)).status, 410);
});

test("legal pages are public, isolated from callback parameters and linked from the connection page", async () => {
  const home = await (await fetch(base)).text();
  for (const path of ["/privacy", "/terms"]) {
    assert.ok(home.includes(`href="${path}"`));
    const result = await fetch(`${base}${path}?code=private-code&state=private-state`);
    assert.equal(result.status, 200);
    assert.equal(result.headers.get("Referrer-Policy"), "no-referrer");
    assert.match(result.headers.get("Content-Security-Policy"), /default-src 'none'/);
    const html = await result.text();
    assert.ok(!html.includes("private-code") && !html.includes("private-state"));
    assert.ok(html.includes("enzo@zoen.space"));
  }
});

test("Google registration and PKCE rejection use the real isolated Durable Object", async () => {
  const state = randomBytes(32).toString("base64url"), poll_token = randomBytes(32).toString("base64url");
  const verifier = randomBytes(48).toString("base64url");
  const code_challenge = createHash("sha256").update(verifier).digest("base64url");
  const register = (capabilities) => fetch(`${base}/google/flows`, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({ state, poll_token, code_challenge, capabilities }) });
  assert.equal((await register(["gmail_read"])).status, 403);
  const result = await register(["calendar_read"]);
  assert.equal(result.status, 201);
  const data = await result.json(), url = new URL(data.authorization_url);
  assert.equal(data.auth_mode, "testing");
  assert.equal(url.origin, "https://accounts.google.com");
  assert.equal(url.searchParams.get("code_challenge"), code_challenge);
  assert.equal(url.searchParams.get("code_challenge_method"), "S256");
  assert.ok(!url.href.includes(poll_token) && !url.href.includes("fixture-secret"));
  assert.ok(!url.searchParams.get("scope").includes("gmail"));
  assert.equal((await callback({ state })).status, 200);
  const exchange = (headers) => fetch(`${base}/google/flows/${data.flow_id}/exchange`, { method: "POST",
    headers: { "Content-Type": "application/json", ...headers }, body: JSON.stringify({ code_verifier: "wrong".repeat(12) }) });
  assert.equal((await exchange({})).status, 403);
  assert.equal((await exchange({ Authorization: `Bearer ${poll_token}` })).status, 403);
  const headers = { Authorization: `Bearer ${poll_token}` };
  assert.equal((await fetch(`${base}/flows/${data.flow_id}`, { method: "DELETE", headers })).status, 200);
  assert.equal((await callback({ state })).status, 409);
});
