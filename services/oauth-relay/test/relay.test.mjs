import { after, before, test } from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createHash, createHmac, randomBytes } from "node:crypto";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { setTimeout as pause } from "node:timers/promises";

const base = "http://127.0.0.1:18791";
let process, folder;
before(async () => {
  folder = await mkdtemp(join(tmpdir(), "zoen-relay-"));
  process = spawn("node", ["node_modules/wrangler/bin/wrangler.js", "dev", "test/worker-fixture.mjs", "--local", "--ip", "127.0.0.1",
    "--port", "18791", "--persist-to", folder, "--var", "FLOW_TTL_SECONDS:3",
    "--var", "GOOGLE_CLIENT_ID:fixture.apps.googleusercontent.com", "--var", "GOOGLE_CLIENT_SECRET:fixture-secret",
    "--var", "GOOGLE_ENCRYPTION_KEY:" + "ab".repeat(32), "--var", "GOOGLE_REDIRECT_URI:https://auth.example.com/callback",
    "--var", "GOOGLE_ENABLED_CAPABILITIES:identity,calendar_read", "--var", "GOOGLE_AUTH_MODE:testing",
    "--var", "KAPSO_WEBHOOK_SECRET:fixture-hook", "--var", "WHATSAPP_POLL_TOKEN:fixture-poll-token-32",
    "--var", "KAPSO_API_KEY:fixture-key", "--var", "KAPSO_PHONE_NUMBER_ID:123456789012345",
    "--var", "KAPSO_API_BASE:http://127.0.0.1:18791/__fixture/kapso/v24.0",
    "--var", "PLOW_API_BASE:http://127.0.0.1:18791/__fixture/plow", "--log-level", "error"],
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

test("Google token requests use a redirect mode supported by the Cloudflare runtime", async () => {
  const result = await fetch(`${base}/__fixture/google-runtime`);
  assert.equal(result.status, 200);
  assert.deepEqual(await result.json(), { refreshed: true, redirect: "manual" });
});

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
  assert.match(html, /mesmo link/);
  assert.ok(!html.includes("sensitive text"));
  const data = await (await fetch(flow.url, { headers: flow.headers })).json();
  assert.equal(data.status, "pending");
  assert.equal(data.callback, undefined);
});

test("signup error keeps the flow open for a later code", async () => {
  const flow = await create();
  assert.equal((await callback(flow, { code: "", error: "access_denied" })).status, 200);
  assert.equal((await callback(flow, { code: "", error: "login_required" })).status, 200);
  assert.equal((await (await fetch(flow.url, { headers: flow.headers })).json()).status, "pending");
  const result = await callback(flow);
  assert.equal(result.status, 200);
  assert.match(await result.text(), /Autorização recebida/);
  const data = await (await fetch(flow.url, { headers: flow.headers })).json();
  assert.equal(data.status, "ready");
  assert.equal(data.callback.code, "test-code");
  assert.equal((await callback(flow, { code: "", error: "access_denied" })).status, 200);
  assert.equal((await (await fetch(flow.url, { headers: flow.headers })).json()).callback.code, "test-code");
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
  assert.ok(home.includes('href="https://tryzoen.com"'));
  assert.ok(!home.includes("zoen.tironi.xyz"));
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

async function pair(headers, phone, code, idem, extra = {}) {
  const call = () => fetch(`${base}/whatsapp/register`, {
    method: "POST",
    headers: { ...headers, "Content-Type": "application/json" },
    body: JSON.stringify({ ...extra, code }),
  });
  const waiting = await (await call()).json();
  const payload = JSON.stringify({
    message: { id: `wamid.${idem}`, type: "text", from: phone, text: { body: code }, kapso: { direction: "inbound" } },
    conversation: { contact_name: phone, phone_number: phone },
  });
  const inbound = await (await fetch(`${base}/whatsapp/webhook`, kapso(payload, idem))).json();
  return { waiting, inbound, linked: await (await call()).json() };
}

function kapso(payload, key) {
  return {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Webhook-Event": "whatsapp.message.received",
      "X-Webhook-Signature": createHmac("sha256", "fixture-hook").update(payload).digest("hex"),
      "X-Idempotency-Key": key,
    },
    body: payload,
  };
}

test("the two-factor link is one clickable address that opens the setup SMS", async () => {
  const start = await fetch(`${base}/whatsapp/start`);
  assert.equal(start.status, 200);
  const html = await start.text();
  assert.match(html, /class="connection-page"/);
  assert.match(html, /class="brand"/);
  assert.match(html, /Confirmação de dois fatores/);
  assert.match(html, /Esse botão manda um SMS pra confirmar o seu telefone/);
  assert.match(html, /Quando a linha existir, eu te mando um código no iMessage/);
  assert.match(html, /Você envia esse código aqui no WhatsApp/);
  assert.match(html, /Pode levar alguns minutinhos/);
  assert.match(html, /class="button" href="sms:\+16282463032\?&amp;body=Set%20this%20up%20for%20me%3A%20aiworthusing.com%2Fagent-index%2Fzoen"/);
});

test("the setup button waits fifteen minutes before it is sent again", async () => {
  const phone = "5511655555555";
  const inbound = (id, body, key) => fetch(`${base}/whatsapp/webhook`, kapso(JSON.stringify({
    message: { id, type: "text", from: phone, text: { body }, kapso: { direction: "inbound" } },
    conversation: { contact_name: "Caio", phone_number: phone },
  }), key));
  assert.equal((await (await inbound("wamid.wait", "oi", "idem-wait")).json()).setup, true);
  assert.equal((await (await inbound("wamid.wait2", "de novo", "idem-wait-2")).json()).setup, false);
  const posts = await (await fetch(`${base}/__fixture/kapso/posts`)).json();
  const buttons = posts.filter((post) => post?.to === phone && post?.type === "interactive");
  assert.equal(buttons.length, 1);
  assert.match(buttons[0].interactive.body.text, /pode levar alguns minutinhos/);
});

test("a new WhatsApp number gets the setup SMS, then only its own agent", async () => {
  const first = JSON.stringify({
    message: { id: "wamid.1", type: "text", from: "5511999999999", text: { body: "oi" }, kapso: { direction: "inbound" } },
    conversation: { contact_name: "Ana", phone_number: "5511999999999" },
  });
  const opened = await (await fetch(`${base}/whatsapp/webhook`, kapso(first, "idem-1"))).json();
  assert.equal(opened.setup, true);
  assert.equal(opened.ok, true);
  const duplicate = await (await fetch(`${base}/whatsapp/webhook`, kapso(first, "idem-1"))).json();
  assert.equal(duplicate.duplicate, true);
  assert.equal((await fetch(`${base}/whatsapp/inbox`)).status, 403);
  const badSig = kapso(first, "idem-bad");
  badSig.headers["X-Webhook-Signature"] = "ab".repeat(32);
  assert.equal((await fetch(`${base}/whatsapp/webhook`, badSig)).status, 401);
  assert.equal((await fetch(`${base}/whatsapp/register`, {
    method: "POST",
    headers: { Authorization: "Bearer wrong-agent-token", "Content-Type": "application/json" },
    body: JSON.stringify({ phone: "5511999999999" }),
  })).status, 403);
  assert.equal((await fetch(`${base}/whatsapp/register`, {
    method: "POST",
    headers: { Authorization: "Bearer fixture-agent-token-32", "Content-Type": "application/json" },
    body: JSON.stringify({ phone: "5511888888888" }),
  })).status, 404);
  const registered = (await pair(
    { Authorization: "Bearer fixture-agent-token-32" },
    "5511999999999",
    "111111",
    "pair-ana",
  )).linked;
  assert.equal(registered.ok, true);
  assert.match(registered.token, /^[A-Za-z0-9_-]{43,}$/);
  const second = JSON.stringify({
    message: { id: "wamid.2", type: "text", from: "5511999999999", text: { body: "voltei" }, kapso: { direction: "inbound" } },
    conversation: { contact_name: "Ana", phone_number: "5511999999999" },
  });
  const again = await (await fetch(`${base}/whatsapp/webhook`, kapso(second, "idem-2"))).json();
  assert.equal(again.setup, false);
  const auth = { Authorization: `Bearer ${registered.token}` };
  const inbox = await (await fetch(`${base}/whatsapp/inbox`, { headers: auth })).json();
  assert.deepEqual(inbox.messages.map((message) => message.text), ["oi", "111111", "voltei"]);
  assert.equal((await fetch(`${base}/whatsapp/send`, {
    method: "POST",
    headers: { ...auth, "Content-Type": "application/json" },
    body: JSON.stringify({ to: "5511888888888", text: "nao" }),
  })).status, 403);
  assert.equal((await fetch(`${base}/whatsapp/send`, {
    method: "POST",
    headers: { ...auth, "Content-Type": "application/json" },
    body: JSON.stringify({ to: "5511999999999", text: "oi ana" }),
  })).status, 200);
  assert.equal((await fetch(`${base}/whatsapp/inbox/ack`, {
    method: "POST",
    headers: { ...auth, "Content-Type": "application/json" },
    body: JSON.stringify({ ids: ["wamid.1", "wamid.pair-ana", "wamid.2"] }),
  })).status, 200);
  const empty = await (await fetch(`${base}/whatsapp/inbox`, { headers: auth })).json();
  assert.deepEqual(empty.messages, []);
  const third = JSON.stringify({
    message: { id: "wamid.3", type: "text", from: "5511777777777", text: { body: "bia" }, kapso: { direction: "inbound" } },
    conversation: { contact_name: "Bia", phone_number: "5511777777777" },
  });
  const bia = await (await fetch(`${base}/whatsapp/webhook`, kapso(third, "idem-3"))).json();
  assert.equal(bia.setup, true);
  const fromContacts = (await pair(
    { Authorization: "Bearer fixture-agent-token-33" },
    "5511777777777",
    "222222",
    "pair-bia",
  )).linked;
  assert.equal(fromContacts.ok, true);
  const brazil = JSON.stringify({
    message: { id: "wamid.4", type: "text", from: "553199941160", text: { body: "Fala comigo" }, kapso: { direction: "inbound" } },
    conversation: { contact_name: "Lia", phone_number: "553199941160" },
  });
  const openedBrazil = await (await fetch(`${base}/whatsapp/webhook`, kapso(brazil, "idem-4"))).json();
  assert.equal(openedBrazil.setup, true);
  const matched = (await pair(
    { Authorization: "Bearer fixture-agent-token-34" },
    "553199941160",
    "333333",
    "pair-lia",
  )).linked;
  assert.equal(matched.ok, true);
  const lia = { Authorization: `Bearer ${matched.token}` };
  const waiting = await (await fetch(`${base}/whatsapp/inbox`, { headers: lia })).json();
  assert.equal(waiting.messages[0].text, "Fala comigo");
  assert.equal(waiting.messages[0].to, "553199941160");
  const resumedRegister = await (await fetch(`${base}/whatsapp/register`, {
    method: "POST",
    headers: { Authorization: "Bearer fixture-agent-token-34", "Content-Type": "application/json" },
    body: "{}",
  })).json();
  assert.equal(resumedRegister.ok, true);
  const resumed = await (await fetch(`${base}/whatsapp/inbox`, { headers: { Authorization: `Bearer ${resumedRegister.token}` } })).json();
  assert.equal(resumed.messages[0].text, "Fala comigo");
  const one = JSON.stringify({
    message: { id: "wamid.5", type: "text", from: "5511611111111", text: { body: "um" }, kapso: { direction: "inbound" } },
    conversation: { contact_name: "Um", phone_number: "5511611111111" },
  });
  const two = JSON.stringify({
    message: { id: "wamid.6", type: "text", from: "5511622222222", text: { body: "dois" }, kapso: { direction: "inbound" } },
    conversation: { contact_name: "Dois", phone_number: "5511622222222" },
  });
  assert.equal((await (await fetch(`${base}/whatsapp/webhook`, kapso(one, "idem-5"))).json()).setup, true);
  assert.equal((await (await fetch(`${base}/whatsapp/webhook`, kapso(two, "idem-6"))).json()).setup, true);
  const crowded = await fetch(`${base}/whatsapp/register`, {
    method: "POST",
    headers: { Authorization: "Bearer fixture-agent-token-35", "Content-Type": "application/json" },
    body: "{}",
  });
  assert.equal(crowded.status, 404);
  const posts = await (await fetch(`${base}/__fixture/kapso/posts`)).json();
  const button = posts.find((post) => post?.to === "5511611111111" && post?.type === "interactive");
  const claim = new URL(button.interactive.action.parameters.url).searchParams.get("c");
  assert.equal((await fetch(`${base}/whatsapp/start?c=${claim}`)).status, 200);
  const claimed = (await pair(
    { Authorization: "Bearer fixture-agent-token-35" },
    "5511611111111",
    "444444",
    "pair-um",
  )).linked;
  assert.equal(claimed.ok, true);
  const emailOwner = { Authorization: `Bearer ${claimed.token}` };
  const held = await (await fetch(`${base}/whatsapp/inbox`, { headers: emailOwner })).json();
  assert.equal(held.messages[0].text, "um");
  assert.equal(held.messages[0].to, "5511611111111");
});

test("a cloud VM links with the uid it read from its own proxy", async () => {
  const inbound = JSON.stringify({
    message: { id: "wamid.cloud", type: "text", from: "5511633333333", text: { body: "cloud" }, kapso: { direction: "inbound" } },
    conversation: { contact_name: "Cloud", phone_number: "5511633333333" },
  });
  assert.equal((await (await fetch(`${base}/whatsapp/webhook`, kapso(inbound, "idem-cloud"))).json()).setup, true);
  const uid = "ab".repeat(16);
  const secret = "a".repeat(43);
  const register = (body) => fetch(`${base}/whatsapp/register`, {
    method: "POST",
    headers: { Authorization: "Bearer proxied", "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  assert.equal((await register({})).status, 403);
  const linked = (await pair(
    { Authorization: "Bearer proxied" },
    "5511633333333",
    "555555",
    "pair-cloud",
    { agent_uid: uid, secret },
  )).linked;
  assert.equal(linked.ok, true);
  const inbox = await (await fetch(`${base}/whatsapp/inbox`, { headers: { Authorization: `Bearer ${linked.token}` } })).json();
  assert.equal(inbox.messages[0].text, "cloud");
  assert.equal((await register({ agent_uid: uid, secret: "b".repeat(43) })).status, 403);
  const resumed = await (await register({ agent_uid: uid, secret })).json();
  assert.equal(resumed.ok, true);
  const intruder = "cd".repeat(16);
  assert.equal((await (await register({ agent_uid: intruder, secret: "c".repeat(43), code: "666666" })).json()).waiting, true);
  const stolen = JSON.stringify({
    message: { id: "wamid.cloud-steal", type: "text", from: "5511633333333", text: { body: "666666" }, kapso: { direction: "inbound" } },
    conversation: { contact_name: "Cloud", phone_number: "5511633333333" },
  });
  assert.equal((await (await fetch(`${base}/whatsapp/webhook`, kapso(stolen, "idem-cloud-steal"))).json()).ok, true);
  assert.equal((await register({ agent_uid: intruder, secret: "c".repeat(43), code: "666666" })).status, 409);
  assert.equal((await fetch(`${base}/whatsapp/release`, {
    method: "POST",
    headers: { Authorization: `Bearer ${resumed.token}` },
  })).status, 200);
  assert.equal((await fetch(`${base}/whatsapp/inbox`, { headers: { Authorization: `Bearer ${resumed.token}` } })).status, 403);
  const again = JSON.stringify({
    message: { id: "wamid.cloud2", type: "text", from: "5511633333333", text: { body: "de novo" }, kapso: { direction: "inbound" } },
    conversation: { contact_name: "Cloud", phone_number: "5511633333333" },
  });
  assert.equal((await (await fetch(`${base}/whatsapp/webhook`, kapso(again, "idem-cloud-2"))).json()).setup, true);
});

test("a WhatsApp photo, quote and tapback stay on that chat", async () => {
  const photo = JSON.stringify({
    message: {
      id: "wamid.photo",
      type: "image",
      from: "5511644444444",
      image: { id: "media-jpeg", mime_type: "image/jpeg", caption: "olha" },
      context: { id: "wamid.earlier" },
      kapso: { direction: "inbound", quoted_content: "a mensagem de antes" },
    },
    conversation: { contact_name: "Foto", phone_number: "5511644444444" },
  });
  assert.equal((await (await fetch(`${base}/whatsapp/webhook`, kapso(photo, "idem-photo"))).json()).setup, true);
  const registered = (await pair(
    { Authorization: "Bearer proxied" },
    "5511644444444",
    "777777",
    "pair-photo",
    { agent_uid: "ef".repeat(16), secret: "f".repeat(43) },
  )).linked;
  const auth = { Authorization: `Bearer ${registered.token}`, "Content-Type": "application/json" };
  const inbox = await (await fetch(`${base}/whatsapp/inbox`, { headers: auth })).json();
  assert.equal(inbox.messages[0].text, "olha");
  assert.equal(inbox.messages[0].media_id, "media-jpeg");
  assert.equal(inbox.messages[0].kind, "image");
  assert.equal(inbox.messages[0].reply_to, "wamid.earlier");
  assert.equal(inbox.messages[0].reply_text, "a mensagem de antes");
  const file = await fetch(`${base}/whatsapp/media?id=media-jpeg`, { headers: auth });
  assert.equal(file.status, 200);
  assert.equal(file.headers.get("content-type"), "image/jpeg");
  assert.equal((await file.arrayBuffer()).byteLength, 4);
  assert.equal((await fetch(`${base}/whatsapp/send`, {
    method: "POST",
    headers: auth,
    body: JSON.stringify({ to: "5511644444444", text: "vi", reply_to: "wamid.photo" }),
  })).status, 200);
  assert.equal((await fetch(`${base}/whatsapp/send`, {
    method: "POST",
    headers: auth,
    body: JSON.stringify({ to: "5511644444444", reaction: { type: "love", message_id: "wamid.photo" } }),
  })).status, 200);
  const png = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]).toString("base64");
  assert.equal((await fetch(`${base}/whatsapp/send`, {
    method: "POST",
    headers: auth,
    body: JSON.stringify({
      to: "5511644444444",
      media: { mime: "image/png", name: "shot.png", data: png },
      reply_to: "wamid.photo",
    }),
  })).status, 200);
  const posts = await (await fetch(`${base}/__fixture/kapso/posts`)).json();
  const quote = posts.find((post) => post?.context?.message_id === "wamid.photo" && post?.type === "text");
  const heart = posts.find((post) => post?.type === "reaction" && post?.to === "5511644444444");
  const picture = posts.find((post) => post?.type === "image" && post?.image?.id === "uploaded-media");
  assert.equal(quote.text.body, "vi");
  assert.equal(heart.reaction.emoji, "❤️");
  assert.equal(picture.context.message_id, "wamid.photo");
});

test("each line's code binds only the WhatsApp that sends it", async () => {
  const inbound = (phone, id, body, key) => fetch(`${base}/whatsapp/webhook`, kapso(JSON.stringify({
    message: { id, type: "text", from: phone, text: { body }, kapso: { direction: "inbound" } },
    conversation: { contact_name: phone, phone_number: phone },
  }), key));
  const ana = "5511666666666";
  const bia = "5511677777777";
  assert.equal((await (await inbound(ana, "wamid.code.ana", "oi ana", "idem-code-ana")).json()).setup, true);
  assert.equal((await (await inbound(bia, "wamid.code.bia", "oi bia", "idem-code-bia")).json()).setup, true);
  const register = (uid, secret, code) => fetch(`${base}/whatsapp/register`, {
    method: "POST",
    headers: { Authorization: "Bearer proxied", "Content-Type": "application/json" },
    body: JSON.stringify({ agent_uid: uid, secret, code }),
  });
  const waitingA = await (await register("12".repeat(16), "d".repeat(43), "142857")).json();
  const waitingB = await (await register("34".repeat(16), "e".repeat(43), "314159")).json();
  assert.equal(waitingA.waiting, true);
  assert.equal(waitingA.token, undefined);
  assert.equal(waitingB.waiting, true);
  assert.equal((await (await inbound(ana, "wamid.code.ana2", "142857", "idem-code-ana2")).json()).ok, true);
  const linkedA = await (await register("12".repeat(16), "d".repeat(43), "142857")).json();
  assert.equal(linkedA.ok, true);
  assert.match(linkedA.token, /^[A-Za-z0-9_-]{43,}$/);
  const inboxA = await (await fetch(`${base}/whatsapp/inbox`, {
    headers: { Authorization: `Bearer ${linkedA.token}` },
  })).json();
  assert.deepEqual(inboxA.messages.map((message) => message.text), ["oi ana", "142857"]);
  assert.equal((await fetch(`${base}/whatsapp/send`, {
    method: "POST",
    headers: { Authorization: `Bearer ${linkedA.token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ to: bia, text: "nao" }),
  })).status, 403);
  assert.equal((await (await inbound(bia, "wamid.code.bia2", "314159", "idem-code-bia2")).json()).ok, true);
  const linkedB = await (await register("34".repeat(16), "e".repeat(43), "314159")).json();
  assert.equal(linkedB.ok, true);
  const inboxB = await (await fetch(`${base}/whatsapp/inbox`, {
    headers: { Authorization: `Bearer ${linkedB.token}` },
  })).json();
  assert.deepEqual(inboxB.messages.map((message) => message.text), ["oi bia", "314159"]);
  const posts = await (await fetch(`${base}/__fixture/kapso/posts`)).json();
  const welcomes = posts.filter((post) => post?.text?.body === "pode falar. eu tô aqui." && (post.to === ana || post.to === bia));
  assert.deepEqual(welcomes.map((post) => post.to).sort(), [ana, bia]);
});
