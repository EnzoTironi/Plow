"""Kapso moves WhatsApp bytes. Hermes still runs the turn, so usage stays on the agent."""
from __future__ import annotations

import asyncio
import base64
import functools
import logging
import os
import re
import secrets
from pathlib import Path

log = logging.getLogger("zoen-whatsapp")
_QUIET = None
_TASK = None
_TOKEN = ""
def _prompt(message_id: str) -> str:
    return (
        "This WhatsApp message continues the same owner conversation. "
        "Earlier turns in this session are the history. Answer from that history. "
        "Do not greet again and do not start over. "
        "The only way they see a reply is zoen_imessage, and that call is delivered on WhatsApp. "
        "Each text item is its own bubble. MEDIA:/absolute/path sends the picture here. "
        "VOICE:/absolute/path sends the voice note here. "
        f"This bubble's id is {message_id}. "
        "To quote a bubble, set reply_to on that zoen_imessage item to its id. "
        "A tapback is react.py and lands on this bubble. "
        "Do not mention Kapso, the relay, or this note."
    )
_HOME = ""


def bind(quiet) -> None:
    global _QUIET
    _QUIET = quiet


def relay_base() -> str:
    base = os.environ.get("ZOEN_OAUTH_RELAY_URL", "").strip()
    if base:
        return base.rstrip("/")
    try:
        from hermes_cli.config import load_config
        return str(load_config().get("zoen", {}).get("oauth_relay_url") or "").rstrip("/")
    except Exception:
        return ""


def install(adapter_cls, module) -> None:
    global _TASK
    base = relay_base()
    if not base or _QUIET is None or getattr(adapter_cls, "_zoen_whatsapp", False):
        return
    adapter_cls._zoen_whatsapp = True
    _remember_relay(base)
    _QUIET.WHATSAPP_DELIVER = lambda payload: _send(base, payload)
    _QUIET.WHATSAPP_MEDIA = lambda spec: _send_media(base, spec)
    original_init = adapter_cls.__init__
    original_connect = getattr(adapter_cls, "connect", None)
    original_message = getattr(adapter_cls, "_on_message", None)

    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        _remember(adapter_cls, self, module, base)

    adapter_cls.__init__ = init
    if original_connect is not None:
        @functools.wraps(original_connect)
        async def connect(self, *args, **kwargs):
            _remember(adapter_cls, self, module, base)
            return await original_connect(self, *args, **kwargs)

        adapter_cls.connect = connect
    if original_message is not None:
        @functools.wraps(original_message)
        async def on_message(self, message, chat):
            _remember(adapter_cls, self, module, base)
            return await original_message(self, message, chat)

        adapter_cls._on_message = on_message
    _start(adapter_cls, module, base)


def _remember(adapter_cls, self, module, base) -> None:
    adapter_cls._zoen_live = self
    _start(adapter_cls, module, base)


def _start(adapter_cls, module, base) -> None:
    global _TASK
    if _TASK is not None and not _TASK.done():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    _TASK = loop.create_task(_run(adapter_cls, module, base))


def _digits(value) -> str:
    phone = re.sub(r"\D", "", str(value or ""))
    return phone if 8 <= len(phone) <= 15 else ""


def phone_from_identity(me) -> str:
    """Owner phone on the agent identity. Same digits the relay matches."""
    if not isinstance(me, dict):
        return ""
    for chat in me.get("chats") or []:
        if not isinstance(chat, dict):
            continue
        for person in chat.get("participants") or []:
            if not isinstance(person, dict) or person.get("role") != "owner":
                continue
            if person.get("provider_type") not in (None, "imessage"):
                continue
            phone = _digits(person.get("provider_key"))
            if phone:
                return phone
    return ""


def home_chat_uid(me) -> str:
    """The owner's private chat, so a WhatsApp turn can run before they text iMessage."""
    if not isinstance(me, dict):
        return ""
    for chat in me.get("chats") or []:
        if not isinstance(chat, dict) or chat.get("status") != "active":
            continue
        uid = str(chat.get("uid") or "")
        members = [
            person for person in chat.get("participants") or []
            if isinstance(person, dict) and person.get("type") == "member"
        ]
        if uid.startswith("cht_") and len(members) == 1 and members[0].get("role") == "owner":
            return uid
    return ""


def phone_from_contacts(rows) -> str:
    """Owner handle from the agent's contact book, when the home chat is not up yet."""
    if not isinstance(rows, list):
        return ""
    for person in rows:
        if isinstance(person, dict) and person.get("role") == "owner":
            phone = _digits(person.get("provider_key"))
            if phone:
                return phone
    return ""


def owner_phone(adapter, module) -> str:
    chats = getattr(adapter, "_chats", None) or {}
    for uid, chat in chats.items():
        if not module._owner_dm(chat) or adapter._send_guard(uid) is not None:
            continue
        handle = module._owner_handle(chat) if hasattr(module, "_owner_handle") else ""
        phone = _digits(handle)
        if phone:
            return phone
    return ""


def _agent_secret() -> str:
    """Stable on this VM's volume. The cloud token is only the placeholder."""
    path = os.path.join(os.path.dirname(_token_path()), "agent.id")
    try:
        current = open(path, encoding="utf-8").read().strip()
    except OSError:
        current = ""
    if re.fullmatch(r"[A-Za-z0-9_-]{43,128}", current):
        return current
    current = secrets.token_urlsafe(32)
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(current + "\n")
    return current


def _remember_relay(base: str) -> None:
    path = os.path.join(os.path.dirname(_token_path()), "relay.url")
    try:
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(base.rstrip("/") + "\n")
    except OSError:
        return


def _token_path() -> str:
    root = (os.environ.get("HERMES_HOME") or "/var/lib/hermes").strip() or "/var/lib/hermes"
    return os.path.join(root, "zoen", "whatsapp.token")


def _read_token() -> str:
    try:
        token = open(_token_path(), encoding="utf-8").read().strip()
    except OSError:
        return ""
    return token if re.fullmatch(r"[A-Za-z0-9_-]{43,256}", token) else ""


def _write_token(token: str) -> None:
    path = _token_path()
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(token + "\n")


async def _request(method, url, token, body=None):
    import aiohttp
    headers = {"Authorization": f"Bearer {token}"}
    timeout = aiohttp.ClientTimeout(total=8)
    async with aiohttp.ClientSession(timeout=timeout) as http:
        async with http.request(method, url, json=body, headers=headers, allow_redirects=False) as result:
            if result.status >= 300:
                raise RuntimeError(f"whatsapp_http_{result.status}")
            data = await result.json()
            if not isinstance(data, (dict, list)):
                raise RuntimeError("whatsapp_response_invalid")
            return data


_MIME = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp",
    ".gif": "image/gif", ".mp4": "video/mp4", ".m4a": "audio/mp4", ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg", ".opus": "audio/ogg", ".pdf": "application/pdf",
}


async def _send(base, payload) -> bool:
    target = _QUIET.WHATSAPP.get() if _QUIET is not None else None
    if not target or not _TOKEN:
        return False
    if isinstance(payload, str):
        body = {"text": payload[:4096]}
    elif isinstance(payload, dict):
        body = dict(payload)
    else:
        return False
    if target.get("to"):
        body["to"] = target["to"]
    elif target.get("recipient"):
        body["recipient"] = target["recipient"]
    else:
        return False
    if not body.get("text") and not body.get("media") and not body.get("reaction"):
        return False
    try:
        await _request("POST", base + "/whatsapp/send", _TOKEN, body)
    except Exception:
        log.warning("whatsapp send failed")
        return False
    return True


async def _voice_note(path: Path) -> Path | None:
    if path.suffix.lower() in {".ogg", ".opus"}:
        return path
    out = path.with_suffix(".whatsapp.ogg")
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", str(path), "-c:a", "libopus", "-b:a", "32k", str(out),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
    except OSError:
        return None
    if await proc.wait() != 0 or not out.is_file():
        return None
    return out


async def _send_media(base, spec) -> bool:
    raw = Path(str((spec or {}).get("path") or ""))
    if not raw.is_file():
        return False
    path = raw
    voice = bool((spec or {}).get("voice"))
    if voice:
        note = await _voice_note(raw)
        if note is not None:
            path = note
            voice = True
        else:
            voice = False
    mime = _MIME.get(path.suffix.lower(), "")
    if voice:
        mime = "audio/ogg"
    if not mime:
        return False
    data = path.read_bytes()
    body = {
        "media": {
            "mime": mime,
            "name": path.name,
            "data": base64.b64encode(data).decode(),
            "voice": voice and mime == "audio/ogg",
        },
    }
    reply = str((spec or {}).get("reply_to") or "").strip()
    if reply:
        body["reply_to"] = reply
    return await _send(base, body)


async def _plow_json(agent: str, path: str):
    api = os.environ.get("PLOW_API_BASE", "").strip().rstrip("/")
    if not api or not agent:
        return None
    return await _request("GET", api + path, agent)


async def _register(adapter_cls, module, base) -> str:
    global _HOME
    agent = os.environ.get("PLOW_AGENT_TOKEN", "").strip()
    if not agent:
        return ""
    me = {}
    try:
        found = await _plow_json(agent, "/v1/agents/me")
        if isinstance(found, dict):
            me = found
    except Exception:
        me = {}
    _HOME = home_chat_uid(me) or _HOME
    payload = {}
    if agent == "proxied":
        uid = ""
        if isinstance(me, dict):
            uid = str((me.get("agent") or {}).get("uid") or me.get("uid") or "")
        if not re.fullmatch(r"[a-f0-9]{32}", uid):
            return ""
        payload = {"agent_uid": uid, "secret": _agent_secret()}
    try:
        data = await _request("POST", base + "/whatsapp/register", agent, payload)
    except RuntimeError as exc:
        if str(exc) in {"whatsapp_http_404", "whatsapp_http_409"}:
            return ""
        raise
    token = str(data.get("token") or "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{43,256}", token):
        raise RuntimeError("whatsapp_response_invalid")
    _write_token(token)
    return token


async def _run(adapter_cls, module, base) -> None:
    global _TOKEN
    _TOKEN = _read_token()
    while True:
        try:
            if not _TOKEN:
                _TOKEN = await _register(adapter_cls, module, base)
            if _TOKEN:
                data = await _request("GET", base + "/whatsapp/inbox", _TOKEN)
                for message in data.get("messages") or []:
                    if await _accept(adapter_cls, module, message, base):
                        await _request("POST", base + "/whatsapp/inbox/ack", _TOKEN, {"ids": [message.get("id")]})
        except Exception:
            log.warning("whatsapp poll failed")
        await asyncio.sleep(2)


def _owner_chat(adapter, module):
    chats = getattr(adapter, "_chats", None) or {}
    for uid, chat in chats.items():
        if module._owner_dm(chat) and adapter._send_guard(uid) is None:
            return uid, chat
    return None, None


async def _bytes(url, token) -> tuple[bytes, str]:
    import aiohttp
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as http:
        async with http.get(url, headers={"Authorization": f"Bearer {token}"}, allow_redirects=False) as result:
            if result.status >= 300:
                raise RuntimeError(f"whatsapp_http_{result.status}")
            return await result.read(), str(result.headers.get("content-type") or "")


async def _cache_inbound(module, kind: str, data: bytes, mime: str) -> str:
    if kind == "image" and hasattr(module, "cache_image_from_bytes"):
        ext = ".png" if "png" in mime else ".webp" if "webp" in mime else ".jpg"
        return await asyncio.to_thread(module.cache_image_from_bytes, data, ext)
    if kind == "audio" and hasattr(module, "cache_audio_from_bytes"):
        ext = ".ogg" if "ogg" in mime or "opus" in mime else ".m4a"
        return await asyncio.to_thread(module.cache_audio_from_bytes, data, ext)
    if kind == "video" and hasattr(module, "cache_video_from_bytes"):
        return await asyncio.to_thread(module.cache_video_from_bytes, data, ".mp4")
    root = Path((os.environ.get("HERMES_HOME") or "/var/lib/hermes").strip() or "/var/lib/hermes")
    folder = root / "zoen" / "inbound"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"inbound-{secrets.token_hex(8)}"
    path.write_bytes(data)
    return str(path)


def _event_type(module, kind: str):
    name = {"image": "PHOTO", "audio": "VOICE", "video": "VIDEO", "document": "DOCUMENT", "sticker": "STICKER"}.get(kind)
    enum = getattr(module, "MessageType", None)
    if name and enum is not None and hasattr(enum, name):
        return getattr(enum, name)
    return module._message_type([])


async def _accept(adapter_cls, module, message, base) -> bool:
    live = getattr(adapter_cls, "_zoen_live", None)
    if live is None or not isinstance(message, dict) or not message.get("id"):
        return False
    text = str(message.get("text") or "").strip()
    media_id = str(message.get("media_id") or "")
    if not text and not media_id:
        return False
    chat_uid, _chat = _owner_chat(live, module)
    if chat_uid is None:
        chat_uid = _HOME or None
    if not chat_uid:
        return False
    media_urls, media_types = [], []
    if media_id and _TOKEN:
        try:
            data, mime = await _bytes(base + "/whatsapp/media?id=" + media_id, _TOKEN)
            mime = str(message.get("mime") or mime).split(";")[0].strip()
            path = await _cache_inbound(module, str(message.get("kind") or ""), data, mime)
            media_urls.append(path)
            if mime:
                media_types.append(mime)
        except Exception:
            log.warning("whatsapp media missed")
    if not text and media_urls:
        text = "(attachment)"
    if not text:
        return False
    await live._refresh_current_chat(chat_uid)
    chat = await live.get_chat_info(chat_uid)
    authority, _recall = module._authority(chat, True, human=True)
    event = module.MessageEvent(
        text=text[:4096],
        source=live.build_source(
            chat_id=chat_uid, chat_name=chat["name"], chat_type=chat["type"],
            user_id="whatsapp", user_name=str(message.get("name") or "WhatsApp")[:120],
            role_authorized=True,
        ),
        message_id="whatsapp-" + str(message["id"])[:200],
        message_type=_event_type(module, str(message.get("kind") or "")),
        media_urls=media_urls,
        media_types=media_types,
        channel_prompt=module._channel_prompt(
            chat, "owner", live._chats[chat_uid], live._identity, authority, speak_rule=False,
        ),
    )
    # A real owner turn. internal=True is stored as a notification and stripped
    # from the next turn, which made every WhatsApp message a blank session.
    event.channel_prompt = (event.channel_prompt or "") + "\n" + _prompt(str(message["id"])[:200])
    event.internal = False
    event.authority, event.recall_everywhere = authority, False
    event.reply_to_message_id = message.get("reply_to") or None
    event.reply_to_text = message.get("reply_text") or None
    event.interrupts_run = not media_urls and text != "(attachment)"
    event.zoen_whatsapp = {
        "to": message.get("to"),
        "recipient": message.get("recipient"),
        "message_id": str(message["id"])[:256],
    }
    await live._handoff_message(event)
    return bool(getattr(event, "_gateway_accepted", True))
