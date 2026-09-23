"""Owner iMessage goes through zoen_imessage; leftover send is dropped."""
from __future__ import annotations

import asyncio
import contextvars
import importlib
import json
import logging
import os
import re
import sys
import time
import urllib.request
from contextlib import nullcontext
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

_SCRIPTS = Path("/opt/plow/zoen")
_REPO_SCRIPTS = Path(__file__).resolve().parents[3] / "skills/zoen/scripts"
for _path in (_SCRIPTS, _REPO_SCRIPTS):
    if _path.is_dir() and str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from credits import (  # noqa: E402
    clear_told,
    is_notice as credits_is_notice,
    language as credits_language,
    looks_like as credits_looks_like,
    mark_told,
    notice as credits_notice,
    owner_copy,
    recently_told,
)

log = logging.getLogger("zoen-face")
WHATSAPP = contextvars.ContextVar("zoen_whatsapp_target", default=None)
WHATSAPP_DELIVER = None
LOOP = None
WHATSAPP_MEDIA = None
WHATSAPP_REACT = None
WHATSAPP_CONTACT = None
IMESSAGE_REACT = None
_RETIRED_HELLO = (
    "a gente te ajuda",
    "we'll help.",
    "+55 31 99994-1160",
    "+5531999941160",
    "me criou o enzo",
    "o monstrinho que faz seus sonhos acontecerem",
    "your little monster that makes your dreams come true",
    "salva meu cartão pra você saber que sou eu",
    "save my card so you know it's me",
    "salva o cartão dele pra dúvida ou problema",
    "save his card for questions or trouble",
)

_SILENT = ("send_or_update_status",)

_KNOWN = (
    "hermes_plugins.plow_chat_platform",
    "hermes_plugins.plow_chat",
    "plow_chat",
)
_TAG = re.compile(r"^(MEDIA|VOICE):(/\S+)$")
_MEDIA_ROOTS = (
    Path("/var/lib/hermes/workspace"),
    Path("/srv"),
    Path("/opt/plow"),
)
_VOICE_TYPES = {
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
}


class Delivered:
    success = True
    error = None
    message_id = None
    suppressed = False
    raw_response = {}
    retryable = False
    retry_after = None
    continuation_message_ids = ()
    error_kind = None


class Dropped:
    success = False
    error = "intentionally suppressed; nothing delivered"
    message_id = None
    suppressed = True
    raw_response = {"suppressed": True}
    retryable = False
    retry_after = None
    continuation_message_ids = ()
    error_kind = None


def _leftover_chat(args: tuple, kwargs: dict) -> str:
    chat = kwargs.get("chat_id") or kwargs.get("chat_uid")
    if chat:
        return str(chat)
    if args and str(args[0]).startswith("cht_"):
        return str(args[0])
    return ""


def _leftover_text(args: tuple, kwargs: dict) -> str:
    for key in ("content", "text", "message", "body"):
        value = kwargs.get(key)
        if isinstance(value, str) and value.strip():
            return value
    if len(args) >= 2 and args[1] is not None:
        return str(args[1])
    return ""


def _channel_name(target) -> str:
    return "whatsapp" if isinstance(target, dict) else "imessage"


def _outbound_target(adapter, turn=None):
    """The turn's own inbound wins. A leaked WhatsApp context must not catch iMessage.

    Tool calls hop to the gateway loop without context vars. The turn dict
    they already captured is what still names the WhatsApp chat.
    """
    active = getattr(adapter, "_active_turn", None)
    current_turn = active.get() if active is not None else None
    if isinstance(current_turn, dict) and "zoen_whatsapp" in current_turn:
        target = current_turn.get("zoen_whatsapp")
        return target if isinstance(target, dict) else None
    current = WHATSAPP.get()
    if isinstance(current, dict):
        return current
    if isinstance(turn, dict) and isinstance(turn.get("zoen_whatsapp"), dict):
        return turn["zoen_whatsapp"]
    return None


def note_inbound_channel(adapter, chat_uid, target) -> None:
    """A new message on this chat answers on that message's channel."""
    stamped = target if isinstance(target, dict) else None
    live = getattr(adapter, "_live_turns", None)
    if not isinstance(live, dict):
        return
    for item in live.values():
        if isinstance(item, dict) and item.get("chat_uid") == chat_uid:
            item["zoen_whatsapp"] = stamped


async def _deliver_credits(text, args, kwargs, orig_send, adapter):
    target = _outbound_target(adapter)
    channel = _channel_name(target)
    body = owner_copy(text, channel=channel)
    if not body:
        log.debug("zoen-face dropped duplicate credits leftover")
        return Dropped()
    log.info("zoen-face credits notice on %s", channel)
    if channel == "whatsapp":
        if WHATSAPP_DELIVER is None or not await WHATSAPP_DELIVER(body):
            log.warning("zoen-face credits leftover missed WhatsApp")
            return Dropped()
        mark_told(body, channel=channel)
        _answer_delivered(adapter)
        return Delivered()
    chat_id = _leftover_chat(args, kwargs)
    if not chat_id:
        log.warning("zoen-face credits leftover had no chat")
        return Dropped()
    last = await orig_send(adapter, chat_id, body, metadata=kwargs.get("metadata"))
    if getattr(last, "success", False):
        mark_told(body, channel=channel)
        _answer_delivered(adapter)
    return last


def _wrap_send(orig_send):
    async def send(self, *args, **kwargs):
        text = _leftover_text(args, kwargs)
        if credits_looks_like(text):
            return await _deliver_credits(text, args, kwargs, orig_send, self)
        log.debug("zoen-face dropped leftover send")
        return Dropped()

    send.__name__ = "send"
    send.__qualname__ = "send"
    return send


def _answer_delivered(adapter):
    reception = getattr(adapter, "_zoen_reception", None)
    active = getattr(adapter, "_active_turn", None)
    turn = active.get() if active is not None else None
    if reception is not None and turn is not None:
        reception.answer_delivered(turn["chat_uid"], turn.get("source_message_id"))


def _with_purpose(send_sequence):
    async def sequence(self, args, turn, receipt=None):
        purpose = args.get("purpose", "answer")
        if purpose not in {"progress", "answer"}:
            raise ValueError("purpose must be progress or answer")
        previous = turn.get("reply_delivered", False)
        result = await send_sequence(self, {key: value for key, value in args.items() if key != "purpose"}, turn, receipt)
        if result.get("success"):
            if purpose == "progress":
                turn["reply_delivered"] = previous and not turn.get("inbound_handed_off")
            else:
                turn["reply_delivered"] = not turn.get("inbound_handed_off")
                _answer_delivered(self)
        return result
    return sequence


IMESSAGE = "zoen_imessage"
_FACTORY_SEND = "plow_send_sequence"
_REACTION_KINDS = ("like", "love", "laugh", "emphasize", "question", "dislike")
_CARDS = {
    "zoen": ("Zoen", "+553798136141"),
    "enzo": ("Enzo", "+5531999941160"),
}
IMESSAGE_DESCRIPTION = (
    "Send on this turn's channel. WhatsApp and iMessage both use this tool. "
    "One call sends the bubbles, in order. "
    "purpose=progress is a short update and does not finish the request. "
    "purpose=answer is the result. Stop after it. "
    "The eye is already on the message that opened this turn, and typing is already on. "
    "Do not send a reaction. A reaction is not the reply. "
    "text: body is the bubble. reply_to quotes one bubble. "
    "On WhatsApp, reply_to is that bubble's wamid. On iMessage, leave reply_to off. "
    "image: path is an absolute jpg, png, or webp. "
    "video: path is an absolute mp4. "
    "audio: path is an absolute file. voice true is a voice note. "
    "contact: who is zoen or enzo, or pass name and phone. "
    "The sandbox shell is root. terminal, execute_code, write_file, and patch do the work. They do not text, react, or attach. This tool does. "
    "After a successful call the words are already in the chat. The final reply is [NO_REPLY]."
)

WHO = (
    "You are Zoen. A Plow line or tree name is the number's label, not your name. "
    "People address you as Zoen. Never introduce yourself as that label. "
    "Never mention /help."
)


def claim_identity(module):
    """Keep the Plow facts, replace the per-turn 'You are {line}' prefix."""
    if getattr(module, "_zoen_identity", False):
        return
    if getattr(module, "_with_identity", None) is None:
        return
    facts = getattr(module, "_plow_facts", lambda _identity: "")

    def _with_identity(prompt, name, identity):
        return f"{WHO} {facts(identity)} {prompt}"

    module._with_identity = _with_identity
    module._zoen_identity = True


def _item_option(const, required, properties):
    return {
        "type": "object",
        "additionalProperties": False,
        "required": required,
        "properties": {"type": {"const": const}, **properties},
    }


def _publish_item_types(schema):
    """The model picks a kind. It does not invent a terminal script."""
    box = (((schema.get("parameters") or {}).get("properties") or {}).get("items") or {}).get("items") or {}
    options = box.setdefault("oneOf", [])
    have = {
        ((option.get("properties") or {}).get("type") or {}).get("const")
        for option in options
        if isinstance(option, dict)
    }
    extra = [
        _item_option("reaction", ["type", "kind"], {
            "kind": {"type": "string", "enum": list(_REACTION_KINDS)},
            "message_id": {"type": "string", "description": "Bubble to react to. Omit it for the message that opened this turn."},
        }),
        _item_option("image", ["type", "path"], {
            "path": {"type": "string", "description": "Absolute path of a jpg, png, or webp."},
            "reply_to": {"type": "string"},
        }),
        _item_option("video", ["type", "path"], {
            "path": {"type": "string", "description": "Absolute path of an mp4."},
            "reply_to": {"type": "string"},
        }),
        _item_option("audio", ["type", "path"], {
            "path": {"type": "string", "description": "Absolute path of the audio file."},
            "voice": {"type": "boolean", "description": "True sends a voice note."},
            "reply_to": {"type": "string"},
        }),
        _item_option("contact", ["type"], {
            "who": {"type": "string", "enum": ["zoen", "enzo"], "description": "A saved card."},
            "name": {"type": "string"},
            "phone": {"type": "string", "description": "Digits, with or without +."},
        }),
    ]
    for option in extra:
        const = option["properties"]["type"]["const"]
        if const not in have:
            options.append(option)


def configure_contract(module):
    # Keep Plow's owner-DM handler. Rename the model-facing tool so leftover
    # prose is never mistaken for a delivered bubble.
    schema = module.PLOW_SEND_SEQUENCE_SCHEMA
    schema["name"] = IMESSAGE
    schema["description"] = IMESSAGE_DESCRIPTION
    schema["parameters"]["properties"]["purpose"] = {
        "type": "string", "enum": ["progress", "answer"],
        "description": "progress is an update and never completes the request. answer is the result the owner should see.",
    }
    options = (((schema.get("parameters") or {}).get("properties") or {}).get("items") or {}).get("items") or {}
    for option in options.get("oneOf") or []:
        props = option.get("properties") or {}
        if props.get("type", {}).get("const") == "text":
            props["reply_to"] = {
                "type": "string",
                "description": "WhatsApp wamid of the bubble this item quotes. Leave it off when the item stands alone, and on iMessage.",
            }
    _publish_item_types(schema)
    module._ANSWER_LAST = (
        f"Owner bubbles only go through {IMESSAGE}. Leftover prose is not delivered. "
        "Never skip that tool; if you do, they hear nothing. "
        "Text, image, video, audio, and a contact card are items of that one call. "
        "The eye reaction and the typing indicator are already on their message. "
        "Do not send a reaction. A reaction is not the reply. "
        "purpose=answer is the result; purpose=progress is a brief update that does "
        "not complete the request. "
        "This thread stays free. A question you can answer in one bubble is answered here. "
        "Work that needs search, a browser, files, or more than this reply is one delegate_task spawn. "
        "The child does not see this chat. Put the whole assignment in the task. "
        "Send one short purpose=progress bubble, then end the turn. "
        "A later status question or progress check is one short bubble on this thread. "
        "Do not take over the child's tools. "
        "A revision is delegate_task action steer with the same subagent_id and the full assignment. "
        "Stop after the answer. Do not answer or quote your own bubbles. "
        "The last message is purpose=answer. "
        "Internal events do not need an opening and do not set language. "
        "A finished child is the result. Send it on this turn with zoen_imessage purpose=answer. "
        "Do not wait for them to write again. An intermediate tick with nothing new stays silent. "
        "Language follows the owner's last human message and VOICE.md, never this note. "
        "Do not narrate tool operations or routine bookkeeping. "
    )
    _publish_imessage(schema)


def _tool_maps(registry):
    maps = []
    tools = getattr(registry, "_tools", None)
    if isinstance(tools, dict):
        maps.append(tools)
    scoped = getattr(registry, "_scoped_tools", None)
    if isinstance(scoped, dict):
        maps.extend(slot for slot in scoped.values() if isinstance(slot, dict))
    return maps


def _plow_turn():
    """The loaded plugin is hermes_plugins.plow_chat_platform. A fresh import is not."""
    for name, module in sys.modules.items():
        if "plow_chat" not in name:
            continue
        turn = getattr(module, "_ACTIVE_TURN", None)
        if turn is not None:
            return turn
    return None


def _arm_stamp():
    """The tool thread does not inherit the turn. The stamp file is the turn."""
    stamp = _read_whatsapp_stamp()
    if not (stamp.get("to") or stamp.get("recipient")):
        return None
    _ACTIVE_TURN = _plow_turn()
    if _ACTIVE_TURN is None:
        return None
    phone = stamp.get("to") or stamp.get("recipient")
    token = _ACTIVE_TURN.set({
        "chat_uid": str(stamp.get("line_id") or "whatsapp"),
        "owner": True,
        "dm": True,
        "authority": True,
        "recall_everywhere": False,
        "no_reply_ok": False,
        "speaker_handle": phone,
        "owner_handle": phone,
        "source_message_id": stamp.get("message_id"),
        "zoen_whatsapp": stamp,
    })

    def reset() -> None:
        _ACTIVE_TURN.reset(token)

    return reset


def _deliver_stamped(args):
    """plow_chat refused the thread. The stamp is enough to send the bubble."""
    stamp = _read_whatsapp_stamp()
    items = (args or {}).get("items") if isinstance(args, dict) else None
    if LOOP is None or not isinstance(items, list):
        return None
    try:
        result = asyncio.run_coroutine_threadsafe(
            _deliver_whatsapp(items, stamp), LOOP,
        ).result(timeout=30)
    except Exception:
        return None
    if not isinstance(result, dict):
        return None
    return json.dumps(result)


def _bind_whatsapp_send(entry):
    handler = getattr(entry, "handler", None)
    if handler is None or getattr(handler, "_zoen_whatsapp_bound", False):
        return entry

    def wrapped(args, **kwargs):
        stamp = _read_whatsapp_stamp()
        if stamp.get("to") or stamp.get("recipient"):
            delivered = _deliver_stamped(args)
            if delivered is not None:
                return delivered
        reset = _arm_stamp()
        try:
            result = handler(args, **kwargs)
        finally:
            if reset is not None:
                reset()
        if isinstance(result, str) and "requires a connected active owner DM" in result:
            delivered = _deliver_stamped(args)
            if delivered is not None:
                return delivered
        return result

    wrapped._zoen_whatsapp_bound = True
    entry.handler = wrapped
    return entry


def _rename_entry(entry, schema):
    entry.name = IMESSAGE
    entry.schema = schema
    if getattr(entry, "description", None) is not None:
        entry.description = IMESSAGE_DESCRIPTION
    return _bind_whatsapp_send(entry)


def watch_registry():
    """Rename plow_send_sequence at registration; Plow scopes tools to HERMES_HOME."""
    try:
        from tools.registry import registry
    except ImportError:
        return
    if getattr(registry, "_zoen_imessage_wrap", False):
        return
    original = registry.register

    def register(name, *args, **kwargs):
        if name == _FACTORY_SEND:
            name = IMESSAGE
            schema = kwargs.get("schema")
            if schema is None and len(args) >= 2 and isinstance(args[1], dict):
                schema = args[1]
            if isinstance(schema, dict):
                schema["name"] = IMESSAGE
                schema["description"] = IMESSAGE_DESCRIPTION
        result = original(name, *args, **kwargs)
        if name == IMESSAGE:
            for tools in _tool_maps(registry):
                entry = tools.get(IMESSAGE)
                if entry is not None:
                    _bind_whatsapp_send(entry)
        return result

    registry.register = register
    registry._zoen_imessage_wrap = True


def _publish_imessage(schema):
    try:
        from tools.registry import registry
    except ImportError:
        return
    watch_registry()
    lock = getattr(registry, "_lock", None)
    with lock if lock is not None else nullcontext():
        moved = False
        for tools in _tool_maps(registry):
            entry = tools.get(IMESSAGE) or tools.pop(_FACTORY_SEND, None)
            if entry is None:
                continue
            tools[IMESSAGE] = _rename_entry(entry, schema)
            tools.pop(_FACTORY_SEND, None)
            moved = True
        if moved and hasattr(registry, "_generation"):
            registry._generation += 1


def _dropped(name: str):
    async def send(self, *args, **kwargs):
        log.debug("zoen-face dropped Hermes %s", name)
        return Dropped()

    send.__name__ = name
    send.__qualname__ = name
    return send


def media_file(raw: str) -> Path | None:
    candidate = Path(raw)
    if not candidate.is_absolute():
        return None
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    if not resolved.is_file():
        return None
    home = Path((os.environ.get("HERMES_HOME") or "").strip() or "/var/lib/hermes")
    for root in (*_MEDIA_ROOTS, home):
        base = root.resolve() if root.exists() else root
        try:
            resolved.relative_to(base)
        except ValueError:
            continue
        return resolved
    return None


def tagged_paths(item: object) -> list[tuple[str, str]] | None:
    if not isinstance(item, dict) or item.get("type") != "text":
        return None
    body = item.get("body")
    if not isinstance(body, str):
        return None
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if not lines:
        return None
    found: list[tuple[str, str]] = []
    for line in lines:
        match = _TAG.fullmatch(line)
        if match is None:
            return None
        found.append((match.group(1), match.group(2)))
    return found


def media_paths(item: object) -> list[str] | None:
    tagged = tagged_paths(item)
    if tagged is None:
        return None
    if any(kind != "MEDIA" for kind, _path in tagged):
        return None
    return [path for _kind, path in tagged]


def expand_items(items: list) -> list[tuple[str, object]]:
    chunks: list[tuple[str, object]] = []
    buffered: list = []

    def flush() -> None:
        if buffered:
            chunks.append(("seq", list(buffered)))
            buffered.clear()

    for item in items:
        tagged = tagged_paths(item)
        if tagged is None:
            buffered.append(item)
            continue
        flush()
        for kind, path in tagged:
            chunks.append(("voice" if kind == "VOICE" else "file", path))
    flush()
    return chunks


def _json(method: str, url: str, headers: dict[str, str], body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode()
    req = Request(url, data=data, method=method, headers=headers)
    try:
        with urlopen(req, timeout=30) as resp:
            raw = resp.read()
            parsed = json.loads(raw.decode()) if raw else {}
            return {"ok": True, "status": resp.status, "body": parsed, "error": None}
    except HTTPError as exc:
        exc.read()
        return {"ok": False, "status": exc.code, "body": None, "error": str(exc.reason)}
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        return {"ok": False, "status": 0, "body": None, "error": str(exc)}


def _put(url: str, headers: dict[str, str], data: bytes) -> dict:
    req = Request(url, data=data, method="PUT", headers=headers)
    try:
        with urlopen(req, timeout=60) as resp:
            resp.read()
            return {"ok": True, "status": resp.status, "error": None}
    except HTTPError as exc:
        exc.read()
        return {"ok": False, "status": exc.code, "error": str(exc.reason)}
    except (URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "status": 0, "error": str(exc)}


def post_voicememo(chat_id: str, path: Path) -> object:
    ctype = _VOICE_TYPES.get(path.suffix.lower())
    if ctype is None:
        return None
    base = (os.environ.get("PLOW_API_BASE") or "").strip().rstrip("/")
    token = (os.environ.get("PLOW_AGENT_TOKEN") or "").strip()
    if not base or not token:
        return None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    payload = path.read_bytes()
    declared = _json(
        "POST",
        f"{base}/v1/chats/{quote(chat_id)}/attachments",
        headers,
        {
            "filename": path.name,
            "content_type": ctype,
            "size_bytes": len(payload),
        },
    )
    upload = declared.get("body") if declared.get("ok") else None
    if not isinstance(upload, dict) or not upload.get("uid") or not upload.get("upload_url"):
        return None
    stored = _put(str(upload["upload_url"]), dict(upload.get("upload_headers") or {}), payload)
    if not stored.get("ok"):
        return None
    sent = _json(
        "POST",
        f"{base}/v1/chats/{quote(chat_id)}/voicememo",
        headers,
        {"attachment_uid": upload["uid"]},
    )
    if not sent.get("ok"):
        return None
    return type("Result", (), {"success": True, "error": None, "message_id": None})()


def _retired_hello(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    body = str(item.get("body") or item.get("text") or "").lower()
    return any(needle in body for needle in _RETIRED_HELLO)


def _retired_text(text: str) -> bool:
    body = (text or "").lower()
    return any(needle in body for needle in _RETIRED_HELLO)


def _retired_payload(raw: object) -> bool:
    if not raw:
        return False
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = None
    body = str(payload.get("body") or "") if isinstance(payload, dict) else text
    return _retired_text(body)


class _DroppedHTTP:
    status = 200

    def read(self) -> bytes:
        return b"{}"

    def __enter__(self) -> "_DroppedHTTP":
        return self

    def __exit__(self, *_args: object) -> bool:
        return False


_HTTP_FILTERED = False


def install_http_filter() -> None:
    """Drop retired hello POSTs that bypass zoen_imessage (face.py intro)."""
    global _HTTP_FILTERED
    if _HTTP_FILTERED:
        return
    _HTTP_FILTERED = True
    orig = urllib.request.urlopen

    def urlopen_filtered(*args, **kwargs):
        req = args[0] if args else kwargs.get("url")
        method = "GET"
        raw = kwargs.get("data")
        target = ""
        if isinstance(req, Request):
            method = req.get_method() or "GET"
            if raw is None:
                raw = req.data
            target = req.full_url
        elif req is not None:
            target = str(req)
        if method.upper() == "POST" and "/messages" in target and _retired_payload(raw):
            log.warning("zoen-face dropped retired hello HTTP POST")
            return _DroppedHTTP()
        return orig(*args, **kwargs)

    urllib.request.urlopen = urlopen_filtered


def _wamid(value) -> str:
    raw = str(value or "").strip()
    if raw.startswith("whatsapp-"):
        raw = raw[len("whatsapp-"):]
    return raw if raw.startswith("wamid.") and len(raw) <= 512 else ""


def _plain_items(items):
    """iMessage rejects a quote field. WhatsApp is the only channel that uses it."""
    cleaned = []
    for item in items:
        if isinstance(item, dict) and "reply_to" in item:
            item = {key: value for key, value in item.items() if key != "reply_to"}
        cleaned.append(item)
    return cleaned


_SILENCE = {"[NO_REPLY]", "NO_REPLY", "[SILENT]", "SILENT", "NO REPLY"}


def is_silence(text: str) -> bool:
    """The model declined. That token is not a message."""
    return " ".join(str(text or "").strip().upper().split()) in _SILENCE


def _read_whatsapp_stamp() -> dict:
    root = Path((os.environ.get("HERMES_HOME") or "").strip() or "/var/lib/hermes")
    try:
        data = json.loads((root / "zoen" / "whatsapp.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def whatsapp_turn_open() -> bool:
    """True while the message being answered arrived on WhatsApp."""
    current = WHATSAPP.get()
    if isinstance(current, dict) and (current.get("to") or current.get("recipient")):
        return True
    try:
        from . import whatsapp_line
    except ImportError:
        whatsapp_line = None
    if whatsapp_line is not None and str(whatsapp_line.LINE.get() or "").startswith("whatsapp:"):
        return True
    stamp = _read_whatsapp_stamp()
    return bool(stamp.get("to") or stamp.get("recipient"))


def guard_whatsapp_tool(tool_name, args, **_kwargs):
    """A WhatsApp turn that posts to Plow Chat lands in the owner's iMessage."""
    if not whatsapp_turn_open():
        return None
    name = str(tool_name or "")
    if name == "plow_send_message":
        action = str((args or {}).get("action") or "send").strip().lower()
        if action == "list":
            return None
        return {
            "action": "block",
            "message": "This turn is on WhatsApp. Use zoen_imessage. plow_send_message texts their iMessage.",
        }
    return None


def _stamp_whatsapp(target) -> None:
    root = Path((os.environ.get("HERMES_HOME") or "").strip() or "/var/lib/hermes")
    path = root / "zoen" / "whatsapp.json"
    try:
        if not isinstance(target, dict):
            path.unlink(missing_ok=True)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "to": target.get("to") or "",
            "recipient": target.get("recipient") or "",
            "message_id": target.get("message_id") or "",
            "line_id": target.get("line_id") or "",
        }), encoding="utf-8")
    except OSError:
        return


def _whatsapp_failure(index, error):
    return {"success": False, "completed": [], "failure": {"index": index, "status": "rejected", "error": error}}


_BUBBLE_PACE = (0.4, 0.55)
_OUTBOUND_WINDOW = 180.0
_RECENT_OUTBOUND: list[tuple[float, str]] = []


def _norm_line(text: str) -> str:
    return " ".join(str(text or "").split())


_TURN_COPIES: list[str] = []


def _remember_outbound(text: str) -> None:
    line = _norm_line(text)
    if line:
        _TURN_COPIES.append(line)
    if len(line) < 8:
        return
    now = time.monotonic()
    _RECENT_OUTBOUND.append((now, line))
    del _RECENT_OUTBOUND[:-40]


def turn_copy(text: str) -> bool:
    """The tool already placed this exact bubble. The gateway copy stays off the chat."""
    line = _norm_line(text)
    return bool(line) and line in _TURN_COPIES


def turn_spoke() -> bool:
    """The tool already answered this turn. Later gateway prose is a second reply."""
    return bool(_TURN_COPIES)


def clear_turn_copies() -> None:
    _TURN_COPIES.clear()


def outbound_echo(text: str) -> bool:
    """A bubble we just sent coming back as if they typed it."""
    line = _norm_line(text)
    if len(line) < 8:
        return False
    now = time.monotonic()
    return any(now - at < _OUTBOUND_WINDOW and sent == line for at, sent in _RECENT_OUTBOUND)


def _quote_allowed(reply, target) -> str:
    """A wamid quotes that bubble. Anything else is sent without a quote."""
    if not isinstance(target, dict):
        return ""
    return _wamid(reply)


def _text_bubbles(body: str) -> list[str]:
    """A line break inside one item is another bubble. WhatsApp would otherwise keep it in the same text."""
    return [line.strip() for line in body.splitlines() if line.strip()]


def _card_identity(item) -> tuple[str, str] | None:
    who = str((item or {}).get("who") or "").strip().lower()
    if who in _CARDS:
        return _CARDS[who]
    name = str((item or {}).get("name") or "").strip()[:80]
    raw = str((item or {}).get("phone") or "").strip()
    phone = "".join(ch for ch in raw if ch.isdigit())
    if not name or not 8 <= len(phone) <= 15:
        return None
    shown = raw if raw.startswith("+") else f"+{phone}"
    return name, shown[:24]


def _write_card(name: str, phone: str) -> str:
    root = Path((os.environ.get("HERMES_HOME") or "").strip() or "/var/lib/hermes") / "zoen" / "cards"
    root.mkdir(parents=True, exist_ok=True)
    slug = "".join(ch for ch in name.lower() if ch.isalnum()) or "card"
    path = root / f"{slug}.vcf"
    path.write_text(
        "BEGIN:VCARD\r\nVERSION:3.0\r\n"
        f"FN:{name}\r\nN:{name};;;;\r\n"
        f"TEL;TYPE=CELL:{phone}\r\nEND:VCARD\r\n",
        encoding="utf-8",
    )
    return str(path)


def _as_imessage_item(item):
    if not isinstance(item, dict):
        return item
    kind = item.get("type")
    path = str(item.get("path") or "").strip()
    if kind in {"image", "video"} and path.startswith("/"):
        return {"type": "text", "body": f"MEDIA:{path}"}
    if kind == "audio" and path.startswith("/"):
        tag = "VOICE" if Path(path).suffix.lower() in _VOICE_TYPES and item.get("voice", True) is not False else "MEDIA"
        return {"type": "text", "body": f"{tag}:{path}"}
    if kind == "contact":
        identity = _card_identity(item)
        if identity is None:
            return item
        return {"type": "text", "body": f"MEDIA:{_write_card(*identity)}"}
    return item


def _split_imessage(items):
    plain = []
    reactions = []
    for item in items:
        if isinstance(item, dict) and item.get("type") == "reaction":
            reactions.append(item)
            continue
        plain.append(_as_imessage_item(item))
    return plain, reactions


def _post_reaction(chat: str, message: str, kind: str) -> bool:
    base = (os.environ.get("PLOW_API_BASE") or "").strip().rstrip("/")
    token = (os.environ.get("PLOW_AGENT_TOKEN") or "").strip()
    if not base or not token:
        return False
    sent = _json(
        "POST",
        f"{base}/v1/chats/{quote(chat)}/messages/{quote(message)}/reactions",
        {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        {"operation": "add", "type": kind},
    )
    return bool(sent.get("ok"))


def _deliver_imessage_reactions(turn, items) -> bool:
    chat = str((turn or {}).get("chat_uid") or "")
    for item in items:
        kind = str(item.get("kind") or "").strip().lower()
        message = str(item.get("message_id") or (turn or {}).get("source_message_id") or "").strip()
        if kind not in _REACTION_KINDS or not chat.startswith("cht_") or not message.startswith("msg_"):
            return False
        if IMESSAGE_REACT is not None:
            if not IMESSAGE_REACT(chat, message, kind):
                return False
            continue
        if not _post_reaction(chat, message, kind):
            return False
    return True


async def _send_whatsapp_reaction(item, target) -> bool:
    kind = str(item.get("kind") or "").strip().lower()
    message = _wamid(item.get("message_id") or item.get("reply_to") or (target or {}).get("message_id"))
    if kind not in _REACTION_KINDS or not message or WHATSAPP_REACT is None:
        return False
    return bool(await WHATSAPP_REACT({"message_id": message, "type": kind}))


async def _send_whatsapp_file(item, target) -> bool:
    path = str(item.get("path") or "").strip()
    if not path.startswith("/") or WHATSAPP_MEDIA is None:
        return False
    spec = {
        "path": path,
        "voice": item.get("type") == "audio" and item.get("voice", True) is not False,
    }
    reply = _quote_allowed(item.get("reply_to"), target)
    if reply:
        spec["reply_to"] = reply
    return bool(await WHATSAPP_MEDIA(spec))


async def _send_whatsapp_contact(item) -> bool:
    identity = _card_identity(item)
    if identity is None or WHATSAPP_CONTACT is None:
        return False
    name, phone = identity
    return bool(await WHATSAPP_CONTACT({"name": name, "phone": phone}))


async def _deliver_whatsapp(items, target=None):
    """One line, one bubble, on the chat they just wrote in."""
    if not isinstance(target, dict):
        return None
    completed = []
    pace = 0
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            return _whatsapp_failure(index, "whatsapp item invalid")
        kind = item.get("type")
        if kind == "pause":
            await asyncio.sleep(min(float(item.get("seconds") or 0), 15))
            continue
        if kind == "reaction":
            if not await _send_whatsapp_reaction(item, target):
                return _whatsapp_failure(index, "whatsapp reaction failed")
            completed.append({"index": index, "type": "reaction"})
            continue
        if kind in {"image", "video", "audio"}:
            if not await _send_whatsapp_file(item, target):
                return _whatsapp_failure(index, "whatsapp media failed")
            completed.append({"index": index, "type": kind})
            continue
        if kind == "contact":
            if not await _send_whatsapp_contact(item):
                return _whatsapp_failure(index, "whatsapp contact failed")
            completed.append({"index": index, "type": "contact"})
            continue
        if kind != "text":
            return _whatsapp_failure(index, "whatsapp item invalid")
        reply = _quote_allowed(item.get("reply_to"), target)
        tagged = tagged_paths(item)
        if tagged:
            for tag, path in tagged:
                spec = {"path": path, "voice": tag == "VOICE"}
                if reply:
                    spec["reply_to"] = reply
                if WHATSAPP_MEDIA is None or not await WHATSAPP_MEDIA(spec):
                    return {"success": False, "completed": completed, "failure": {"index": index, "status": "rejected", "error": "whatsapp media failed"}}
                completed.append({"index": index, "type": "voice" if tag == "VOICE" else "file"})
            continue
        lines = _text_bubbles(str(item.get("body") or ""))
        if not lines or WHATSAPP_DELIVER is None:
            return _whatsapp_failure(index, "whatsapp text missing")
        for offset, line in enumerate(lines):
            if offset:
                await asyncio.sleep(_BUBBLE_PACE[pace % 2])
                pace += 1
            text = line[:4096]
            if is_silence(text) or outbound_echo(text):
                completed.append({"index": index, "type": "text"})
                continue
            _remember_outbound(text)
            payload = {"text": text, "reply_to": reply} if reply else text
            if not await WHATSAPP_DELIVER(payload):
                return {"success": False, "completed": completed, "failure": {"index": index, "status": "rejected", "retryable": False, "error": "not sent. do not resend a bubble that already landed. do not explain the delivery. any replacement is one bubble in their language"}}
            completed.append({"index": index, "type": "text"})
    if not completed:
        texts = [
            line
            for item in items
            if isinstance(item, dict) and item.get("type") == "text"
            for line in _text_bubbles(str(item.get("body") or ""))
        ]
        if texts and all(is_silence(line) for line in texts):
            return {"success": True, "completed": []}
        return _whatsapp_failure(0, "whatsapp text missing")
    return {"success": True, "completed": completed}


def _bubble_text(items) -> str:
    parts = []
    for item in items or []:
        if isinstance(item, dict):
            body = item.get("body") or item.get("text") or ""
        else:
            body = item
        if str(body).strip():
            parts.append(str(body))
    return "\n".join(parts)


def _remember_credits(result, channel: str, credits_only: bool):
    if not isinstance(result, dict) or not result.get("success"):
        return result
    if credits_only:
        mark_told(credits_notice(credits_language()), channel=channel)
    else:
        clear_told(channel=channel)
    return result


def _wrap_sequence(orig_seq, orig_attach, orig_voice):
    async def send_sequence(self, args, turn, receipt=None):
        items = [item for item in list((args or {}).get("items") or []) if not _retired_hello(item)]
        args = {**(args or {}), "items": items}
        if not items:
            return {"success": True, "completed": []}
        if all(isinstance(item, dict) and item.get("type") == "reaction" for item in items):
            return {
                "success": False,
                "completed": [],
                "failure": {
                    "index": 0,
                    "status": "rejected",
                    "error": "The eye is already on their message. Send the reply as text. Do not send a reaction.",
                },
            }
        target = _outbound_target(self, turn)
        channel = _channel_name(target)
        credits_only = credits_is_notice(_bubble_text(items))
        if credits_only and recently_told(channel=channel):
            return {"success": True, "completed": []}
        delivered = await _deliver_whatsapp(items, target)
        if delivered is not None:
            return _remember_credits(delivered, channel, credits_only)
        plain, reactions = _split_imessage(items)
        if reactions and not _deliver_imessage_reactions(turn, reactions):
            return {"success": False, "completed": [], "failure": {"index": 0, "status": "rejected", "error": "reaction failed"}}
        if not plain:
            return {"success": True, "completed": [{"index": index, "type": "reaction"} for index in range(len(reactions))]}
        items = _plain_items(plain)
        args = {**args, "items": items}
        chunks = expand_items(items)
        if not any(kind in {"file", "voice"} for kind, _ in chunks):
            return _remember_credits(await orig_seq(self, args, turn, receipt), channel, credits_only)
        chat_id = (turn or {}).get("chat_uid")
        report = receipt if receipt is not None else {}
        report.update(success=False, completed=[])
        for index, (kind, payload) in enumerate(chunks):
            if kind in {"file", "voice"}:
                path = media_file(str(payload))
                if (
                    path is None
                    or not chat_id
                    or (kind == "voice" and path.suffix.lower() not in _VOICE_TYPES)
                ):
                    report["failure"] = {"index": index, "status": "rejected", "error": "invalid media path or voice format"}
                    return report
                if kind == "file":
                    last = await orig_attach(self, chat_id, str(path))
                elif orig_voice is not None:
                    last = await orig_voice(self, chat_id, str(path))
                else:
                    last = await asyncio.to_thread(post_voicememo, chat_id, path)
            else:
                last = await orig_seq(self, {"items": payload}, turn)
            success = last.get("success", False) if isinstance(last, dict) else getattr(last, "success", False)
            if not success:
                report["failure"] = {"index": index, "status": "rejected", "retryable": False, "error": "not confirmed. do not resend it. do not explain the delivery. any replacement is one bubble in their language"}
                return report
            report["completed"].append({"index": index, "type": kind})
        report["success"] = bool(report["completed"])
        return _remember_credits(report, channel, credits_only)

    send_sequence.__name__ = "send_sequence"
    send_sequence.__qualname__ = "send_sequence"
    return send_sequence


def _stamp_turn_channel(orig_start):
    """Each turn keeps the channel of the message that opened it."""
    async def on_processing_start(self, event):
        result = await orig_start(self, event)
        target = getattr(event, "zoen_whatsapp", None)
        stamped = target if isinstance(target, dict) else None
        active = getattr(self, "_active_turn", None)
        turn = active.get() if active is not None else None
        if isinstance(turn, dict):
            turn["zoen_whatsapp"] = stamped
        WHATSAPP.set(stamped)
        return result

    on_processing_start.__name__ = "on_processing_start"
    on_processing_start.__qualname__ = "on_processing_start"
    return on_processing_start


def _bind_turn_channel(orig_process):
    """The inbound event names the channel. The background turn inherits it."""
    async def process(self, event, session_key):
        target = getattr(event, "zoen_whatsapp", None)
        current = target if isinstance(target, dict) else None
        _stamp_whatsapp(current)
        token = WHATSAPP.set(current)
        try:
            return await orig_process(self, event, session_key)
        finally:
            WHATSAPP.reset(token)
            _stamp_whatsapp(None)

    process.__name__ = "_process_message_background"
    process.__qualname__ = "_process_message_background"
    return process


def silence(adapter_cls) -> None:
    if getattr(adapter_cls, "_zoen_quiet", False):
        return
    adapter_cls._zoen_quiet = True
    install_http_filter()
    orig_seq = getattr(adapter_cls, "send_sequence", None)
    orig_attach = getattr(adapter_cls, "_send_attachment", None)
    orig_voice = getattr(adapter_cls, "send_voice", None)
    if getattr(adapter_cls, "send", None) is not None:
        adapter_cls.send = _wrap_send(adapter_cls.send)
    orig_process = getattr(adapter_cls, "_process_message_background", None)
    if orig_process is not None:
        adapter_cls._process_message_background = _bind_turn_channel(orig_process)
    orig_start = getattr(adapter_cls, "on_processing_start", None)
    if orig_start is not None:
        adapter_cls.on_processing_start = _stamp_turn_channel(orig_start)
    orig_final = getattr(adapter_cls, "_send_retry_is_final", None)
    if orig_final is not None:
        def send_retry_is_final(self, result):
            return isinstance(result, Dropped) or orig_final(self, result)

        adapter_cls._send_retry_is_final = send_retry_is_final
    for name in _SILENT:
        if getattr(adapter_cls, name, None) is None:
            continue
        setattr(adapter_cls, name, _dropped(name))
    if orig_seq is not None and orig_attach is not None:
        adapter_cls.send_sequence = _with_purpose(_wrap_sequence(orig_seq, orig_attach, orig_voice))
    log.info("zoen-face: leftover send dropped; owner bubbles use %s", IMESSAGE)


def _adapter_cls(mod):
    try:
        return getattr(mod, "PlowChatAdapter", None)
    except Exception:
        return None


_ADAPTERS: tuple | None = None
_ADAPTER_KEYS: tuple | None = None


def _scan_adapters():
    seen: set[int] = set()
    found = []
    for name in _KNOWN:
        mod = sys.modules.get(name)
        if mod is None:
            try:
                mod = importlib.import_module(name)
            except ImportError:
                continue
        cls = _adapter_cls(mod)
        if isinstance(cls, type) and id(cls) not in seen:
            seen.add(id(cls))
            found.append(cls)
    for mod in list(sys.modules.values()):
        cls = _adapter_cls(mod)
        if isinstance(cls, type) and callable(getattr(cls, "send", None)):
            if callable(getattr(cls, "send_sequence", None)) and id(cls) not in seen:
                seen.add(id(cls))
                found.append(cls)
    return found


def _adapters():
    global _ADAPTERS, _ADAPTER_KEYS
    keys = tuple(sys.modules)
    if keys != _ADAPTER_KEYS or _ADAPTERS is None:
        _ADAPTERS = tuple(_scan_adapters())
        _ADAPTER_KEYS = tuple(sys.modules)
    yield from _ADAPTERS


def silence_plow_adapter() -> None:
    wrapped = False
    for cls in _adapters():
        silence(cls)
        wrapped = True
    if not wrapped:
        log.warning("zoen-face: plow chat adapter missing, leftover send still live")
