"""Owner-requested catalog connections on the existing gateway loop."""
import asyncio
import contextvars
import logging
import uuid

from .connection_catalog import catalog_result, server_config

log = logging.getLogger(__name__)
_jobs = {}


def cached_status(name, config):
    from tools.mcp_oauth import HermesTokenStorage
    from tools.mcp_tool_discovery import get_registered_mcp_server_names
    oauth = config.get("auth") == "oauth"
    saved = HermesTokenStorage(name).has_cached_tokens() if oauth else None
    loaded = name in get_registered_mcp_server_names()
    status = "tools_ready" if loaded else "credentials_saved" if saved else "not_started"
    return {"credentials_saved": saved, "tools_loaded": loaded, "account_verified": None, "status": status,
            "authentication": "oauth" if oauth else "public",
            "instruction": "Account verification requires a live read; cached credentials alone do not establish access."}


def connect_public(name, config):
    from hermes_cli.mcp_config import _probe_single_server, _save_mcp_server
    tools = _probe_single_server(name, {**config, "connect_timeout": 12}, connect_timeout=15)
    if not tools:
        raise RuntimeError("public_connector_has_no_tools")
    if not _save_mcp_server(name, config):
        raise RuntimeError("public_connector_configuration_rejected")


async def notify(adapter, module, chat_uid, name, details):
    """Resume through Plow's normal message queue, preserving its send guards."""
    await asyncio.wait_for(adapter._refresh_current_chat(chat_uid), 5)
    if not module._owner_dm(adapter._chats.get(chat_uid, {})) or adapter._send_guard(chat_uid) is not None:
        raise PermissionError("owner_dm_no_longer_authorized")
    chat = await adapter.get_chat_info(chat_uid)
    authority, recall = module._authority(chat, True, human=False)
    event = module.MessageEvent(
        text=f"[Zoen connection event: {name}]\n{details}\nThis is the result of the owner's earlier connection request, not a new human message. Use the existing conversation and task context.",
        source=adapter.build_source(chat_id=chat_uid, chat_name=chat["name"], chat_type=chat["type"],
                                    user_id="plow_connection", user_name="Connection result", role_authorized=True),
        message_id=f"connection-{uuid.uuid4().hex}", message_type=module._message_type([]),
        channel_prompt=module._channel_prompt(chat, "owner", adapter._chats[chat_uid],
                                              adapter._identity, authority, speak_rule=False),
    )
    event.internal = True
    event.authority, event.recall_everywhere = authority, recall
    event.recall_text = f"The owner's pending task involving {name}"
    await adapter._handoff_message(event)


def activate_tools(name):
    from tools.mcp_tool_common import _core
    from tools.mcp_tool_scope import _resolve_server_key
    from tools.mcp_tool_loop import _signal_reconnect_and_wait
    from tools.mcp_tool_discovery import discover_mcp_tools, get_registered_mcp_server_names
    with _core._lock:
        server = _core._servers.get(_resolve_server_key(name))
    # Reauthorization must also replace an already-live session's auth object.
    # Otherwise a switch of account could keep serving the previous account.
    if server is not None and not _signal_reconnect_and_wait(name, server, op_description="owner reauthorized"):
        return False
    discover_mcp_tools([name])
    return name in get_registered_mcp_server_names()


class ConnectionJob:
    def __init__(self, adapter, module, chat, name, cfg, flow=None):
        self.adapter, self.module, self.chat = adapter, module, chat
        self.name, self.flow, self.cfg = name, flow, cfg
        self.status = "starting"
        self.task = None

    async def announce(self, text):
        await notify(self.adapter, self.module, self.chat, self.name, text)

    async def wait_authorization(self, worker):
        announced = False
        while not worker.done():
            snapshot = self.flow.snapshot()
            if snapshot["status"] == "error":
                self.status = self.flow.failure_code or "authorization_failed"
            else:
                self.status = "verifying_connection" if snapshot["status"] == "approved" else self.flow.phase
            if snapshot["authorization_url"] and snapshot["status"] != "error" and not announced:
                announced = True
                self.status = "awaiting_consent"
                await self.announce("Send this authorization link once in the owner's private iMessage conversation, using your own voice. "
                                    "Ask them to check the account and requested permissions on the provider's page. "
                                    "This link expires in five minutes. "
                                    "Do not claim the account is connected yet. The result will arrive automatically; do not poll or start another login.\n"
                                    + snapshot["authorization_url"])
            await asyncio.sleep(.2)
        await worker
        if self.flow.snapshot()["status"] == "approved":
            return True
        self.status = self.flow.failure_code or "authorization_failed"
        if self.status != "authorization_cancelled":
            await self.announce(f"Connection did not complete ({self.status}). Explain this briefly; no account access was verified. "
                                "Keep the task awaiting access. Offer a fresh link if they want to retry. "
                                "Do not guess that the provider or Plow configuration caused the failure.")
        return False

    async def run(self):
        from .oauth_runner import run_authorization
        worker = None
        try:
            if self.flow:
                worker = asyncio.create_task(asyncio.to_thread(run_authorization, self.flow, self.cfg))
                if not await self.wait_authorization(worker):
                    return
            else:
                self.status = "checking_connection"
                await asyncio.to_thread(connect_public, self.name, self.cfg)
            # Refresh only this connector. Hermes refreshes cached agents from
            # the registry between turns, preserving history and tool filters.
            self.status = "loading_tools"
            loaded = await asyncio.to_thread(activate_tools, self.name)
            self.status = "tools_ready" if loaded else "tools_unavailable"
            authorization = "OAuth completed; credentials are saved by Hermes." if self.flow else "Public service enabled; no personal account was connected."
            await self.announce(f"{authorization} Tool loading: {self.status}. "
                                "Before claiming success, perform one small read; for an account connector verify the account or workspace. "
                                "For Treg verify identity/team with balance and query catalog_search for a capability such as web search; do not spend credits for verification. "
                                "Then resume only the owner's previously requested task, respecting its scope and any cancellation. "
                                "If no task is pending, report the verified connection concisely. Never substitute a different account.")
        except asyncio.CancelledError:
            if self.flow:
                self.flow.cancel()
            self.status = "authorization_cancelled"
            raise
        except Exception as exc:
            if self.flow:
                self.flow.cancel()
            self.status = "connection_failed"
            log.warning("connection job failed (%s)", type(exc).__name__)
            try:
                await self.announce("Connection setup could not complete. Keep the pending task awaiting access. "
                                    "Check saved credentials and tool availability before suggesting a retry; do not guess the cause.")
            except Exception as delivery_error:
                log.warning("connection result could not be delivered (%s)", type(delivery_error).__name__)
        finally:
            try:
                if self.flow:
                    await self.flow.relay.finish(consumed=self.flow.snapshot()["status"] == "approved")
            except Exception as exc:
                # Relay records expire independently even if cleanup is offline.
                log.warning("connection cleanup deferred to expiry (%s)", type(exc).__name__)
            if worker:
                await worker


async def dispatch(adapter, module, turn, args):
    from hermes_constants import get_hermes_home
    from .oauth_relay import authorization_flow, RelayError
    action, name = args.get("action"), args.get("connector")
    if action == "catalog":
        return catalog_result(args.get("query", ""))
    if not isinstance(name, str):
        return {"ok": False, "error": "connector_required"}
    try:
        cfg = server_config(name)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    home = str(get_hermes_home())
    key = (home, name)
    job = _jobs.get(key)
    pending = job is not None and not job.task.done()
    if action == "status":
        cached = cached_status(name, cfg)
        if job:
            cached["status"] = job.status
        return {"ok": True, "connector": name, **cached}
    if action == "cancel":
        cancelled = pending and job.flow is not None and job.flow.cancel()
        if cancelled:
            job.status = "authorization_cancelled"
        return {"ok": True, "cancelled": bool(cancelled), "instruction": "If the code exchange already started, wait for status; cancellation does not disconnect a saved account."}
    if action != "connect":
        return {"ok": False, "error": "unsupported_action"}
    if pending:
        return {"ok": True, "status": job.status, "instruction": "The existing login is still active. Do not start another or duplicate the link."}
    if any(existing_home == home and not existing.task.done() for (existing_home, _), existing in _jobs.items()):
        return {"ok": False, "error": "another_connection_in_progress", "instruction": "Complete or cancel the current login first."}
    try:
        flow = authorization_flow(name, home, cfg)
    except RelayError as exc:
        return {"ok": False, "error": str(exc)}
    job = ConnectionJob(adapter, module, turn["chat_uid"], name, cfg, flow)
    context = contextvars.copy_context()
    context.run(module._ACTIVE_TURN.set, None)
    job.task = asyncio.create_task(job.run(), context=context)
    _jobs[key] = job
    return {"ok": True, "status": "starting", "instruction": "Keep the pending task in Kanban. The result will arrive as a connection event; OAuth services also send an authorization link. Public services require no login. Do not poll, invent a link, or start another connection."}
