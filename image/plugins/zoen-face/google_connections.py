"""Google consent over the same private iMessage connection event queue."""
import asyncio
import base64
import contextvars
import hashlib
import os
import secrets
import time

from google_account import Account, GoogleError, relay_url, request, validate_tokens, verify_identity
from . import mcp_connections
from .oauth_relay import RelayClient, RelayError


class GoogleJob:
    def __init__(self, adapter, module, chat, home, relay, options):
        self.adapter, self.module, self.chat = adapter, module, chat
        self.account, self.relay = Account(home), RelayClient(relay_url(relay))
        self.capabilities, self.status = options.get("capabilities") or ["identity"], "starting"
        self.task = None
        self.exchanging = False
        self.replace_account = options.get("replace_account") is True

    async def announce(self, text):
        await mcp_connections.notify(self.adapter, self.module, self.chat, "google", text)

    async def authorize(self):
        baseline = self.account.read()
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        identifier = hashlib.sha256(state.encode()).hexdigest()
        self.relay.path = "/flows/" + identifier
        result = await self.relay.request("POST", "/google/flows", {
            "state": state, "poll_token": self.relay.secret, "code_challenge": challenge,
            "capabilities": self.capabilities,
        })
        self.status = "awaiting_consent"
        await self.announce("Send this Google authorization link once in the owner's private conversation. "
                            "Ask them to check the account and permissions. It expires in five minutes. "
                            "Do not claim success yet or ask them to bypass an unverified-app warning.\n"
                            + result["authorization_url"])
        await self.wait_for_callback(result["expires_at"], state)
        self.exchanging = True
        self.status = "verifying_account"
        tokens = await self.exchange(identifier, verifier)
        validate_tokens(tokens)
        identity = await asyncio.to_thread(verify_identity, tokens["access_token"])
        if baseline and baseline.get("account", {}).get("id") != identity["id"] and not self.replace_account:
            raise GoogleError("google_account_switch_requires_owner_request")
        await asyncio.wait_for(self.adapter._refresh_current_chat(self.chat), 5)
        if not self.module._owner_dm(self.adapter._chats.get(self.chat, {})) or self.adapter._send_guard(self.chat) is not None:
            raise GoogleError("google_owner_chat_no_longer_authorized")
        self.account.commit({**tokens, "relay_url": self.relay.base, "account": identity}, baseline)
        self.status = "credentials_saved"
        await self.announce(f"Google identity verified: {identity['email']}. Credentials saved in this instance. "
                            "Use /opt/plow/zoen/google_workspace.py for Google API calls; the Plow Google connector is not involved. "
                            f"Granted scopes: {', '.join(tokens['scopes'])}. "
                            "Verify one small read for the pending task before claiming that service works. "
                            "Do not substitute a different account. Never print credential files.")

    async def wait_for_callback(self, expires_at, state):
        deadline = min(expires_at / 1000, time.time() + 300)
        while time.time() < deadline:
            status = await self.relay.poll()
            if status.get("status") == "ready":
                callback = status.get("callback", {})
                if callback.get("state") != state:
                    raise GoogleError("google_state_mismatch")
                if callback.get("error"):
                    raise GoogleError("google_authorization_denied")
                break
            if status.get("status") in {"consumed", "cancelled"}:
                raise GoogleError("google_authorization_cancelled")
            await asyncio.sleep(1)
        else:
            raise GoogleError("google_authorization_expired")

    async def exchange(self, identifier, verifier):
        for attempt in range(2):
            try:
                return await self.relay.request("POST", f"/google/flows/{identifier}/exchange",
                                                {"code_verifier": verifier}, timeout=20)
            except RelayError as exc:
                if str(exc) != "relay_unavailable" or attempt:
                    raise

    async def run(self):
        try:
            await self.authorize()
        except asyncio.CancelledError:
            self.status = "authorization_cancelled"
            raise
        except (GoogleError, RelayError) as exc:
            self.status = "authorization_failed"
            await self.announce(f"Google connection did not complete ({exc}). Previous saved access was preserved. "
                                "Keep the task waiting for access; do not guess that the account is disconnected.")
        except Exception:
            self.status = "connection_failed"
            await self.announce("Google setup could not complete. No account access was verified. "
                                "Check the saved connection before suggesting another login.")
        finally:
            try:
                await self.relay.finish(consumed=self.status == "credentials_saved")
            except RelayError:
                pass  # The relay deletes expired attempts independently.


async def dispatch(adapter, module, turn, args):
    from hermes_constants import get_hermes_home
    from hermes_cli.config import load_config
    home, action = str(get_hermes_home()), args.get("action")
    job = mcp_connections._jobs.get((home, "google"))
    pending = job is not None and not job.task.done()
    if action == "status":
        result = Account(home).status()
        if job:
            result["status"] = job.status
        return {"ok": True, "connector": "google", "authentication": "zoen_oauth", **result}
    if action == "cancel":
        cancelled = pending and not job.exchanging
        if cancelled:
            job.task.cancel()
        return {"ok": True, "cancelled": bool(cancelled)}
    if action != "connect":
        return {"ok": False, "error": "unsupported_action"}
    if pending:
        return {"ok": True, "status": job.status, "instruction": "The existing Google login is still active; do not duplicate it."}
    if any(key[0] == home and not value.task.done() for key, value in mcp_connections._jobs.items()):
        return {"ok": False, "error": "another_connection_in_progress"}
    relay = os.environ.get("ZOEN_GOOGLE_RELAY_URL") or load_config().get("zoen", {}).get("google_relay_url")
    if not relay:
        return {"ok": False, "error": "google_operator_setup_required"}
    config = await asyncio.wait_for(asyncio.to_thread(request, "GET", relay_url(relay) + "/google/config"), 8)
    capabilities = args.get("capabilities") or ["identity"]
    if not config.get("configured") or any(name not in config.get("capabilities", []) for name in capabilities):
        return {"ok": False, "error": "google_capability_not_enabled", "available": config.get("capabilities", []),
                "instruction": "Independent Google access is awaiting operator setup or Google verification. Do not route through Plow, fabricate a login link or ask the user to bypass a warning."}
    job = GoogleJob(adapter, module, turn["chat_uid"], home, relay, args)
    context = contextvars.copy_context()
    context.run(module._ACTIVE_TURN.set, None)
    job.task = asyncio.create_task(job.run(), context=context)
    mcp_connections._jobs[(home, "google")] = job
    return {"ok": True, "status": "starting", "instruction": "Authorization and completion arrive automatically in this conversation. Keep the pending task; do not poll."}
