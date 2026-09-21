"""Transport only: native Hermes still owns PKCE, tokens and issuer validation."""
import asyncio
import hashlib
import os
import secrets
import time
import uuid
from urllib.parse import parse_qs, urlsplit

import aiohttp
from mcp.client.auth.exceptions import OAuthFlowError
from tools.mcp_dashboard_oauth import DashboardOAuthFlow


class RelayError(OAuthFlowError):
    """Safe error code; never includes a URL, callback or credential."""


def authorization_flow(name, home, config):
    """Public services need no relay; OAuth gets a private, per-attempt flow."""
    if config.get("auth") != "oauth":
        return None
    from hermes_cli.config import load_config
    settings = load_config().get("zoen", {})
    relay_url = os.environ.get("ZOEN_OAUTH_RELAY_URL") or settings.get("oauth_relay_url")
    if not relay_url:
        raise RelayError("operator_must_configure_oauth_relay_url")
    flow = RelayOAuthFlow(relay_url=relay_url, flow_id=uuid.uuid4().hex, server_name=name,
                          profile=None, hermes_home=home)
    config["oauth"] = {**(config.get("oauth") or {}), "redirect_uri": flow.redirect_uri}
    return flow


class RelayClient:
    def __init__(self, base_url):
        url = urlsplit(base_url)
        local = url.scheme == "http" and url.hostname in {"127.0.0.1", "localhost"}
        if not (url.scheme == "https" or local) or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise RelayError("relay_configuration_invalid")
        self.base = base_url.rstrip("/")
        self.secret = secrets.token_urlsafe(32)
        self.path = None

    async def request(self, method, path, body=None, *, timeout=8):
        # Native MCP runs its own event loop. Do not share an aiohttp session
        # with the gateway loop, or follow a redirect carrying our poll secret.
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as http:
                async with http.request(method, self.base + path, json=body, allow_redirects=False,
                                        headers={"Authorization": f"Bearer {self.secret}"}) as result:
                    if result.status == 410:
                        raise RelayError("authorization_expired")
                    if result.status == 429 or result.status >= 500:
                        raise RelayError("relay_unavailable")
                    if result.status >= 300:
                        raise RelayError(f"relay_http_{result.status}")
                    data = await result.json()
                    if not isinstance(data, dict):
                        raise RelayError("relay_response_invalid")
                    return data
        except (aiohttp.ClientError, TimeoutError, ValueError):
            raise RelayError("relay_unavailable") from None

    async def register(self, state):
        self.path = "/flows/" + hashlib.sha256(state.encode()).hexdigest()
        return await self.request("POST", "/flows", {"state": state, "poll_token": self.secret})

    async def finish(self, *, consumed=False):
        if self.path:
            await self.request("POST" if consumed else "DELETE", self.path + ("/ack" if consumed else ""))

    async def poll(self):
        try:
            return await self.request("GET", self.path)
        except RelayError as exc:
            if str(exc) != "relay_unavailable":
                raise
            return {"status": "retry"}


class RelayOAuthFlow(DashboardOAuthFlow):
    def __init__(self, *, relay_url, **kwargs):
        self.relay = RelayClient(relay_url)
        super().__init__(redirect_uri=self.relay.base + "/callback", **kwargs)
        self.phase = "starting"
        self.failure_code = None

    async def publish_authorization_url(self, url):
        parsed = urlsplit(url)
        query = parse_qs(parsed.query)
        state = query.get("state", [""])[0]
        if parsed.scheme != "https" and parsed.hostname not in {"127.0.0.1", "localhost"}:
            raise RelayError("authorization_url_invalid")
        if query.get("code_challenge_method") != ["S256"] or not query.get("code_challenge"):
            raise RelayError("provider_requires_pkce")
        if query.get("redirect_uri") != [self.redirect_uri] or len(state) < 32:
            raise RelayError("authorization_url_invalid")
        await self.relay.register(state)
        await super().publish_authorization_url(url)
        self.phase = "awaiting_consent"

    async def wait_for_callback(self, timeout=900):
        deadline = time.monotonic() + timeout
        try:
            while time.monotonic() < deadline:
                if self.snapshot()["status"] == "error":
                    raise RelayError(self.failure_code or "authorization_cancelled")
                data = await self.relay.poll()
                if data.get("status") == "ready":
                    callback = data["callback"]
                    error = callback.get("error")
                    self.deliver_callback(code=callback.get("code"), state=callback.get("state"),
                                          error=("access_denied" if error == "access_denied" else "provider_error") if error else None)
                    if error:
                        raise RelayError(self.failure_code)
                    self.phase = "exchanging_code"
                    # Native SDK 2.0 checks iss when the issuer advertises it.
                    # Ack happens after native code exchange, in the supervisor.
                    result = await super().wait_for_callback(timeout=0)
                    return (*result, callback.get("iss"))
                if data.get("status") in {"consumed", "cancelled"}:
                    raise RelayError("authorization_cancelled")
                await asyncio.sleep(1)
            raise RelayError("authorization_expired")
        except RelayError as exc:
            self.failure_code = str(exc)
            raise

    def cancel(self):
        # Once the native exchange starts, let it finish; cancellation is not
        # permission to erase a concurrently saved connection or old tokens.
        with self._lock:
            if self._callback_ready.is_set() or self.status == "approved":
                return False
            self.failure_code = "authorization_cancelled"
            self.status = "error"
            self.error = self.failure_code
            self._callback_ready.set()
            self._authorization_ready.set()
            return True

    def deliver_callback(self, **kwargs):
        super().deliver_callback(**kwargs)
        if kwargs.get("error"):
            self.failure_code = "authorization_denied" if kwargs["error"] == "access_denied" else "provider_authorization_failed"
