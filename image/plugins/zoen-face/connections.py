"""Connection lifecycle. iMessage uses the owner DM. WhatsApp uses the bound phone."""
import asyncio
import json
import sys
import time

from connect import connection
from . import quiet
from . import whatsapp_line

SCHEMA = {
    "name": "zoen_connections",
    "description": "Find and connect services for the owner. Authority is the iMessage owner DM or the WhatsApp line on the bound phone. Google uses Zoen's independent OAuth; request only Google capabilities needed for the task. Slack uses Plow. Native Hermes covers other accounts and public tools. Connect activates only the chosen service in the background; OAuth links and completion arrive automatically. Status reports cached state; verify accounts with a live read. Cancel stops pending consent. Never ask for passwords or pasted tokens.",
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


_BOUND = {"phone": "", "at": 0.0}


def open_whatsapp_line() -> str:
    """The line of this turn. The tool thread reads the stamp; the loop does not keep it."""
    current = str(whatsapp_line.LINE.get() or "")
    if current.startswith("whatsapp:"):
        return current
    stamp = quiet._read_whatsapp_stamp()
    line = str(stamp.get("line_id") or "")
    if line.startswith("whatsapp:"):
        return line
    phone = whatsapp_line.digits(stamp.get("to") or stamp.get("recipient"))
    return f"whatsapp:{phone}" if phone else ""


async def bound_phone(adapter) -> str:
    now = time.monotonic()
    if _BOUND["phone"] and now - _BOUND["at"] < 60:
        return _BOUND["phone"]
    try:
        me = await asyncio.wait_for(adapter._tool_json("GET", "/v1/agents/me"), 5)
    except Exception:
        return ""
    from . import whatsapp
    phone = whatsapp.phone_from_identity(me) if isinstance(me, dict) else ""
    if phone:
        _BOUND["phone"] = phone
        _BOUND["at"] = now
    return phone


async def admits(adapter, module, chat: str, line_id: str = "") -> bool:
    """iMessage owner DM, or the WhatsApp line that opened this turn.

    The relay already bound that phone to this agent. It does not have to equal
    the iMessage handle on /v1/agents/me.
    """
    named = str(line_id or "")
    if not named.startswith("whatsapp:") and str(chat).startswith("whatsapp:"):
        named = str(chat)
    open_line = open_whatsapp_line()
    if named.startswith("whatsapp:") or open_line:
        chosen = named if named.startswith("whatsapp:") else open_line
        if open_line:
            return chosen == open_line
        return bool(whatsapp_line.digits(chosen[len("whatsapp:"):]))
    if adapter._send_guard(chat) is not None:
        return False
    return bool(module._owner_dm(adapter._chats.get(chat, {})))


async def authorized_connection(adapter, module, turn, args, line_id=""):
    chat = turn["chat_uid"]
    # The tool thread captured the line. The gateway loop does not inherit it.
    line_id = str(line_id or open_whatsapp_line() or "")
    if not line_id.startswith("whatsapp:"):
        await asyncio.wait_for(adapter._refresh_current_chat(chat), 5)
    if not await admits(adapter, module, chat, line_id):
        return {"ok": False, "error": "requires the bound line"}
    if args.get("connector") == "google" and args.get("action") != "catalog":
        from . import google_connections
        return await google_connections.dispatch(adapter, module, turn, args)
    if args.get("connector") == "slack" and args.get("action") != "catalog":
        return await asyncio.to_thread(connection, args.get("action"), args.get("connector"))
    from . import mcp_connections
    return await mcp_connections.dispatch(adapter, module, turn, args)


def _dispatch(adapter, module, loop, turn, args, line_id=""):
    future = asyncio.run_coroutine_threadsafe(
        authorized_connection(adapter, module, turn, args, line_id), loop
    )
    try:
        return json.dumps(future.result(timeout=18))
    except Exception as exc:
        future.cancel()
        return json.dumps({"ok": False, "error": f"connection unavailable: {type(exc).__name__}"})


def handle(args, **_kwargs):
    line_id = open_whatsapp_line()
    on_whatsapp = line_id.startswith("whatsapp:")
    for adapter_cls in quiet._adapters():
        module = sys.modules.get(adapter_cls.__module__)
        live = getattr(module, "_live", None) if module is not None else None
        if live is None:
            continue
        if on_whatsapp:
            turn = {"chat_uid": line_id, "owner": True, "dm": True}
        else:
            turn = module._ACTIVE_TURN.get()
            if not turn or not turn.get("owner") or not turn.get("dm"):
                continue
        adapter, loop = live
        return _dispatch(adapter, module, loop, turn, args, line_id)
    missing = "the bound line" if on_whatsapp else "an active owner DM"
    return json.dumps({"ok": False, "error": f"connection management requires {missing}"})
