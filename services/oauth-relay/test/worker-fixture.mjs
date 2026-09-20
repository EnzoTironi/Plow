// Local test entry only; production deploys src/worker.js.
import worker, { OAuthFlow } from "../src/worker.js";
import { refreshGoogle, seal } from "../src/google.js";
export { OAuthFlow };

export default {
  async fetch(request, env, ctx) {
    if (new URL(request.url).pathname !== "/__fixture/google-runtime") return worker.fetch(request, env, ctx);
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
