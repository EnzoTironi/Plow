"""Owner-DM-only connection lifecycle, using the existing Plow turn authority."""
import asyncio
import json
import sys

from connect import connection
from . import quiet

SCHEMA = {
    "name": "zoen_connections",
    "description": "Check or connect the owner's Google (Gmail/Calendar) or Slack account from their private iMessage conversation. On connect, send the returned short-lived URL to the owner, then verify status and account before resuming the task. No passwords or pasted tokens.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["status", "connect"]},
            "connector": {"type": "string", "enum": ["google", "slack"]},
        },
        "required": ["action", "connector"],
        "additionalProperties": False,
    },
}


async def authorized_connection(adapter, module, turn, args):
    chat = turn["chat_uid"]
    await asyncio.wait_for(adapter._refresh_current_chat(chat), 5)
    if not module._owner_dm(adapter._chats.get(chat, {})) or adapter._send_guard(chat) is not None:
        return {"ok": False, "error": "requires the owner's current private chat"}
    return await asyncio.to_thread(connection, args.get("action"), args.get("connector"))


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
