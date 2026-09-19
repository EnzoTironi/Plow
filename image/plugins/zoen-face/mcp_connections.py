"""Owner-requested catalog OAuth jobs on the existing gateway loop."""
import asyncio
import contextvars
import logging
import os
import uuid

log = logging.getLogger(__name__)
_jobs = {}


def catalog():
    from hermes_cli.mcp_catalog import list_catalog
    return [entry for entry in list_catalog()
            if entry.auth.type == "oauth" and entry.transport.type == "http"
            and entry.transport.url.startswith("https://") and entry.install is None
            and not entry.auth.env and not entry.transport.env]


def server_config(name):
    from hermes_cli.mcp_catalog import _build_server_config
    from hermes_cli.mcp_config import _get_mcp_servers
    entry = next((entry for entry in catalog() if entry.name == name), None)
    if entry is None:
        raise ValueError("connector_not_in_native_oauth_catalog")
    cfg = _build_server_config(entry, None)
    prior = _get_mcp_servers().get(name, {})
    if prior and (prior.get("url") != cfg["url"] or prior.get("auth") != "oauth" or prior.get("headers") or prior.get("command")):
        raise ValueError("existing_connector_configuration_conflicts")
    cfg.update(prior)
    cfg["enabled"] = True
    if "tools" not in cfg:
        selection = {}
        if entry.tools.default_enabled is not None:
            selection["include"] = list(entry.tools.default_enabled)
        if entry.tools.default_excluded:
            selection["exclude"] = list(entry.tools.default_excluded)
        if selection:
            cfg["tools"] = selection
    if (cfg.get("oauth") or {}).get("flow", "browser") != "browser":
        raise ValueError("device_flow_not_available_in_imessage")
    return cfg


def cached_status(name):
    from tools.mcp_oauth import HermesTokenStorage
    from tools.mcp_tool_discovery import get_registered_mcp_server_names
    return {"credentials_saved": HermesTokenStorage(name).has_cached_tokens(),
            "tools_loaded": name in get_registered_mcp_server_names(), "account_verified": False}


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
    def __init__(self, adapter, module, chat, flow, cfg):
        self.adapter, self.module, self.chat = adapter, module, chat
        self.flow, self.cfg = flow, cfg
        self.status = "starting"
        self.task = None

    async def announce(self, text):
        await notify(self.adapter, self.module, self.chat, self.flow.server_name, text)

    async def run(self):
        from .oauth_runner import run_authorization
        worker = asyncio.create_task(asyncio.to_thread(run_authorization, self.flow, self.cfg))
        announced = False
        try:
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
            if self.flow.snapshot()["status"] != "approved":
                self.status = self.flow.failure_code or "authorization_failed"
                if self.status != "authorization_cancelled":
                    await self.announce(f"Connection did not complete ({self.status}). Explain this briefly; no account access was verified. "
                                        "Keep the task awaiting access. Offer a fresh link if they want to retry. "
                                        "Do not guess that the provider or Plow configuration caused the failure.")
                return
            # Refresh only this connector. Hermes refreshes cached agents from
            # the registry between turns, preserving history and tool filters.
            loaded = await asyncio.to_thread(activate_tools, self.flow.server_name)
            self.status = "tools_ready" if loaded else "authorized_tools_unavailable"
            await self.announce(f"OAuth completed; credentials are saved by Hermes. Tool loading: {self.status}. "
                                "Before claiming success, use the connector to verify the account or workspace and perform one small read. "
                                "Then resume only the owner's previously requested task, respecting its scope and any cancellation. "
                                "If no task is pending, report the verified connection concisely. Never substitute a different account.")
        except asyncio.CancelledError:
            self.flow.cancel()
            self.status = "authorization_cancelled"
            raise
        except Exception as exc:
            self.flow.cancel()
            self.status = "connection_delivery_failed"
            log.warning("connection job failed (%s)", type(exc).__name__)
        finally:
            try:
                await self.flow.relay.finish(consumed=self.flow.snapshot()["status"] == "approved")
            except Exception as exc:
                # Relay records expire independently even if cleanup is offline.
                log.warning("connection cleanup deferred to expiry (%s)", type(exc).__name__)
            await worker


async def dispatch(adapter, module, turn, args):
    from hermes_constants import get_hermes_home
    from hermes_cli.config import load_config
    action, name = args.get("action"), args.get("connector")
    if action == "catalog":
        return {"ok": True, "connectors": [{"name": entry.name, "description": entry.description,
                                            "availability": "requires_provider_authorization"} for entry in catalog()]}
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
        return {"ok": True, "connector": name, "status": job.status if job else "not_started", **cached_status(name)}
    if action == "cancel":
        cancelled = pending and job.flow.cancel()
        if cancelled:
            job.status = "authorization_cancelled"
        return {"ok": True, "cancelled": bool(cancelled), "instruction": "If the code exchange already started, wait for status; cancellation does not disconnect a saved account."}
    if action != "connect":
        return {"ok": False, "error": "unsupported_action"}
    if pending:
        return {"ok": True, "status": job.status, "instruction": "The existing login is still active. Do not start another or duplicate the link."}
    if any(existing_home == home and not existing.task.done() for (existing_home, _), existing in _jobs.items()):
        return {"ok": False, "error": "another_connection_in_progress", "instruction": "Complete or cancel the current login first."}
    settings = load_config().get("zoen", {})
    relay_url = os.environ.get("ZOEN_OAUTH_RELAY_URL") or settings.get("oauth_relay_url")
    if not relay_url:
        return {"ok": False, "error": "operator_must_configure_oauth_relay_url"}
    from .oauth_relay import RelayOAuthFlow
    flow = RelayOAuthFlow(relay_url=relay_url, flow_id=uuid.uuid4().hex, server_name=name,
                          profile=None, hermes_home=home)
    cfg["oauth"] = {**(cfg.get("oauth") or {}), "redirect_uri": flow.redirect_uri}
    job = ConnectionJob(adapter, module, turn["chat_uid"], flow, cfg)
    context = contextvars.copy_context()
    context.run(module._ACTIVE_TURN.set, None)
    job.task = asyncio.create_task(job.run(), context=context)
    _jobs[key] = job
    return {"ok": True, "status": "starting", "instruction": "Keep the pending task in Kanban. The authorization link and result will arrive as connection events; do not poll, invent a link, or start another login."}
