"""Owner-DM-only connection lifecycle, using the existing Plow turn authority."""
import asyncio
import json
import sys

from connect import connection
from . import quiet

SCHEMA = {
    "name": "zoen_connections",
    "description": "Find and connect services in the owner's private iMessage conversation. Catalog supports a query by name or capability and identifies OAuth, public services, and operator setup. Google/Slack use Plow; native Hermes covers accounts, public tools and Treg's API catalog. Connect activates only the chosen service in the background; OAuth links and completion arrive automatically. Status reports cached state; verify accounts with a live read. Cancel stops pending consent. Never ask for passwords or pasted tokens.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["catalog", "status", "connect", "cancel"]},
            "connector": {"type": "string", "description": "google, slack, or an exact name returned by catalog. Omit for catalog."},
            "query": {"type": "string", "maxLength": 100, "description": "Optional catalog filter by service name or capability words (catalog descriptions are in English). Omit to list all."},
        },
        "required": ["action"],
        "additionalProperties": False,
    },
}


async def authorized_connection(adapter, module, turn, args):
    chat = turn["chat_uid"]
    await asyncio.wait_for(adapter._refresh_current_chat(chat), 5)
    if not module._owner_dm(adapter._chats.get(chat, {})) or adapter._send_guard(chat) is not None:
        return {"ok": False, "error": "requires the owner's current private chat"}
    if args.get("connector") in {"google", "slack"} and args.get("action") != "catalog":
        return await asyncio.to_thread(connection, args.get("action"), args.get("connector"))
    from . import mcp_connections
    return await mcp_connections.dispatch(adapter, module, turn, args)


def handle(args, **_kwargs):
    for adapter_cls in quiet._adapters():
        module = sys.modules.get(adapter_cls.__module__)
        turn = module._ACTIVE_TURN.get() if module is not None else None
        if not turn or not turn.get("owner") or not turn.get("dm") or module._live is None:
            continue
        adapter, loop = module._live
        future = asyncio.run_coroutine_threadsafe(authorized_connection(adapter, module, turn, args), loop)
        try:
            return json.dumps(future.result(timeout=18))
        except Exception as exc:
            future.cancel()
            return json.dumps({"ok": False, "error": f"connection unavailable: {type(exc).__name__}"})
    return json.dumps({"ok": False, "error": "connection management requires an active owner DM"})
