"""Real pinned Hermes/SDK + deployed relay + loopback OAuth/MCP fixture.

Run inside the image with this checkout mounted at /workspace and an explicit
ZOEN_OAUTH_RELAY_URL. No real user credentials or provider accounts are used.
"""
import asyncio
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
from urllib.parse import parse_qs, urlencode, urlsplit

import aiohttp
from aiohttp import web

sys.path.insert(0, "/opt/hermes")


class Provider:
    def __init__(self):
        self.base = ""
        self.challenge = None
        self.redirect = None
        self.access = secrets.token_urlsafe(32)
        self.refresh = secrets.token_urlsafe(32)
        self.exchanges = 0
        self.refreshes = 0
        self.reads = 0

    async def resource(self, request):
        return web.json_response({"resource": self.base + "/mcp", "authorization_servers": [self.base],
                                  "scopes_supported": ["tasks:read"]})

    async def metadata(self, request):
        return web.json_response({"issuer": self.base, "authorization_endpoint": self.base + "/authorize",
                                  "token_endpoint": self.base + "/token", "registration_endpoint": self.base + "/register",
                                  "response_types_supported": ["code"], "grant_types_supported": ["authorization_code", "refresh_token"],
                                  "token_endpoint_auth_methods_supported": ["none"], "code_challenge_methods_supported": ["S256"],
                                  "authorization_response_iss_parameter_supported": True})

    async def register(self, request):
        body = await request.json()
        self.redirect = body["redirect_uris"][0]
        assert self.redirect == os.environ["ZOEN_OAUTH_RELAY_URL"].rstrip("/") + "/callback"
        return web.json_response({**body, "client_id": "zoen-fixture-client", "token_endpoint_auth_method": "none"}, status=201)

    async def token(self, request):
        data = await request.post()
        if data["grant_type"] == "authorization_code":
            challenge = base64.urlsafe_b64encode(hashlib.sha256(data["code_verifier"].encode()).digest()).decode().rstrip("=")
            assert challenge == self.challenge
            assert data["redirect_uri"] == self.redirect and data["code"] == "fixture-code"
            self.exchanges += 1
        else:
            assert data["grant_type"] == "refresh_token" and data["refresh_token"] == self.refresh
            self.refreshes += 1
        return web.json_response({"access_token": self.access, "refresh_token": self.refresh,
                                  "token_type": "Bearer", "expires_in": 3600, "scope": "tasks:read"})

    async def mcp(self, request):
        if request.headers.get("Authorization") != "Bearer " + self.access:
            return web.Response(status=401, headers={"WWW-Authenticate": f'Bearer resource_metadata="{self.base}/.well-known/oauth-protected-resource"'})
        if request.method != "POST":
            return web.Response(status=405)
        message = await request.json()
        if "id" not in message:
            return web.Response(status=202)
        method = message["method"]
        if method == "initialize":
            result = {"protocolVersion": message["params"]["protocolVersion"], "capabilities": {"tools": {}},
                      "serverInfo": {"name": "zoen-oauth-fixture", "version": "1"}}
        elif method == "tools/list":
            result = {"tools": [{"name": "whoami", "description": "Read the connected fixture account", "inputSchema": {"type": "object", "properties": {}}}]}
        elif method == "tools/call":
            assert message["params"]["name"] == "whoami"
            self.reads += 1
            result = {"content": [{"type": "text", "text": "fixture-owner@example.invalid"}]}
        else:
            result = {}
        return web.json_response({"jsonrpc": "2.0", "id": message["id"], "result": result})


async def verify(home):
    os.environ["HERMES_HOME"] = str(home)
    (home / "config.yaml").write_text("mcp_servers: {}\n")
    spec = importlib.util.spec_from_file_location("relay_bridge", "/opt/hermes/plugins/zoen-face/oauth_relay.py")
    bridge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge)
    runner_spec = importlib.util.spec_from_file_location("oauth_runner", "/opt/hermes/plugins/zoen-face/oauth_runner.py")
    oauth_runner = importlib.util.module_from_spec(runner_spec)
    runner_spec.loader.exec_module(oauth_runner)
    from tools.mcp_oauth import HermesTokenStorage
    from tools.mcp_tool_discovery import discover_mcp_tools
    from tools.mcp_tool_lifecycle import shutdown_mcp_servers
    from tools.registry import registry

    provider = Provider()
    app = web.Application()
    app.router.add_get("/.well-known/oauth-protected-resource", provider.resource)
    app.router.add_get("/.well-known/oauth-authorization-server", provider.metadata)
    app.router.add_post("/register", provider.register)
    app.router.add_post("/token", provider.token)
    app.router.add_route("*", "/mcp", provider.mcp)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    provider.base = f"http://127.0.0.1:{runner.addresses[0][1]}"
    flow = bridge.RelayOAuthFlow(relay_url=os.environ["ZOEN_OAUTH_RELAY_URL"], flow_id="fixture-flow",
                                 server_name="zoen-fixture", profile=None, hermes_home=str(home))
    config = {"url": provider.base + "/mcp", "auth": "oauth", "connect_timeout": 1,
              "tools": {"include": ["whoami"]}}
    worker = asyncio.create_task(asyncio.to_thread(oauth_runner.run_authorization, flow, config))
    try:
        url = await flow.wait_for_authorization_url(timeout=30)
        params = parse_qs(urlsplit(url).query)
        provider.challenge = params["code_challenge"][0]
        assert params["redirect_uri"] == [flow.redirect_uri]
        assert params["state"] == [flow.expected_state]
        # Consent takes longer than a normal MCP handshake. The staged runner
        # must extend the INNER transport timeout, not only the outer probe.
        await asyncio.sleep(2)
        async with aiohttp.ClientSession() as http:
            wrong = {"state": secrets.token_urlsafe(32), "code": "fixture-code", "iss": provider.base}
            async with http.get(flow.redirect_uri, params=wrong) as response:
                assert response.status == 410
            async with http.get(flow.redirect_uri, params={**wrong, "state": flow.expected_state}) as response:
                assert response.status == 200
        await asyncio.wait_for(asyncio.shield(worker), 35)
        assert flow.status == "approved", flow.error
        assert provider.exchanges == 1
        storage = HermesTokenStorage("zoen-fixture")
        assert storage.has_cached_tokens()
        token_path = storage._tokens_path()
        assert token_path.stat().st_mode & 0o777 == 0o600
        saved = (home / "config.yaml").read_text()
        assert "zoen-fixture:" in saved and provider.access not in saved and provider.refresh not in saved
        names = await asyncio.to_thread(discover_mcp_tools, ["zoen-fixture"])
        selected = [name for name in names if "whoami" in name]
        assert len(selected) == 1, names
        result = await asyncio.to_thread(registry.dispatch, selected[0], {})
        assert "fixture-owner@example.invalid" in str(result), result
        assert provider.reads == 1
        await flow.relay.finish(consumed=True)
        after = await flow.relay.request("GET", flow.relay.path)
        assert after == {"status": "consumed"}
        # Expired native credentials refresh on the next connection. No relay,
        # browser, account password or custom token implementation participates.
        await asyncio.to_thread(shutdown_mcp_servers)
        data = json.loads(token_path.read_text())
        data["expires_at"] = 1
        token_path.write_text(json.dumps(data))
        child = await asyncio.create_subprocess_exec(sys.executable, "-c", """
import sys
sys.path.insert(0, '/opt/hermes')
from tools.mcp_tool_discovery import discover_mcp_tools
from tools.mcp_tool_lifecycle import shutdown_mcp_servers
from tools.registry import registry
try:
    names = discover_mcp_tools(['zoen-fixture'])
    name = next(name for name in names if 'whoami' in name)
    assert 'fixture-owner@example.invalid' in str(registry.dispatch(name, {}))
    print('restart-read-passed')
finally:
    shutdown_mcp_servers()
""", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await asyncio.wait_for(child.communicate(), 35)
        assert child.returncode == 0 and b"restart-read-passed" in stdout, stderr.decode()
        assert provider.refreshes == 1, provider.refreshes
        assert provider.reads == 2
        saved_tokens = token_path.read_bytes()
        # Failed reauthorization must restore the earlier connection. A wrong
        # issuer must never reach the token endpoint, even with a correct state.
        for outcome in ("wrong_issuer", "denied", "cancelled"):
            retry = bridge.RelayOAuthFlow(relay_url=os.environ["ZOEN_OAUTH_RELAY_URL"], flow_id=outcome,
                                          server_name="zoen-fixture", profile=None, hermes_home=str(home))
            retry_worker = asyncio.create_task(asyncio.to_thread(oauth_runner.run_authorization, retry, config))
            retry_url = await retry.wait_for_authorization_url(timeout=30)
            provider.challenge = parse_qs(urlsplit(retry_url).query)["code_challenge"][0]
            if outcome == "cancelled":
                assert retry.cancel()
            elif outcome == "denied":
                callback = {"state": retry.expected_state, "error": "access_denied", "iss": provider.base}
                async with aiohttp.ClientSession() as http:
                    async with http.get(retry.redirect_uri, params=callback) as response:
                        assert response.status == 200
                assert retry.cancel()
            else:
                callback = {"state": retry.expected_state, "code": "fixture-code", "iss": "https://wrong-issuer.example"}
                async with aiohttp.ClientSession() as http:
                    async with http.get(retry.redirect_uri, params=callback) as response:
                        assert response.status == 200
            try:
                await asyncio.wait_for(asyncio.shield(retry_worker), 45)
            except TimeoutError:
                raise AssertionError(f"native worker did not finish after {outcome}") from None
            assert retry.status == "error" and provider.exchanges == 1
            assert token_path.read_bytes() == saved_tokens
            assert not list((home / "zoen/oauth-pending").iterdir())
            await retry.relay.finish()
        print(json.dumps({"native_oauth_pkce": True, "public_relay_callback": True, "wrong_state_rejected": True,
                          "issuer_preserved": True, "native_tokens_mode_0600": True, "native_registry_read": True,
                          "fresh_process_refresh_and_read": True, "callback_consumed": True,
                          "wrong_issuer_rejected": True, "denial_and_cancellation_restore_connection": True}), flush=True)
    finally:
        flow.cancel()
        await worker
        await asyncio.to_thread(shutdown_mcp_servers)
        await runner.cleanup()


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="zoen-oauth-integration-") as folder:
        asyncio.run(verify(Path(folder)))
