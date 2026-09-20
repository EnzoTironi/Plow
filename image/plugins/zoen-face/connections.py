"""Owner-DM-only connection lifecycle, using the existing Plow turn authority."""
import asyncio
import json
import sys

from connect import connection
from . import quiet

SCHEMA = {
    "name": "zoen_connections",
    "description": "Find and connect services in the owner's private iMessage conversation. Google uses Zoen's independent OAuth; request only Google capabilities needed for the task. Slack uses Plow. Native Hermes covers other accounts and public tools. Connect activates only the chosen service in the background; OAuth links and completion arrive automatically. Status reports cached state; verify accounts with a live read. Cancel stops pending consent. Never ask for passwords or pasted tokens.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["catalog", "status", "connect", "cancel"]},
            "connector": {"type": "string", "description": "google, slack, or an exact name returned by catalog. Omit for catalog."},
            "query": {"type": "string", "maxLength": 100, "description": "Optional catalog filter by service name or capability words (catalog descriptions are in English). Omit to list all."},
            "capabilities": {"type": "array", "uniqueItems": True, "maxItems": 12,
                             "description": "Google only: permissions needed for this task. Omit for identity-only login. The operator enables capabilities for the configured beta or verified app; the owner grants access on Google's screen.",
                             "items": {"type": "string", "enum": ["identity", "calendar_read", "calendar_write", "gmail_read", "gmail_send", "drive_files", "drive_read", "contacts_read", "sheets_read", "sheets_write", "docs_read", "docs_write"]}},
            "replace_account": {"type": "boolean", "description": "Google only. True solely when the owner explicitly asked to replace the previously connected Google account; adding permissions does not authorize an account switch."},
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
    if args.get("connector") == "google" and args.get("action") != "catalog":
        from . import google_connections
        return await google_connections.dispatch(adapter, module, turn, args)
    if args.get("connector") == "slack" and args.get("action") != "catalog":
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
