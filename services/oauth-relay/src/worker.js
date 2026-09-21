import { page } from "./page.js";

import { HEADERS, capability, response, digest, readBody } from "./http.js";
import { googleRoute, exchangeGoogleFlow } from "./google.js";
import { whatsappRoute, WhatsAppInbox } from "./whatsapp.js";

export { WhatsAppInbox };
const ASSETS = new Set(["/style.css", "/sky-midnight.webp", "/zoen-avatar.webp"]);

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
    if (["/", "/privacy", "/terms"].includes(url.pathname) && request.method === "GET") {
      return page(url.pathname.slice(1) || "welcome", HEADERS);
    }
    if (ASSETS.has(url.pathname) && ["GET", "HEAD"].includes(request.method)) {
      const asset = await env.ASSETS.fetch(new Request(new URL(url.pathname, url.origin), { method: request.method }));
      const result = new Response(asset.body, asset);
      for (const [name, value] of Object.entries(HEADERS)) result.headers.set(name, value);
      return result;
    }
    try {
      if (url.pathname.startsWith("/google/")) return await googleRoute(request, env);
      if (url.pathname.startsWith("/whatsapp/")) {
        const result = await whatsappRoute(request, env);
        if (result) return result;
      }
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
      if (path === "/register") return this.register(await request.json(), flow);
      if (!flow) return response({ error: "expired_or_unknown" }, 410);
      if (path === "/callback") {
        const callback = await request.json();
        if (callback.state !== flow.state) return response({ error: "already_used" }, 409);
        if (flow.status === "ready" && JSON.stringify(flow.callback) === JSON.stringify(callback)) return response({ ok: true });
        if (flow.status === "ready" && flow.callback?.code && callback.error) return response({ ok: true });
        if (flow.status !== "pending") return response({ error: "already_used" }, 409);
        if (callback.error && !callback.code) {
          // Signup and account-picker hops often return error first. Keep the
          // attempt open so the same authorization URL can still deliver a code.
          flow.last_error = callback.error;
          await this.ctx.storage.put("flow", flow);
          return response({ ok: true });
        }
        flow.callback = callback;
        flow.status = "ready";
        await this.ctx.storage.put("flow", flow);
        return response({ ok: true });
      }
      if (request.headers.get("X-Secret-Hash") !== flow.secretHash) return response({ error: "unauthorized" }, 403);
      if (path === "/google/exchange" && request.method === "POST") {
        return exchangeGoogleFlow(request, this.env, this.ctx, flow);
      }
      if (path === "/" && request.method === "GET") return response({ status: flow.status, callback: flow.callback });
      if ((path === "/ack" && request.method === "POST") || (path === "/" && request.method === "DELETE")) {
        if (path === "/ack" && flow.status === "pending") return response({ error: "not_ready" }, 409);
        delete flow.callback;
        delete flow.delivery;
        flow.status = path === "/ack" ? "consumed" : "cancelled";
        await this.ctx.storage.put("flow", flow);
        return response({ status: flow.status });
      }
      return response({ error: "not_found" }, 404);
    });
  }

  async register(body, flow) {
    if (flow) {
      const same = flow.secretHash === body.secretHash && flow.provider === body.provider && flow.challenge === body.challenge;
      return response({ status: flow.status, expires_at: flow.expires }, same ? 200 : 409);
    }
    const ttl = Math.min(1800, Math.max(1, Number(this.env.FLOW_TTL_SECONDS) || 900));
    flow = { ...body, expires: Date.now() + ttl * 1000, status: "pending" };
    await this.ctx.storage.put("flow", flow);
    await this.ctx.storage.setAlarm(flow.expires);
    return response({ status: flow.status, expires_at: flow.expires }, 201);
  }

  async alarm() { await this.ctx.storage.deleteAll(); }
}
