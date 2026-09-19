import { page } from "./page.js";

const HEADERS = {
  "Cache-Control": "no-store",
  "Referrer-Policy": "no-referrer",
  "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
  "X-Content-Type-Options": "nosniff",
};
const ASSETS = new Set(["/style.css", "/sky-midnight.webp", "/zoen-avatar.webp"]);
const capability = (value, min = 32) => typeof value === "string"
  && value.length >= min && value.length <= 256 && /^[A-Za-z0-9_-]+$/.test(value);
const response = (data, status = 200) => Response.json(data, { status, headers: HEADERS });
const digest = async (value) => Array.from(new Uint8Array(
  await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value)),
), (byte) => byte.toString(16).padStart(2, "0")).join("");

async function readBody(request) {
  if (!request.headers.get("Content-Type")?.startsWith("application/json")) throw new Error("json required");
  const reader = request.body?.getReader();
  if (!reader) throw new Error("body required");
  let text = "", size = 0;
  const decoder = new TextDecoder();
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.length;
      if (size > 4096) throw new Error("body too large");
      text += decoder.decode(value, { stream: true });
    }
    return JSON.parse(text + decoder.decode());
  } finally {
    await reader.cancel();
  }
}

function callbackFrom(url) {
  if (url.search.length > 16384) throw new Error("callback too large");
  const params = url.searchParams;
  for (const key of ["state", "code", "error", "iss"]) {
    if (params.getAll(key).length > 1) throw new Error("duplicate parameter");
  }
  const state = params.get("state"), code = params.get("code"), error = params.get("error");
  if (!capability(state) || Boolean(code) === Boolean(error)) throw new Error("invalid callback");
  if ((code?.length || 0) > 8192 || (error?.length || 0) > 256 || (params.get("iss")?.length || 0) > 2048) {
    throw new Error("callback too large");
  }
  return { state, code, error, iss: params.get("iss") };
}

async function receiveCallback(url, env) {
  const callback = callbackFrom(url);
  const object = env.FLOWS.get(env.FLOWS.idFromName(await digest(callback.state)));
  const result = await object.fetch("https://flow/callback", { method: "POST", body: JSON.stringify(callback) });
  if (result.status === 410) return page("expired", HEADERS, 410);
  if (result.status === 409) return page("used", HEADERS, 409);
  if (!result.ok) return page("invalid", HEADERS, result.status);
  return page(callback.error ? "denied" : "received", HEADERS);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/health" && request.method === "GET") return response({ ok: true, version: 1 });
    if (url.pathname === "/" && request.method === "GET") return page("welcome", HEADERS);
    if (ASSETS.has(url.pathname) && ["GET", "HEAD"].includes(request.method)) {
      const asset = await env.ASSETS.fetch(new Request(new URL(url.pathname, url.origin), { method: request.method }));
      const result = new Response(asset.body, asset);
      for (const [name, value] of Object.entries(HEADERS)) result.headers.set(name, value);
      return result;
    }
    try {
      if (url.pathname === "/flows" && request.method === "POST") {
        const { success } = await env.CREATE_LIMITER.limit({ key: request.headers.get("CF-Connecting-IP") || "local" });
        if (!success) return response({ error: "rate_limited" }, 429);
        const body = await readBody(request);
        if (!capability(body.state) || !capability(body.poll_token, 43)) return response({ error: "invalid_flow" }, 400);
        const id = await digest(body.state);
        const object = env.FLOWS.get(env.FLOWS.idFromName(id));
        return object.fetch("https://flow/register", { method: "POST", body: JSON.stringify({
          state: body.state, secretHash: await digest(body.poll_token),
        }) });
      }
      if (url.pathname === "/callback" && request.method === "GET") {
        return await receiveCallback(url, env);
      }
      const match = /^\/flows\/([a-f0-9]{64})(\/ack)?$/.exec(url.pathname);
      if (match) {
        const token = request.headers.get("Authorization")?.replace(/^Bearer /, "");
        if (!capability(token, 43)) return response({ error: "unauthorized" }, 403);
        const object = env.FLOWS.get(env.FLOWS.idFromName(match[1]));
        return object.fetch(`https://flow${match[2] || "/"}`, {
          method: request.method, headers: { "X-Secret-Hash": await digest(token) },
        });
      }
      return response({ error: "not_found" }, 404);
    } catch {
      // Never log callback URLs, request bodies or authorization headers.
      if (url.pathname === "/callback") return page("invalid", HEADERS, 400);
      return response({ error: "invalid_request" }, 400);
    }
  },
};

export class OAuthFlow {
  constructor(ctx, env) { this.ctx = ctx; this.env = env; }

  async fetch(request) {
    return this.ctx.blockConcurrencyWhile(async () => {
      const path = new URL(request.url).pathname;
      let flow = await this.ctx.storage.get("flow");
      if (flow && flow.expires <= Date.now()) {
        await this.ctx.storage.deleteAll();
        flow = null;
      }
      if (path === "/register") {
        const body = await request.json();
        if (flow) return response({ status: flow.status, expires_at: flow.expires }, flow.secretHash === body.secretHash ? 200 : 409);
        const ttl = Math.min(600, Math.max(1, Number(this.env.FLOW_TTL_SECONDS) || 300));
        flow = { ...body, expires: Date.now() + ttl * 1000, status: "pending" };
        await this.ctx.storage.put("flow", flow);
        await this.ctx.storage.setAlarm(flow.expires);
        return response({ status: flow.status, expires_at: flow.expires }, 201);
      }
      if (!flow) return response({ error: "expired_or_unknown" }, 410);
      if (path === "/callback") {
        const callback = await request.json();
        if (flow.status === "ready" && JSON.stringify(flow.callback) === JSON.stringify(callback)) return response({ ok: true });
        if (flow.status !== "pending" || callback.state !== flow.state) return response({ error: "already_used" }, 409);
        flow.callback = callback;
        flow.status = "ready";
        await this.ctx.storage.put("flow", flow);
        return response({ ok: true });
      }
      if (request.headers.get("X-Secret-Hash") !== flow.secretHash) return response({ error: "unauthorized" }, 403);
      if (path === "/" && request.method === "GET") return response({ status: flow.status, callback: flow.callback });
      if ((path === "/ack" && request.method === "POST") || (path === "/" && request.method === "DELETE")) {
        if (path === "/ack" && flow.status === "pending") return response({ error: "not_ready" }, 409);
        delete flow.callback;
        flow.status = path === "/ack" ? "consumed" : "cancelled";
        await this.ctx.storage.put("flow", flow);
        return response({ status: flow.status });
      }
      return response({ error: "not_found" }, 404);
    });
  }

  async alarm() { await this.ctx.storage.deleteAll(); }
}
