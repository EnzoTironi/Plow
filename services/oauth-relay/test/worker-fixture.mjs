// Local test entry only; production deploys src/worker.js.
import worker, { OAuthFlow, WhatsAppInbox } from "../src/worker.js";
import { refreshGoogle, seal } from "../src/google.js";
export { OAuthFlow, WhatsAppInbox };

const kapsoPosts = [];

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === "/__fixture/kapso/posts" && request.method === "GET") return Response.json(kapsoPosts);
    if (url.pathname === "/__fixture/kapso/bytes/tiny") {
      return new Response(Uint8Array.from([0xff, 0xd8, 0xff, 0xd9]), { headers: { "content-type": "image/jpeg" } });
    }
    if (url.pathname.startsWith("/__fixture/kapso/")) {
      if (request.method === "GET" && url.pathname.endsWith("/media-jpeg")) {
        return Response.json({ url: "http://127.0.0.1:18791/__fixture/kapso/bytes/tiny", mime_type: "image/jpeg" });
      }
      if (request.method === "POST" && url.pathname.endsWith("/media")) {
        kapsoPosts.push({ upload: request.headers.get("content-type") || "" });
        return Response.json({ id: "uploaded-media" });
      }
      if (request.method === "POST") kapsoPosts.push(await request.json());
      return Response.json({ ok: true });
    }
    if (url.pathname === "/__fixture/plow/v1/agents/me") {
      const token = request.headers.get("Authorization") || "";
      if (token === "Bearer fixture-agent-token-34") {
        return Response.json({
          agent: { uid: "agt_lia" },
          chats: [{ participants: [{ role: "owner", provider_type: "imessage", provider_key: "+55 31 99994-1160" }] }],
        });
      }
      if (token === "Bearer fixture-agent-token-33") {
        return Response.json({
          agent: { uid: "agt_bia" },
          chats: [{ participants: [{ role: "owner", provider_type: "email", provider_key: "bia@example.com" }] }],
        });
      }
      if (token === "Bearer fixture-agent-token-35") {
        return Response.json({
          agent: { uid: "agt_cleo" },
          chats: [{ participants: [{ role: "owner", provider_type: "email", provider_key: "cleo@example.com" }] }],
        });
      }
      if (token !== "Bearer fixture-agent-token-32") return Response.json({ error: "unauthorized" }, { status: 401 });
      return Response.json({
        agent: { uid: "agt_ana" },
        chats: [{ participants: [{ role: "owner", provider_key: "+5511999999999" }] }],
      });
    }
    if (url.pathname === "/__fixture/plow/v1/contacts") {
      const token = request.headers.get("Authorization") || "";
      if (token === "Bearer fixture-agent-token-33") {
        return Response.json([{ role: "owner", provider_key: "+5511777777777" }]);
      }
      return Response.json([]);
    }
    if (url.pathname !== "/__fixture/google-runtime") return worker.fetch(request, env, ctx);
    const refresh_handle = await seal({ refresh_token: "fixture-refresh", scopes: ["email"] }, "refresh", env);
    let redirect;
    await refreshGoogle({ refresh_handle }, env, async (url, init) => {
      // Construct in workerd: Node accepts redirect modes that Cloudflare rejects.
      const outbound = new Request(url, init);
      redirect = outbound.redirect;
      return Response.json({ access_token: "fixture-access", token_type: "Bearer", expires_in: 3600 });
    });
    return Response.json({ refreshed: true, redirect });
  },
};
