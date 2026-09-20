import { capability, digest, readBody, response } from "./http.js";

const PREFIX = "https://www.googleapis.com/auth/";
// Each capability is requested only for the owner's current task. Google
// enforces its test-user restrictions and unverified-app authorization limits.
export const CAPABILITIES = {
  identity: [],
  calendar_read: ["calendar.events.readonly", "calendar.calendarlist.readonly"],
  calendar_write: ["calendar.events", "calendar.calendarlist.readonly"],
  gmail_read: ["gmail.readonly"],
  gmail_send: ["gmail.send"],
  drive_files: ["drive.file"],
  drive_read: ["drive.readonly"],
  contacts_read: ["contacts.readonly"],
  sheets_read: ["spreadsheets.readonly"],
  sheets_write: ["spreadsheets"],
  docs_read: ["documents.readonly"],
  docs_write: ["documents"],
};
const encode = (bytes) => btoa(String.fromCharCode(...new Uint8Array(bytes))).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
const decode = (text) => Uint8Array.from(atob(text.replaceAll("-", "+").replaceAll("_", "/")), (char) => char.charCodeAt(0));

function enabled(env) {
  return (env.GOOGLE_ENABLED_CAPABILITIES || "").split(",").filter((name) => Object.hasOwn(CAPABILITIES, name));
}

export function configured(env) {
  return Boolean(env.GOOGLE_CLIENT_ID?.endsWith(".apps.googleusercontent.com")
    && env.GOOGLE_CLIENT_SECRET && /^[a-f0-9]{64}$/.test(env.GOOGLE_ENCRYPTION_KEY || "")
    && ["testing", "unverified", "verified"].includes(env.GOOGLE_AUTH_MODE)
    && /^https:\/\/[^/?#]+\/callback$/.test(env.GOOGLE_REDIRECT_URI || "") && enabled(env).length);
}

async function key(env) {
  const bytes = Uint8Array.from(env.GOOGLE_ENCRYPTION_KEY.match(/../g), (part) => parseInt(part, 16));
  return crypto.subtle.importKey("raw", bytes, "AES-GCM", false, ["encrypt", "decrypt"]);
}

export async function seal(data, purpose, env) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const additionalData = new TextEncoder().encode(`zoen:${purpose}:${env.GOOGLE_CLIENT_ID}`);
  const encrypted = await crypto.subtle.encrypt({ name: "AES-GCM", iv, additionalData }, await key(env),
    new TextEncoder().encode(JSON.stringify(data)));
  return `${encode(iv)}.${encode(encrypted)}`;
}

export async function unseal(value, purpose, env) {
  if (typeof value !== "string" || value.length > 16384 || !/^[\w-]+\.[\w-]+$/.test(value)) throw new Error("invalid_handle");
  const [iv, data] = value.split(".").map(decode);
  const additionalData = new TextEncoder().encode(`zoen:${purpose}:${env.GOOGLE_CLIENT_ID}`);
  const plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv, additionalData }, await key(env), data);
  return JSON.parse(new TextDecoder().decode(plain));
}

async function tokenRequest(params, env, http) {
  const result = await http("https://oauth2.googleapis.com/token", {
    method: "POST", redirect: "error", signal: AbortSignal.timeout(10000),
    body: new URLSearchParams({ ...params, client_id: env.GOOGLE_CLIENT_ID, client_secret: env.GOOGLE_CLIENT_SECRET }),
  });
  const data = await result.json();
  if (!result.ok) throw new Error(data.error === "invalid_grant" ? "google_reauthorization_required" : "google_token_exchange_failed");
  if (typeof data.access_token !== "string" || data.token_type?.toLowerCase() !== "bearer"
    || !Number.isFinite(data.expires_in) || data.expires_in <= 0) throw new Error("invalid_google_token");
  return data;
}

async function credentials(tokens, env, previous) {
  const scopes = typeof tokens.scope === "string" ? tokens.scope.split(" ").filter(Boolean) : previous?.scopes || [];
  const refresh = tokens.refresh_token || previous?.refresh_token;
  if (!refresh) throw new Error("google_offline_access_required");
  return {
    access_token: tokens.access_token,
    expires_at: Date.now() + tokens.expires_in * 1000,
    scopes,
    refresh_handle: await seal({ refresh_token: refresh, scopes }, "refresh", env),
  };
}

async function register(request, env) {
  const { success } = await env.CREATE_LIMITER.limit({ key: request.headers.get("CF-Connecting-IP") || "local" });
  if (!success) return response({ error: "rate_limited" }, 429);
  const body = await readBody(request);
  if (!capability(body.state) || !capability(body.poll_token, 43) || !/^[\w-]{43}$/.test(body.code_challenge || "")) {
    return response({ error: "invalid_google_flow" }, 400);
  }
  const requested = body.capabilities;
  if (!Array.isArray(requested) || !requested.length || requested.some((name) => !enabled(env).includes(name))) {
    return response({ error: "google_capability_not_enabled", enabled_capabilities: enabled(env) }, 403);
  }
  const scopes = [...new Set(["openid", "email", ...requested.flatMap((name) => CAPABILITIES[name].map((scope) => PREFIX + scope))])];
  const id = await digest(body.state);
  const object = env.FLOWS.get(env.FLOWS.idFromName(id));
  const saved = await object.fetch("https://flow/register", { method: "POST", body: JSON.stringify({
    state: body.state, secretHash: await digest(body.poll_token), provider: "google", challenge: body.code_challenge,
  }) });
  if (!saved.ok) return saved;
  const url = new URL("https://accounts.google.com/o/oauth2/v2/auth");
  url.search = new URLSearchParams({
    client_id: env.GOOGLE_CLIENT_ID, redirect_uri: env.GOOGLE_REDIRECT_URI, response_type: "code",
    scope: scopes.join(" "), state: body.state, code_challenge: body.code_challenge, code_challenge_method: "S256",
    access_type: "offline", include_granted_scopes: "true", prompt: "consent select_account",
  }).toString();
  return response({ ...(await saved.json()), authorization_url: url.href, flow_id: id, scopes,
    auth_mode: env.GOOGLE_AUTH_MODE }, saved.status);
}

// Called inside the existing Durable Object's concurrency lock. Delivery can be
// retried after a lost HTTP response without redeeming Google's code twice.
export async function exchangeGoogleFlow(request, env, ctx, flow, http = fetch) {
  if (flow.provider !== "google") return response({ error: "wrong_provider" }, 400);
  const body = await request.json();
  if (!/^[\w-]{43,128}$/.test(body.code_verifier || "")) return response({ error: "invalid_verifier" }, 403);
  const challenge = encode(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(body.code_verifier)));
  if (challenge !== flow.challenge) return response({ error: "invalid_verifier" }, 403);
  if (flow.delivery) return response(await unseal(flow.delivery, "delivery", env));
  if (flow.status !== "ready" || !flow.callback?.code) return response({ error: "authorization_not_ready" }, 409);
  if (flow.callback.iss && flow.callback.iss !== "https://accounts.google.com") return response({ error: "wrong_issuer" }, 400);
  let result;
  try {
    const tokens = await tokenRequest({ grant_type: "authorization_code", code: flow.callback.code,
      code_verifier: body.code_verifier, redirect_uri: env.GOOGLE_REDIRECT_URI }, env, http);
    result = await credentials(tokens, env);
  } catch (error) {
    if (error.message === "google_reauthorization_required" || error.message === "google_offline_access_required") {
      return response({ error: error.message }, 400);
    }
    return response({ error: "google_exchange_unavailable" }, 503);
  }
  flow.delivery = await seal(result, "delivery", env);
  delete flow.callback;
  flow.status = "exchanged";
  await ctx.storage.put("flow", flow);
  return response(result);
}

export async function refreshGoogle(body, env, http = fetch) {
  let previous;
  try { previous = await unseal(body.refresh_handle, "refresh", env); }
  catch { throw new Error("invalid_handle"); }
  const tokens = await tokenRequest({ grant_type: "refresh_token", refresh_token: previous.refresh_token }, env, http);
  return credentials(tokens, env, previous);
}

export async function googleRoute(request, env) {
  const path = new URL(request.url).pathname;
  if (path === "/google/config" && request.method === "GET") {
    return response({ configured: configured(env), capabilities: configured(env) ? enabled(env) : [],
      auth_mode: configured(env) ? env.GOOGLE_AUTH_MODE : "disabled" });
  }
  if (!configured(env)) return response({ error: "google_operator_setup_required" }, 503);
  if (path === "/google/flows" && request.method === "POST") return register(request, env);
  const match = /^\/google\/flows\/([a-f0-9]{64})\/exchange$/.exec(path);
  if (match && request.method === "POST") {
    const token = request.headers.get("Authorization")?.replace(/^Bearer /, "");
    if (!capability(token, 43)) return response({ error: "unauthorized" }, 403);
    const body = await readBody(request);
    const object = env.FLOWS.get(env.FLOWS.idFromName(match[1]));
    return object.fetch("https://flow/google/exchange", { method: "POST", body: JSON.stringify(body),
      headers: { "X-Secret-Hash": await digest(token) } });
  }
  if (path === "/google/refresh" && request.method === "POST") {
    const { success } = await env.CREATE_LIMITER.limit({ key: request.headers.get("CF-Connecting-IP") || "local" });
    if (!success) return response({ error: "rate_limited" }, 429);
    try { return response(await refreshGoogle(await readBody(request), env)); }
    catch (error) {
      if (["invalid_handle", "google_reauthorization_required"].includes(error.message)) {
        return response({ error: error.message }, 401);
      }
      return response({ error: "google_refresh_unavailable" }, 503);
    }
  }
  return response({ error: "not_found" }, 404);
}
