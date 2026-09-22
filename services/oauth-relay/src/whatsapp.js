import { HEADERS, capability, digest, response } from "./http.js";
import { page } from "./page.js";

const TEXT_LIMIT = 4096;
const QUEUE_LIMIT = 40;
const HOLD_MS = 2 * 60 * 60 * 1000;
const SETUP_COOLDOWN_MS = 15 * 60 * 1000;
export const SETUP_URL = "https://auth.tryzoen.com/whatsapp/start";

const SETUP_BODY = "pra gente começar a conversar, preciso de uma confirmação de dois fatores. o botão manda um sms pra confirmar o seu telefone. quando a linha existir, eu te mando um código no imessage. você envia esse código aqui. pode levar alguns minutinhos";

export function setupMessage(target, url = SETUP_URL) {
  const body = {
    messaging_product: "whatsapp",
    recipient_type: "individual",
    type: "interactive",
    interactive: {
      type: "cta_url",
      body: { text: SETUP_BODY },
      action: {
        name: "cta_url",
        parameters: { display_text: "Enviar o SMS", url },
      },
    },
  };
  if (target.to) body.to = target.to;
  else body.recipient = target.recipient;
  return body;
}

export function startPage() {
  return page("confirm", HEADERS);
}

export async function verifySignature(raw, signature, secret) {
  if (!(raw instanceof Uint8Array) || typeof signature !== "string" || typeof secret !== "string" || !secret) return false;
  if (!/^[0-9a-f]{64}$/i.test(signature)) return false;
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"],
  );
  const mac = new Uint8Array(await crypto.subtle.sign("HMAC", key, raw));
  const expected = Array.from(mac, (byte) => byte.toString(16).padStart(2, "0")).join("");
  if (expected.length !== signature.length) return false;
  let diff = 0;
  for (let i = 0; i < expected.length; i += 1) diff |= expected.charCodeAt(i) ^ signature.toLowerCase().charCodeAt(i);
  return diff === 0;
}

export function sameSecret(left, right) {
  if (typeof left !== "string" || typeof right !== "string" || left.length < 16 || left.length !== right.length) return false;
  let diff = 0;
  for (let i = 0; i < left.length; i += 1) diff |= left.charCodeAt(i) ^ right.charCodeAt(i);
  return diff === 0;
}

function digits(value) {
  const phone = String(value || "").replace(/\D/g, "");
  return phone.length >= 8 && phone.length <= 15 ? phone : "";
}

// WhatsApp still sends some Brazilian mobiles without the extra 9.
export function samePhone(left, right) {
  if (!left || !right) return false;
  if (left === right) return true;
  const short = left.length <= right.length ? left : right;
  const long = left.length <= right.length ? right : left;
  return short.startsWith("55") && short.length === 12 && long.length === 13
    && long === `${short.slice(0, 4)}9${short.slice(4)}`;
}

export function ownerPhones(me) {
  const found = [];
  for (const chat of Array.isArray(me?.chats) ? me.chats : []) {
    for (const person of chat?.participants || []) {
      if (person?.role !== "owner") continue;
      const phone = digits(person.provider_key);
      if (phone && !found.includes(phone)) found.push(phone);
    }
  }
  return found;
}

export function contactPhones(rows) {
  const found = [];
  for (const person of Array.isArray(rows) ? rows : []) {
    if (person?.role !== "owner") continue;
    const phone = digits(person.provider_key);
    if (phone && !found.includes(phone)) found.push(phone);
  }
  return found;
}

function attachment(message) {
  for (const kind of ["image", "audio", "video", "document", "sticker"]) {
    const item = message?.[kind];
    if (!item || typeof item !== "object" || !item.id) continue;
    return {
      kind,
      id: String(item.id).slice(0, 256),
      mime: String(item.mime_type || "").slice(0, 80),
      voice: item.voice === true,
    };
  }
  return null;
}

function oneMessage(item) {
  const message = item?.message;
  if (!message || typeof message !== "object") return null;
  if (message.kapso?.direction && message.kapso.direction !== "inbound") return null;
  const media = attachment(message);
  const caption = media ? message[media.kind]?.caption : "";
  const explicit = message.text?.body || caption || message.kapso?.transcript || "";
  const text = String(explicit || "").trim().slice(0, TEXT_LIMIT);
  if (!text && !media?.id) return null;
  const id = String(message.id || "").slice(0, 256);
  if (!id) return null;
  const phone = digits(message.from) || digits(item.conversation?.phone_number);
  const scoped = String(message.from_user_id || item.conversation?.business_scoped_user_id || "").slice(0, 128);
  if (!phone && !scoped) return null;
  const replyTo = String(message.context?.id || message.context?.message_id || "").slice(0, 256);
  const replyText = String(message.kapso?.quoted_content || message.kapso?.quoted_body || "").trim().slice(0, 500);
  return {
    id,
    text,
    to: phone || null,
    recipient: phone ? null : scoped,
    name: String(item.conversation?.contact_name || "").slice(0, 120),
    kind: media?.kind || "text",
    media_id: media?.id || null,
    mime: media?.mime || null,
    voice: Boolean(media?.voice),
    reply_to: replyTo || null,
    reply_text: replyText || null,
  };
}

export function inboundMessages(eventName, payload) {
  if (eventName !== "whatsapp.message.received" || !payload || typeof payload !== "object") return [];
  const items = payload.batch === true && Array.isArray(payload.data) ? payload.data : [payload];
  const messages = [];
  for (const item of items) {
    const message = oneMessage(item);
    if (message) messages.push(message);
  }
  return messages;
}

const REACTIONS = {
  like: "👍",
  love: "❤️",
  laugh: "😂",
  emphasize: "‼️",
  question: "❓",
  dislike: "👎",
};

function targetFields(target) {
  if (target.to) return { to: target.to };
  return { recipient: target.recipient };
}

function withQuote(body, replyTo) {
  const id = String(replyTo || "").trim().slice(0, 256);
  if (id) body.context = { message_id: id };
  return body;
}

export function kapsoBody(target, text, replyTo = "") {
  return withQuote({
    messaging_product: "whatsapp",
    recipient_type: "individual",
    type: "text",
    text: { body: text, preview_url: false },
    ...targetFields(target),
  }, replyTo);
}

export function reactionBody(target, messageId, kind) {
  const emoji = REACTIONS[kind];
  if (!emoji) return null;
  return {
    messaging_product: "whatsapp",
    recipient_type: "individual",
    type: "reaction",
    reaction: { message_id: String(messageId).slice(0, 256), emoji },
    ...targetFields(target),
  };
}

export function mediaBody(target, kind, mediaId, options = {}) {
  const key = kind === "image" || kind === "audio" || kind === "video" ? kind : "document";
  const media = { id: mediaId };
  if (options.caption && key !== "audio") media.caption = String(options.caption).slice(0, 1024);
  if (key === "audio" && options.voice) media.voice = true;
  if (key === "document" && options.filename) media.filename = String(options.filename).slice(0, 240);
  return withQuote({
    messaging_product: "whatsapp",
    recipient_type: "individual",
    type: key,
    [key]: media,
    ...targetFields(target),
  }, options.replyTo);
}

export async function readRaw(request, limit = 262144) {
  const raw = new Uint8Array(await request.arrayBuffer());
  if (!raw.byteLength || raw.byteLength > limit) throw new Error("body too large");
  return raw;
}

function bearer(request) {
  return request.headers.get("Authorization")?.replace(/^Bearer /, "") || "";
}

function sessionToken() {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  let text = "";
  for (const byte of bytes) text += String.fromCharCode(byte);
  return btoa(text).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}

function claimToken() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  let text = "";
  for (const byte of bytes) text += String.fromCharCode(byte);
  return btoa(text).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}

function asPending(value) {
  if (value && typeof value === "object" && !Array.isArray(value)) return value;
  return { at: typeof value === "number" ? value : 0, claim: "", confirmed: false };
}

function agentToken(value) {
  return typeof value === "string" && value.length >= 1 && value.length <= 512 && !/\s/.test(value);
}

export async function whatsappRoute(request, env) {
  const url = new URL(request.url);
  if (url.pathname === "/whatsapp/start" && request.method === "GET") return openStart(request, env);
  if (url.pathname === "/whatsapp/webhook" && request.method === "POST") return receiveWebhook(request, env);
  if (url.pathname === "/whatsapp/register" && request.method === "POST") return registerAgent(request, env);
  if (url.pathname === "/whatsapp/diag" && request.method === "GET") {
    const inbox = env.WHATSAPP.get(env.WHATSAPP.idFromName("zoen"));
    return inbox.fetch("https://whatsapp/diag");
  }
  const token = bearer(request);
  if (!capability(token, 43)) return response({ error: "unauthorized" }, 403);
  const hash = await digest(token);
  const inbox = env.WHATSAPP.get(env.WHATSAPP.idFromName("zoen"));
  const headers = { "X-Secret-Hash": hash };
  if (url.pathname === "/whatsapp/inbox" && request.method === "GET") return inbox.fetch("https://whatsapp/", { headers });
  if (url.pathname === "/whatsapp/inbox/ack" && request.method === "POST") {
    return inbox.fetch("https://whatsapp/ack", { method: "POST", headers, body: await request.text() });
  }
  if (url.pathname === "/whatsapp/send" && request.method === "POST") return sendWhatsapp(request, env, inbox, headers);
  if (url.pathname === "/whatsapp/media" && request.method === "GET") return downloadMedia(request, env, inbox, headers);
  if (url.pathname === "/whatsapp/release" && request.method === "POST") {
    return inbox.fetch("https://whatsapp/release", { method: "POST", headers });
  }
  return null;
}

async function receiveWebhook(request, env) {
  if (!env.KAPSO_WEBHOOK_SECRET) return response({ error: "whatsapp_not_configured" }, 503);
  const raw = await readRaw(request);
  if (!await verifySignature(raw, request.headers.get("X-Webhook-Signature") || "", env.KAPSO_WEBHOOK_SECRET)) {
    return response({ error: "unauthorized" }, 401);
  }
  const payload = JSON.parse(new TextDecoder().decode(raw));
  const messages = inboundMessages(request.headers.get("X-Webhook-Event") || "", payload);
  const key = String(request.headers.get("X-Idempotency-Key") || "").slice(0, 128);
  const inbox = env.WHATSAPP.get(env.WHATSAPP.idFromName("zoen"));
  const planned = await inbox.fetch("https://whatsapp/ingest", {
    method: "POST",
    body: JSON.stringify({ key, messages }),
  });
  const plan = await planned.json();
  if (!planned.ok) return response(plan, planned.status);
  if (plan.duplicate) return response(plan);
  const failed = [];
  for (const setup of plan.setups || []) {
    const phone = setup.phone || setup;
    const claim = setup.claim || "";
    const url = claim ? `${SETUP_URL}?c=${encodeURIComponent(claim)}` : SETUP_URL;
    if (!await deliver(env, setupMessage({ to: phone }, url))) failed.push(phone);
  }
  if (failed.length) {
    await inbox.fetch("https://whatsapp/forget-setup", {
      method: "POST",
      body: JSON.stringify({ key, phones: failed }),
    });
    return response({ error: "whatsapp_send_failed" }, 502);
  }
  return response({ ok: true, setup: (plan.setups || []).length > 0 });
}

async function openStart(request, env) {
  const claim = new URL(request.url).searchParams.get("c") || "";
  if (/^[A-Za-z0-9_-]{16,64}$/.test(claim)) {
    const inbox = env.WHATSAPP.get(env.WHATSAPP.idFromName("zoen"));
    await inbox.fetch("https://whatsapp/confirm", {
      method: "POST",
      body: JSON.stringify({ claim }),
    });
  }
  return startPage();
}

async function registerAgent(request, env) {
  const token = bearer(request);
  if (!agentToken(token)) {
    await remember(env, { stage: "token", status: 403, uid_len: token.length });
    return response({ error: "unauthorized" }, 403);
  }
  let body = {};
  try {
    if (request.headers.get("content-length") !== "0") body = await request.json();
  } catch {
    return response({ error: "invalid_phone" }, 400);
  }
  if (body?.phone && !digits(body.phone)) return response({ error: "invalid_phone" }, 400);
  let agent = "";
  let secretHash = "";
  if (token === "proxied") {
    // The exe proxy keeps the real credential. The VM reads its own uid from
    // that proxy and proves continuity with a secret that stays on its volume.
    agent = String(body?.agent_uid || "");
    const secret = String(body?.secret || "");
    if (!/^[a-f0-9]{32}$/.test(agent) || !/^[A-Za-z0-9_-]{43,128}$/.test(secret)) {
      await remember(env, { stage: "uid", status: 403, uid_len: agent.length });
      return response({ error: "unauthorized" }, 403);
    }
    secretHash = await digest(secret);
  } else {
    const me = await plowGet(env, token, "/v1/agents/me");
    if (!me || typeof me !== "object" || Array.isArray(me)) {
      await remember(env, { stage: "me", status: 403, error: "me_rejected" });
      return response({ error: "unauthorized" }, 403);
    }
    agent = String(me.agent?.uid || me.uid || "");
  }
  if (!/^[A-Za-z0-9_-]{4,128}$/.test(agent)) {
    await remember(env, { stage: "uid", status: 403, uid_len: agent.length });
    return response({ error: "unauthorized" }, 403);
  }
  const session = sessionToken();
  const inbox = env.WHATSAPP.get(env.WHATSAPP.idFromName("zoen"));
  const bound = await inbox.fetch("https://whatsapp/bind", {
    method: "POST",
    body: JSON.stringify({
      phone: digits(body?.phone),
      claim: String(body?.claim || ""),
      agent,
      secretHash,
      code: pairingCode(body?.code),
      hash: await digest(session),
    }),
  });
  const data = await bound.json();
  await remember(env, { stage: "bind", status: bound.status, error: data.error || "" });
  if (data.waiting) return response({ ok: true, waiting: true });
  if (!bound.ok) return response(data, bound.status);
  return response({ ok: true, token: session });
}

async function remember(env, note) {
  try {
    const inbox = env.WHATSAPP.get(env.WHATSAPP.idFromName("zoen"));
    await inbox.fetch("https://whatsapp/note", {
      method: "POST",
      body: JSON.stringify({ ...note, at: Date.now() }),
    });
  } catch {
    // The register response must not depend on the diagnostic note.
  }
}

async function plowGet(env, token, path) {
  const base = String(env.PLOW_API_BASE || "https://api.plow.co").replace(/\/$/, "");
  try {
    const result = await fetch(`${base}${path}`, {
      headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
    });
    if (!result.ok) {
      console.log(JSON.stringify({ whatsapp_me: result.status, len: token.length, alpha: /^[A-Za-z]+$/.test(token) }));
      return null;
    }
    const body = await result.json();
    return body ?? null;
  } catch {
    return null;
  }
}

const MEDIA_MIME = {
  "image/jpeg": "image",
  "image/png": "image",
  "image/webp": "image",
  "audio/ogg": "audio",
  "audio/opus": "audio",
  "audio/mpeg": "audio",
  "audio/mp4": "audio",
  "audio/aac": "audio",
  "video/mp4": "video",
  "application/pdf": "document",
};

function decodeMedia(spec) {
  const mime = String(spec?.mime || "").toLowerCase();
  const kind = MEDIA_MIME[mime];
  const raw = String(spec?.data || "");
  if (!kind || !raw || raw.length > 12_000_000) return null;
  let bytes;
  try {
    bytes = Uint8Array.from(atob(raw), (char) => char.charCodeAt(0));
  } catch {
    return null;
  }
  const limit = kind === "image" ? 5_000_000 : 16_000_000;
  if (!bytes.byteLength || bytes.byteLength > limit) return null;
  return { mime: mime === "audio/opus" ? "audio/ogg" : mime, kind, bytes, name: String(spec.name || "file").slice(0, 240), voice: spec.voice === true && (mime === "audio/ogg" || mime === "audio/opus") };
}

async function uploadMedia(env, file) {
  const base = String(env.KAPSO_API_BASE || "https://api.kapso.ai/meta/whatsapp/v24.0").replace(/\/$/, "");
  const form = new FormData();
  form.set("messaging_product", "whatsapp");
  form.set("file", new File([file.bytes], file.name, { type: file.mime }));
  const result = await fetch(`${base}/${env.KAPSO_PHONE_NUMBER_ID}/media`, {
    method: "POST",
    headers: { "X-API-Key": env.KAPSO_API_KEY },
    body: form,
  });
  if (!result.ok) return "";
  const payload = await result.json();
  return String(payload?.id || "");
}

async function sendWhatsapp(request, env, inbox, headers) {
  if (!env.KAPSO_API_KEY || !env.KAPSO_PHONE_NUMBER_ID) return response({ error: "whatsapp_not_configured" }, 503);
  const body = await request.json();
  const to = digits(body.to);
  const recipient = to ? "" : String(body.recipient || "").slice(0, 128);
  if (!to && !recipient) return response({ error: "invalid_message" }, 400);
  if (to) {
    const allowed = await inbox.fetch("https://whatsapp/allow", {
      method: "POST",
      headers,
      body: JSON.stringify({ to }),
    });
    if (!allowed.ok) return allowed;
  }
  const target = { to: to || null, recipient: recipient || null };
  let payload = null;
  if (body.reaction && typeof body.reaction === "object") {
    payload = reactionBody(target, body.reaction.message_id, body.reaction.type);
  } else if (body.media && typeof body.media === "object") {
    const file = decodeMedia(body.media);
    const mediaId = file ? await uploadMedia(env, file) : "";
    payload = mediaId ? mediaBody(target, file.kind, mediaId, {
      caption: body.text, voice: file.voice, filename: file.name, replyTo: body.reply_to,
    }) : null;
  } else {
    const text = String(body.text || "").trim().slice(0, TEXT_LIMIT);
    payload = text ? kapsoBody(target, text, body.reply_to) : null;
  }
  if (!payload) return response({ error: "invalid_message" }, 400);
  if (!await deliver(env, payload)) return response({ error: "whatsapp_send_failed" }, 502);
  return response({ ok: true });
}

function mediaUrlAllowed(value) {
  try {
    const url = new URL(value);
    if (url.protocol === "https:") return true;
    return url.protocol === "http:" && (url.hostname === "127.0.0.1" || url.hostname === "localhost");
  } catch {
    return false;
  }
}

async function downloadMedia(request, env, inbox, headers) {
  if (!env.KAPSO_API_KEY || !env.KAPSO_PHONE_NUMBER_ID) return response({ error: "whatsapp_not_configured" }, 503);
  const known = await inbox.fetch("https://whatsapp/", { headers });
  if (!known.ok) return response({ error: "unauthorized" }, 403);
  const id = new URL(request.url).searchParams.get("id") || "";
  if (!/^[A-Za-z0-9_-]{6,256}$/.test(id)) return response({ error: "invalid_message" }, 400);
  const base = String(env.KAPSO_API_BASE || "https://api.kapso.ai/meta/whatsapp/v24.0").replace(/\/$/, "");
  try {
    const meta = await fetch(`${base}/${id}?phone_number_id=${env.KAPSO_PHONE_NUMBER_ID}`, {
      headers: { "X-API-Key": env.KAPSO_API_KEY, Accept: "application/json" },
    });
    if (!meta.ok) return response({ error: "whatsapp_media_failed" }, 502);
    const described = await meta.json();
    const url = String(described?.url || "");
    if (!mediaUrlAllowed(url)) return response({ error: "whatsapp_media_failed" }, 502);
    const file = await fetch(url, { headers: { "X-API-Key": env.KAPSO_API_KEY } });
    if (!file.ok) return response({ error: "whatsapp_media_failed" }, 502);
    const bytes = new Uint8Array(await file.arrayBuffer());
    if (!bytes.byteLength || bytes.byteLength > 16_000_000) return response({ error: "invalid_message" }, 400);
    const mime = String(described.mime_type || file.headers.get("content-type") || "application/octet-stream").slice(0, 80);
    return new Response(bytes, { headers: { "content-type": mime, "cache-control": "no-store" } });
  } catch {
    return response({ error: "whatsapp_media_failed" }, 502);
  }
}

async function deliver(env, payload) {
  if (!env.KAPSO_API_KEY || !env.KAPSO_PHONE_NUMBER_ID) return false;
  const base = String(env.KAPSO_API_BASE || "https://api.kapso.ai/meta/whatsapp/v24.0").replace(/\/$/, "");
  try {
    const result = await fetch(`${base}/${env.KAPSO_PHONE_NUMBER_ID}/messages`, {
      method: "POST",
      headers: { "X-API-Key": env.KAPSO_API_KEY, "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return result.ok;
  } catch {
    return false;
  }
}

function emptyBox() {
  return { seen: [], pending: {}, bindings: {}, queues: {}, codes: {}, heard: {} };
}

function pairingCode(value) {
  const code = String(value || "").trim();
  return /^\d{6}$/.test(code) ? code : "";
}

function phoneThatSent(box, code) {
  for (const phone of Object.keys(box.queues || {})) {
    if ((box.queues[phone] || []).some((item) => pairingCode(item.text) === code)) return phone;
  }
  return "";
}

export class WhatsAppInbox {
  constructor(ctx, env) { this.ctx = ctx; this.env = env; }

  async fetch(request) {
    return this.ctx.blockConcurrencyWhile(async () => {
      const path = new URL(request.url).pathname;
      let box = await this.ctx.storage.get("box");
      const now = Date.now();
      box = normalize(box, now);
      if (path === "/ingest") return this.ingest(box, await request.json(), now);
      if (path === "/forget-setup") return this.forgetSetup(box, await request.json());
      if (path === "/confirm") return this.confirm(box, await request.json());
      if (path === "/bind") return this.bind(box, await request.json());
      if (path === "/note" && request.method === "POST") return this.note(box, await request.json());
      if (path === "/diag" && request.method === "GET") return this.diag(box);
      if (path === "/allow") return this.allow(box, request.headers.get("X-Secret-Hash"), await request.json());
      if (path === "/release" && request.method === "POST") return this.release(box, request.headers.get("X-Secret-Hash"));
      const phone = phoneFor(box, request.headers.get("X-Secret-Hash"));
      if (!phone) return response({ error: "unauthorized" }, 403);
      if (path === "/" && request.method === "GET") {
        return response({ messages: (box.queues[phone] || []).slice(0, 20).map(({ at, ...message }) => message) });
      }
      if (path === "/ack" && request.method === "POST") return this.ack(box, phone, await request.json());
      return response({ error: "not_found" }, 404);
    });
  }

  async ingest(box, body, now) {
    if (body.key && box.seen.includes(body.key)) return response({ ok: true, duplicate: true, setups: [] });
    const setups = [];
    for (const message of body.messages || []) {
      const phone = message?.to;
      if (!phone) continue;
      const queue = box.queues[phone] || [];
      if (!queue.some((item) => item.id === message.id)) {
        queue.push({ ...message, at: now });
        box.queues[phone] = queue.filter((item) => item.at > now - HOLD_MS).slice(-QUEUE_LIMIT);
      }
      const code = pairingCode(message.text);
      if (code && box.codes[code]) box.heard[code] = phone;
      if (box.bindings[phone]) continue;
      // The SMS onboarding already confirmed this phone. The code just links WhatsApp.
      if (code && box.codes[code]) continue;
      const pending = asPending(box.pending[phone]);
      if (!pending.claim) pending.claim = claimToken();
      const due = !pending.at || now - pending.at >= SETUP_COOLDOWN_MS;
      if (due) {
        pending.at = now;
        setups.push({ phone, claim: pending.claim });
      }
      box.pending[phone] = pending;
    }
    if (body.key) box.seen = [...box.seen, body.key].slice(-500);
    await this.ctx.storage.put("box", box);
    await this.ctx.storage.setAlarm(now + HOLD_MS);
    return response({ ok: true, setups });
  }

  async forgetSetup(box, body) {
    for (const phone of body.phones || []) delete box.pending[digits(phone)];
    if (body.key) box.seen = box.seen.filter((key) => key !== body.key);
    await this.ctx.storage.put("box", box);
    return response({ ok: true });
  }

  async confirm(box, body) {
    const claim = String(body.claim || "");
    const phone = Object.keys(box.pending).find((key) => asPending(box.pending[key]).claim === claim);
    if (phone) {
      const pending = asPending(box.pending[phone]);
      pending.confirmed = true;
      box.pending[phone] = pending;
      await this.ctx.storage.put("box", box);
    }
    return response({ ok: true });
  }

  async bind(box, body) {
    const agent = String(body.agent || "");
    const hash = String(body.hash || "");
    const code = pairingCode(body.code);
    if (!/^[a-f0-9]{64}$/.test(hash)) return response({ error: "unauthorized" }, 403);
    const owned = Object.keys(box.bindings).filter((key) => box.bindings[key].agent === agent);
    if (owned.length > 1) return response({ error: "ambiguous" }, 409);
    let phone = "";
    if (owned.length === 1) {
      phone = owned[0];
    } else if (code) {
      const existing = box.codes[code];
      if (existing && existing.agent !== agent) return response({ error: "code_taken" }, 409);
      box.codes[code] = { agent, secretHash: String(body.secretHash || ""), at: Date.now() };
      phone = box.heard[code] || phoneThatSent(box, code);
      if (!phone) {
        await this.ctx.storage.put("box", box);
        return response({ waiting: true });
      }
    } else {
      return response({ error: "not_waiting" }, 404);
    }
    const current = box.bindings[phone];
    const secretHash = String(body.secretHash || "");
    if (current && current.agent !== agent) return response({ error: "already_bound" }, 409);
    if (current?.secretHash && current.secretHash !== secretHash) return response({ error: "unauthorized" }, 403);
    box.bindings[phone] = {
      hash,
      agent,
      ...(current?.secretHash || secretHash ? { secretHash: secretHash || current.secretHash } : {}),
    };
    box.queues[phone] = box.queues[phone] || [];
    delete box.pending[phone];
    await this.ctx.storage.put("box", box);
    return response({ ok: true, fresh: !current, phone });
  }

  async note(box, body) {
    box.note = {
      at: Number(body.at) || Date.now(),
      stage: String(body.stage || "").slice(0, 16),
      status: Number(body.status) || 0,
      error: String(body.error || "").slice(0, 40),
      uid_len: Number(body.uid_len) || 0,
    };
    await this.ctx.storage.put("box", box);
    return response({ ok: true });
  }

  diag(box) {
    const queued = Object.values(box.queues).reduce((sum, queue) => sum + (queue?.length || 0), 0);
    return response({
      pending: Object.keys(box.pending).length,
      bindings: Object.keys(box.bindings).length,
      queued,
      note: box.note || null,
    });
  }

  async release(box, hash) {
    const phone = phoneFor(box, hash);
    if (!phone) return response({ error: "unauthorized" }, 403);
    const agent = box.bindings[phone]?.agent || "";
    if (agent) {
      for (const code of Object.keys(box.codes)) {
        if (box.codes[code].agent === agent) delete box.codes[code];
      }
    }
    for (const code of Object.keys(box.heard)) {
      if (samePhone(box.heard[code], phone)) delete box.heard[code];
    }
    for (const key of Object.keys(box.bindings)) {
      if (samePhone(key, phone)) delete box.bindings[key];
    }
    for (const key of Object.keys(box.pending)) {
      if (samePhone(key, phone)) delete box.pending[key];
    }
    for (const key of Object.keys(box.queues)) {
      if (samePhone(key, phone)) delete box.queues[key];
    }
    await this.ctx.storage.put("box", box);
    return response({ ok: true });
  }

  async allow(box, hash, body) {
    const phone = phoneFor(box, hash);
    if (!phone || !samePhone(phone, digits(body.to))) return response({ error: "unauthorized" }, 403);
    return response({ ok: true });
  }

  async ack(box, phone, body) {
    const ids = new Set(Array.isArray(body.ids) ? body.ids.map((id) => String(id)) : []);
    box.queues[phone] = (box.queues[phone] || []).filter((item) => !ids.has(item.id));
    await this.ctx.storage.put("box", box);
    return response({ ok: true, queued: box.queues[phone].length });
  }

  async alarm() {
    const box = normalize(await this.ctx.storage.get("box"), Date.now());
    await this.ctx.storage.put("box", box);
    if (Object.values(box.queues).some((queue) => queue.length)) await this.ctx.storage.setAlarm(Date.now() + HOLD_MS);
  }
}

function normalize(box, now) {
  if (!box || !box.queues || !box.bindings || !box.pending) box = emptyBox();
  if (!box.codes) box.codes = {};
  if (!box.heard) box.heard = {};
  for (const phone of Object.keys(box.queues)) {
    box.queues[phone] = box.queues[phone].filter((item) => item.at > now - HOLD_MS);
  }
  for (const code of Object.keys(box.codes)) {
    if ((box.codes[code]?.at || 0) <= now - HOLD_MS) delete box.codes[code];
  }
  return box;
}

function phoneFor(box, hash) {
  if (!hash) return "";
  return Object.keys(box.bindings).find((phone) => box.bindings[phone].hash === hash) || "";
}
