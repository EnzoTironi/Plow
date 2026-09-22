"""WhatsApp as its own Hermes platform. Kapso bytes stay behind the relay."""

from __future__ import annotations

import asyncio
import base64
import contextvars
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

_SCRIPTS = Path("/opt/plow/zoen")
_REPO_SCRIPTS = Path(__file__).resolve().parents[3] / "skills/zoen/scripts"
for _path in (_SCRIPTS, _REPO_SCRIPTS):
    if _path.is_dir() and str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from credits import (  # noqa: E402
    clear_told,
    mark_told,
    owner_copy,
)

log = logging.getLogger("zoen-whatsapp")

try:
    from gateway.config import Platform
    from gateway.platforms.base import (
        BasePlatformAdapter,
        MessageEvent,
        MessageType,
        SendResult,
    )
except ImportError:
    BasePlatformAdapter = None
    MessageEvent = None
    MessageType = None
    Platform = None
    SendResult = None

PLATFORM = "zoen-whatsapp"
LINE = contextvars.ContextVar("zoen_whatsapp_line", default="")
_LIVE = None
_QUIET = None
_MEDIA_MIME = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp",
    ".mp4": "video/mp4", ".m4a": "audio/mp4", ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg", ".opus": "audio/ogg", ".pdf": "application/pdf",
}


def bind_outbound(quiet) -> None:
    """Owner bubbles on this line use the live relay send."""
    global _QUIET
    _QUIET = quiet


def digits(value) -> str:
    phone = "".join(ch for ch in str(value or "") if ch.isdigit())
    return phone if 8 <= len(phone) <= 15 else ""


def line_is_bound(line_id: str, bound_phone: str) -> bool:
    raw = str(line_id or "")
    if raw.startswith("whatsapp:"):
        raw = raw[len("whatsapp:"):]
    phone = digits(raw)
    return bool(phone) and phone == digits(bound_phone)


def live_line():
    return _LIVE


def session_chat_id(burst: Burst) -> str:
    """The Hermes session id. A whatsapp: prefix is eaten at the first colon."""
    return burst.address.to or burst.address.recipient


def turn_target(burst: Burst) -> dict:
    target = {"message_id": burst.message_id, "line_id": burst.line_id}
    if burst.address.to:
        target["to"] = burst.address.to
    else:
        target["recipient"] = burst.address.recipient
    if burst.pointed:
        target["reply_to"] = burst.pointed.id
    return target


HANDSHAKE = "oi, eu sou o zoen. pode falar por aqui"


def pairing_handshake(text: str) -> bool:
    """The pairing code is the link, not a request. It never starts a model turn."""
    raw = str(text or "").strip()
    if not re.fullmatch(r"\d{6}", raw):
        return False
    root = (os.environ.get("HERMES_HOME") or "/var/lib/hermes").strip() or "/var/lib/hermes"
    path = os.path.join(root, "zoen", "whatsapp.code")
    try:
        current = open(path, encoding="utf-8").read().strip()
    except OSError:
        return False
    return current == raw


def _arm_plow_turn(target):
    """Plow tools read this context var. Hermes runs them on a thread copied from here.

    plow_chat loads beside this plugin. Importing it at module scope races that order.
    """
    try:
        from plow_chat._transport import _ACTIVE_TURN
    except ImportError:
        return None
    if not isinstance(target, dict):
        return None
    phone = target.get("to") or target.get("recipient")
    token = _ACTIVE_TURN.set({
        "chat_uid": str(target.get("line_id") or "whatsapp"),
        "owner": True,
        "dm": True,
        "authority": True,
        "recall_everywhere": False,
        "no_reply_ok": False,
        "speaker_handle": phone,
        "owner_handle": phone,
        "source_message_id": target.get("message_id"),
        "zoen_whatsapp": target,
    })

    def reset() -> None:
        _ACTIVE_TURN.reset(token)

    return reset


@dataclass(frozen=True)
class Address:
    to: str = ""
    recipient: str = ""

    def __post_init__(self) -> None:
        if bool(self.to) == bool(self.recipient):
            raise ValueError("whatsapp address needs exactly one of to or recipient")

    def relay_fields(self) -> dict:
        if self.to:
            return {"to": self.to}
        return {"recipient": self.recipient}

    @property
    def line_id(self) -> str:
        return f"whatsapp:{self.to or self.recipient}"


@dataclass(frozen=True)
class Bubble:
    id: str
    text: str = ""


@dataclass(frozen=True)
class Burst:
    line_id: str
    message_id: str
    text: str
    address: Address
    pointed: Bubble | None = None


@dataclass(frozen=True)
class TextDelivery:
    body: str
    reply_to: str = ""


@dataclass(frozen=True)
class ReactionDelivery:
    message_id: str
    kind: str


@dataclass(frozen=True)
class TypingDelivery:
    message_id: str


@dataclass(frozen=True)
class ButtonDelivery:
    body: str
    url: str
    label: str = "Autorizar"


Delivery = TextDelivery | ReactionDelivery | TypingDelivery | ButtonDelivery


def address_from(message: dict) -> Address:
    phone = digits(message.get("to"))
    if phone:
        return Address(to=phone)
    recipient = str(message.get("recipient") or "").strip()[:128]
    if recipient:
        return Address(recipient=recipient)
    raise ValueError("whatsapp message has no address")


def bubble_id(value) -> str:
    raw = str(value or "").strip()
    if raw.startswith("whatsapp-"):
        raw = raw[len("whatsapp-"):]
    if raw.startswith("wamid.") and len(raw) <= 512:
        return raw
    return ""


def burst_from_relay(message: dict) -> Burst:
    if not isinstance(message, dict):
        raise ValueError("whatsapp message must be an object")
    message_id = bubble_id(message.get("id")) or str(message.get("id") or "").strip()[:256]
    if not message_id:
        raise ValueError("whatsapp message has no id")
    address = address_from(message)
    pointed_id = bubble_id(message.get("reply_to"))
    pointed = None
    if pointed_id:
        pointed = Bubble(id=pointed_id, text=str(message.get("reply_text") or "")[:500])
    return Burst(
        line_id=address.line_id,
        message_id=message_id,
        text=str(message.get("text") or "").strip()[:4096],
        address=address,
        pointed=pointed,
    )


def relay_body(address: Address, delivery: Delivery) -> dict:
    body = dict(address.relay_fields())
    if isinstance(delivery, TextDelivery):
        body["text"] = delivery.body[:4096]
        quoted = bubble_id(delivery.reply_to)
        if quoted:
            body["reply_to"] = quoted
        return body
    if isinstance(delivery, ReactionDelivery):
        body["reaction"] = {
            "message_id": bubble_id(delivery.message_id) or str(delivery.message_id)[:256],
            "type": delivery.kind,
        }
        return body
    if isinstance(delivery, TypingDelivery):
        body["typing"] = True
        body["message_id"] = str(delivery.message_id)[:256]
        return body
    if isinstance(delivery, ButtonDelivery):
        body["text"] = delivery.body[:1024]
        body["button"] = {"url": delivery.url[:2000], "label": delivery.label[:20] or "Autorizar"}
        return body
    raise TypeError(f"unknown delivery {type(delivery).__name__}")


_LINK = re.compile(r"https?://[^\s<>\"]+")


def authorization_cards(name: str, details: str) -> list[dict]:
    """One WhatsApp card per https link. The URL stays on the button."""
    text = str(details or "")
    urls: list[str] = []

    def take(match):
        urls.append(match.group(0).rstrip(").,]}>\"'"))
        return ""

    _LINK.sub(take, text)
    https = [url for url in urls if url.startswith("https://")]
    if not https:
        return []
    title = str(name or "").strip()
    title = title[:1].upper() + title[1:] if title else "Conexão"
    if "15 minutes" in text or "expires" in text.lower():
        copy = f"{title}\nO link expira em 15 minutos."
    else:
        copy = f"{title}\nToque em Autorizar para conectar."
    return [{"text": copy, "url": url, "label": "Autorizar"} for url in https]


def poll_pause(idle: int) -> float:
    """Seconds until the next inbox check. A delivery checks again in a second."""
    if idle <= 0:
        return 1
    if idle == 1:
        return 2
    return 5


def absorb_poll_error(idle: int, exc: BaseException, transport) -> int:
    """A rejected session is dropped so the next check can register again."""
    if isinstance(exc, HTTPError) and exc.code in (401, 403):
        transport.token = ""
        return 0
    return idle + 1


class RelayTransport:
    """Relay HTTP. The line sets token after the relay session exists."""

    def __init__(self) -> None:
        self.token = ""

    async def get(self, url: str):
        return await asyncio.to_thread(self._call, "GET", url, None)

    async def post(self, url: str, body: dict):
        return await asyncio.to_thread(self._call, "POST", url, body)

    def _call(self, method: str, url: str, body: dict | None):
        data = None if body is None else json.dumps(body).encode()
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            # Cloudflare rejects the default Python-urllib client with error 1010.
            "User-Agent": "Zoen",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(url, data=data, headers=headers, method=method)
        with urlopen(request, timeout=20) as result:
            payload = json.loads(result.read().decode())
        if not isinstance(payload, dict):
            raise RuntimeError("whatsapp_response_invalid")
        return payload


class WhatsAppLine:
    """Inbox in, relay send out. The session key is the WhatsApp line id."""

    def __init__(self, relay_url: str, transport, authorize=None):
        self.relay_url = relay_url.rstrip("/")
        self.transport = transport
        self.authorize = authorize
        self.handle_message = None
        self.reply_target = None
        self._task = None
        self._auth_not_before = 0.0
        self._seen: list[tuple[float, str, str]] = []

    async def connect(self, *, is_reconnect: bool = False) -> bool:
        global _LIVE
        del is_reconnect
        if not self.relay_url:
            return False
        _LIVE = self
        if _QUIET is not None:
            _QUIET.WHATSAPP_DELIVER = self.post_owner
            _QUIET.WHATSAPP_MEDIA = self.post_media
            _QUIET.WHATSAPP_REACT = self.post_reaction
            _QUIET.WHATSAPP_CONTACT = self.post_contact
        if self._task is not None and not self._task.done():
            return True
        self._task = asyncio.get_running_loop().create_task(self._poll())
        return True

    async def _poll(self) -> None:
        idle = 0
        while True:
            try:
                bursts = await self._turn()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                status = exc.code if isinstance(exc, HTTPError) else type(exc).__name__
                log.warning("whatsapp poll failed: %s", status)
                bursts = []
                idle = absorb_poll_error(idle, exc, self.transport)
            else:
                idle = 0 if bursts else idle + 1
            await asyncio.sleep(poll_pause(idle))

    async def _turn(self) -> list[Burst]:
        if self.authorize is not None and not getattr(self.transport, "token", ""):
            now = asyncio.get_running_loop().time()
            if now < self._auth_not_before:
                return []
            token = await self.authorize()
            if not token:
                self._auth_not_before = now + 15
                return []
            self.transport.token = token
        return await self.poll_once()

    def _fresh(self, message: dict) -> bool:
        """One tap can arrive twice. The second copy is the same text within a few seconds."""
        now = time.monotonic()
        seen = [(at, kind, value) for at, kind, value in self._seen if now - at < 20]
        message_id = str(message.get("id") or "")
        text = " ".join(str(message.get("text") or "").split())
        if message_id and any(kind == "id" and value == message_id for _, kind, value in seen):
            self._seen = seen
            return False
        if text and any(kind == "text" and value == text for _, kind, value in seen):
            self._seen = seen
            return False
        if message_id:
            seen.append((now, "id", message_id))
        if text:
            seen.append((now, "text", text))
        self._seen = seen
        return True

    async def poll_once(self) -> list[Burst]:
        data = await self.transport.get(self.relay_url + "/whatsapp/inbox")
        bursts = []
        ids = []
        for message in (data or {}).get("messages") or []:
            if not self._fresh(message):
                if message.get("id"):
                    ids.append(message.get("id"))
                continue
            burst = await self.accept(message)
            if burst is None:
                continue
            bursts.append(burst)
            if message.get("id"):
                ids.append(message.get("id"))
        if ids:
            await self.transport.post(self.relay_url + "/whatsapp/inbox/ack", {"ids": ids})
        return bursts

    async def disconnect(self) -> None:
        global _LIVE
        if _LIVE is self:
            _LIVE = None
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return

    async def send(self, chat_id: str, content: str, reply_to=None, metadata=None):
        copy = owner_copy(content, channel="whatsapp")
        if copy == "":
            return {"success": True, "message_id": None}
        if copy is not None:
            content = copy
        if _QUIET is not None and (
            _QUIET.is_silence(content) or _QUIET.outbound_echo(content) or _QUIET.turn_copy(content)
        ):
            return {"success": True, "message_id": None}
        address = _address_from_line(chat_id)
        quoted = ""
        if isinstance(metadata, dict):
            quoted = str(metadata.get("reply_to") or "")
        if reply_to:
            quoted = str(reply_to)
        body = relay_body(address, TextDelivery(body=str(content or ""), reply_to=quoted))
        await self.transport.post(self.relay_url + "/whatsapp/send", body)
        if _QUIET is not None:
            _QUIET._remember_outbound(str(content or ""))
        if copy is not None:
            mark_told(str(content), channel="whatsapp")
        return {"success": True, "message_id": None}

    async def send_card(self, chat_id: str, text: str, url: str, label: str = "Autorizar") -> dict:
        """A WhatsApp card. The link is the button, not a line of the message."""
        address = _address_from_line(chat_id)
        body = relay_body(address, ButtonDelivery(body=str(text or ""), url=str(url or ""), label=label))
        await self.transport.post(self.relay_url + "/whatsapp/send", body)
        if _QUIET is not None:
            _QUIET._remember_outbound(str(text or ""))
        return {"success": True, "message_id": None}

    def _reply_address(self) -> Address:
        target = self.reply_target if isinstance(self.reply_target, dict) else None
        if _QUIET is not None:
            current = _QUIET.WHATSAPP.get()
            if isinstance(current, dict) and (current.get("to") or current.get("recipient")):
                target = current
        if not isinstance(target, dict):
            raise ValueError("whatsapp reply has no address")
        phone = digits(target.get("to"))
        if phone:
            return Address(to=phone)
        recipient = str(target.get("recipient") or "").strip()[:128]
        if recipient:
            return Address(recipient=recipient)
        raise ValueError("whatsapp reply has no address")

    async def post_owner(self, payload) -> bool:
        """quiet sends a string or {text, reply_to}. The address is this turn's inbound."""
        try:
            if isinstance(payload, str):
                text, reply = payload, ""
            elif isinstance(payload, dict):
                text = str(payload.get("text") or "")
                reply = str(payload.get("reply_to") or "")
            else:
                return False
            if not text.strip():
                return False
            body = relay_body(self._reply_address(), TextDelivery(body=text, reply_to=reply))
            await self.transport.post(self.relay_url + "/whatsapp/send", body)
            return True
        except Exception as exc:
            log.warning("whatsapp send failed: %s", type(exc).__name__)
            return False

    async def post_media(self, spec) -> bool:
        raw = Path(str((spec or {}).get("path") or ""))
        if not raw.is_file():
            return False
        path = raw
        voice = bool((spec or {}).get("voice"))
        if voice:
            note = await _voice_ogg(raw)
            if note is not None:
                path = note
            else:
                voice = False
        mime = "audio/ogg" if voice else _MEDIA_MIME.get(path.suffix.lower(), "")
        if not mime:
            return False
        data = await asyncio.to_thread(path.read_bytes)
        body = dict(self._reply_address().relay_fields())
        body["media"] = {
            "mime": mime,
            "name": path.name[:240],
            "data": base64.b64encode(data).decode(),
            "voice": voice and mime == "audio/ogg",
        }
        reply = str((spec or {}).get("reply_to") or "").strip()
        if reply:
            body["reply_to"] = reply
        try:
            await self.transport.post(self.relay_url + "/whatsapp/send", body)
            return True
        except Exception as exc:
            log.warning("whatsapp media failed: %s", type(exc).__name__)
            return False

    async def post_reaction(self, spec) -> bool:
        try:
            body = relay_body(self._reply_address(), ReactionDelivery(
                message_id=str((spec or {}).get("message_id") or ""),
                kind=str((spec or {}).get("type") or ""),
            ))
            await self.transport.post(self.relay_url + "/whatsapp/send", body)
            return True
        except Exception as exc:
            log.warning("whatsapp reaction failed: %s", type(exc).__name__)
            return False

    async def post_contact(self, spec) -> bool:
        try:
            body = dict(self._reply_address().relay_fields())
            body["contact"] = {
                "name": str((spec or {}).get("name") or "")[:80],
                "phone": str((spec or {}).get("phone") or "")[:24],
            }
            await self.transport.post(self.relay_url + "/whatsapp/send", body)
            return True
        except Exception as exc:
            log.warning("whatsapp contact failed: %s", type(exc).__name__)
            return False

    async def accept(self, message: dict) -> Burst | None:
        burst = burst_from_relay(message)
        if pairing_handshake(burst.text):
            self.reply_target = turn_target(burst)
            await self.send(burst.line_id, HANDSHAKE)
            return burst
        handler = self.handle_message
        if handler is None:
            return None
        clear_told(channel="whatsapp")
        self.reply_target = turn_target(burst)
        quiet_token = _QUIET.WHATSAPP.set(self.reply_target) if _QUIET is not None else None
        token = LINE.set(burst.line_id)
        reset_plow = _arm_plow_turn(self.reply_target)
        try:
            delivered = await handler(burst)
        finally:
            if reset_plow is not None:
                reset_plow()
            LINE.reset(token)
            if quiet_token is not None:
                _QUIET.WHATSAPP.reset(quiet_token)
        if delivered is False:
            return None
        return burst


def _address_from_line(chat_id: str) -> Address:
    raw = str(chat_id or "")
    if raw.startswith("whatsapp:"):
        raw = raw[len("whatsapp:"):]
    phone = digits(raw)
    if phone:
        return Address(to=phone)
    recipient = raw.strip()[:128]
    if recipient:
        return Address(recipient=recipient)
    raise ValueError("whatsapp line id has no address")


def relay_configured() -> bool:
    return bool(os.environ.get("ZOEN_OAUTH_RELAY_URL", "").strip())


async def steer_followup(handler, runner, event, session_key) -> bool:
    """Text during a WhatsApp turn steers that session.

    The gateway handler still owns approvals, drains, and internal wakes.
    A steer that does not land falls through so the adapter can queue it.
    """
    if handler is not None and await handler(event, session_key):
        return True
    text = str(getattr(event, "text", "") or "").strip()
    if not text or getattr(event, "media_urls", None) or runner is None:
        return False
    state = runner._peek_session_state(session_key)
    turn = getattr(state, "turn", None)
    agent = turn.agent if turn is not None else None
    outcome = await runner._resolve_busy_steer_or_redirect(
        event, session_key, "steer", agent
    )
    return bool(getattr(outcome, "steered", False))


def hermes_adapter(cfg, authorize=None):
    """Build the Hermes adapter. Fail loud when this pin has no platform base."""
    if BasePlatformAdapter is None or Platform is None:
        raise RuntimeError("zoen whatsapp needs Hermes BasePlatformAdapter")
    return _HermesLine(cfg, authorize)


if BasePlatformAdapter is not None:

    class _HermesLine(BasePlatformAdapter):
        """One WhatsApp session. The reply uses this adapter's send."""

        def __init__(self, config, authorize=None):
            super().__init__(config, Platform("whatsapp"))
            extra = getattr(config, "extra", None) or {}
            url = str(extra.get("relay_url") or os.environ.get("ZOEN_OAUTH_RELAY_URL") or "")
            self._line = WhatsAppLine(url.strip(), RelayTransport(), authorize=authorize)

        @property
        def authorization_is_upstream(self) -> bool:
            """The relay binds the phone before delivery. Every install, no fixed allowlist."""
            return True

        def set_busy_session_handler(self, handler):
            if handler is None:
                return super().set_busy_session_handler(None)

            async def _on_busy(event, session_key):
                return await steer_followup(handler, self.gateway_runner, event, session_key)

            return super().set_busy_session_handler(_on_busy)

        async def connect(self, *, is_reconnect: bool = False) -> bool:
            self._line.handle_message = self._deliver
            ok = await self._line.connect(is_reconnect=is_reconnect)
            if ok:
                self._mark_connected()
            return ok

        async def disconnect(self) -> None:
            await self._line.disconnect()
            self._mark_disconnected()

        async def send(self, chat_id, content, reply_to=None, metadata=None):
            result = await self._line.send(chat_id, content, reply_to=reply_to, metadata=metadata)
            return SendResult(
                success=bool(result.get("success")),
                message_id=result.get("message_id"),
            )

        async def get_chat_info(self, chat_id):
            return {"name": str(chat_id), "type": "dm"}

        async def _process_message_background(self, event, session_key):
            target = getattr(event, "zoen_whatsapp", None)
            if _QUIET is not None:
                _QUIET.clear_turn_copies()
                _QUIET.LOOP = asyncio.get_running_loop()
                _QUIET._stamp_whatsapp(target if isinstance(target, dict) else None)
            try:
                return await super()._process_message_background(event, session_key)
            finally:
                if _QUIET is not None:
                    _QUIET._stamp_whatsapp(None)

        async def _deliver(self, burst: Burst):
            if not self._message_handler:
                return False
            session_id = session_chat_id(burst)
            source = self.build_source(
                chat_id=session_id,
                chat_type="dm",
                user_id=session_id,
                user_name=session_id,
            )
            # The relay already bound this phone to this agent. Hermes must not
            # keep a second allowlist, or the next install cannot talk.
            source.delivered_via_upstream_relay = True
            pointed = burst.pointed
            event = MessageEvent(
                text=burst.text,
                message_type=MessageType.TEXT,
                source=source,
                message_id=burst.message_id,
                reply_to_message_id=pointed.id if pointed else None,
                reply_to_text=pointed.text if pointed else None,
            )
            event.zoen_whatsapp = turn_target(burst)
            await super().handle_message(event)
            return True


async def _voice_ogg(path: Path) -> Path | None:
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


def register_line(ctx, *, factory=None) -> None:
    """Register WhatsApp on the Hermes platform registry. Does not touch plow_chat."""
    ctx.register_platform(
        name=PLATFORM,
        label="WhatsApp",
        adapter_factory=factory or hermes_adapter,
        check_fn=relay_configured,
        required_env=["ZOEN_OAUTH_RELAY_URL"],
        platform_hint=(
            "You are chatting on WhatsApp. This session is this phone. "
            "A new message steers this session. Reply on this line. "
            "zoen_imessage sends the reaction, the text, the quote, the photo, the video, the voice note, and the contact card. "
            "reply_to is the wamid of the bubble you are answering. "
            "There is no reception observer on this line."
        ),
    )
