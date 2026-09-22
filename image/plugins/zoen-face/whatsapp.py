"""Kapso moves WhatsApp bytes. Hermes still runs the turn, so usage stays on the agent."""
from __future__ import annotations

import asyncio
import base64
import fcntl
import functools
import logging
import os
import re
import secrets
import time
from pathlib import Path
from urllib.parse import quote

log = logging.getLogger("zoen-whatsapp")
WHATSAPP_DOOR = "553798136141"
ONBOARD_SECONDS = 10.0
try:
    import face as _face
except ImportError:
    # Tests load this file before /opt/plow/zoen is on sys.path.
    _face = None
_IMAGE_STAMP = "/etc/zoen-image-id"
_QUIET = None
_TASK = None
_TOKEN = ""
_ANNOUNCE_LOCK = None
_ANNOUNCE_LOOP = None


def _announce_lock() -> asyncio.Lock:
    """One lock per running loop. Tests call asyncio.run more than once."""
    global _ANNOUNCE_LOCK, _ANNOUNCE_LOOP
    loop = asyncio.get_running_loop()
    if _ANNOUNCE_LOCK is None or _ANNOUNCE_LOOP is not loop:
        _ANNOUNCE_LOCK = asyncio.Lock()
        _ANNOUNCE_LOOP = loop
    return _ANNOUNCE_LOCK


def _voice_written() -> bool:
    root = (os.environ.get("HERMES_HOME") or "").strip()
    if not root:
        return False
    try:
        return bool((Path(root) / "zoen" / "VOICE.md").read_text(encoding="utf-8").strip())
    except OSError:
        return False


def _bubble_id(value: str) -> str:
    raw = str(value or "").strip()
    if raw.startswith("whatsapp-"):
        raw = raw[len("whatsapp-"):]
    return raw if raw.startswith("wamid.") and len(raw) <= 512 else ""


def _quote_line(message_id: str, quoted_id: str, quoted_text: str) -> str:
    pointed = _bubble_id(quoted_id)
    current = _bubble_id(message_id) or message_id
    line = f"This inbound is {current}. "
    if pointed:
        said = " ".join(str(quoted_text or "").split())[:240]
        line += f"They replied to {pointed}. "
        if said:
            line += f"That bubble said: {said}. "
    return (
        line
        + "Set reply_to to the wamid of the bubble this item answers. "
        "Quote this inbound when the item answers this message. "
        "Quote an older bubble only when they pointed at it and this item is about that bubble. "
        "Leave reply_to off when the item stands on its own. "
        "The value is the wamid, with no whatsapp- prefix. "
        "The relay sends it as context.message_id. "
    )


def _prompt(message_id: str, *, first: bool = False, pairing: bool = False, quoted_id: str = "", quoted_text: str = "") -> str:
    current = _bubble_id(message_id) or message_id
    if pairing:
        kind = (
            "This is the first WhatsApp turn. They sent only the pairing code. "
            "Follow the first-contact note and introduce yourself: who you are "
            "and what you can do. Do not ask what the code is. "
            "The tapback is like, not question. "
            "The progress line is that introduction, not a comment on the code. "
        )
    elif first:
        kind = (
            "This is the first WhatsApp turn, right after they linked the line. "
            "Follow the first-contact note and answer them. "
        )
    else:
        kind = (
            "This inbound is the request, together with the other human messages "
            "still unanswered in this burst. Answer that whole burst. "
        )
    return (
        f"<request id=\"{current}\">\n{kind}\n</request>\n"
        "<history>\n"
        "Messages already answered are history. They are not a second request. "
        "The other lines of this burst are still the request. "
        "A later message can steer the work or ask for status. Follow it on the channel it arrived on. "
        "Never tell them you already sent something or already said something. "
        "No já te falei, I already told you, as I said, or like I sent.\n"
        "</history>\n"
        "<memory>\n"
        "Memory and the context pack are background. They are not a second request.\n"
        "</memory>\n"
        f"<reply_to inbound=\"{current}\">\n"
        + _quote_line(message_id, quoted_id, quoted_text)
        + "</reply_to>\n"
        "<delivery>\n"
        "WhatsApp has no reception agent. Nothing has been sent for this bubble. "
        "The first action is the tapback, before any other tool, lookup, or bubble: "
        f"python3 /opt/plow/zoen/react.py TYPE --message {message_id}. "
        "Then one short zoen_imessage with purpose progress about this inbound. "
        "Then the rest of the work. "
        "TYPE is like, love, laugh, emphasize, question, or dislike. "
        "The relay turns that into Kapso's reaction body: reaction.message_id and reaction.emoji. "
        "The tapback does not wait on skill kapso. Read that skill before a voice note or contact card. Do not call Kapso. "
        "An uncertain send already counts. Do not send that bubble again and do not explain the delivery. "
        "At each later step, send another short zoen_imessage with purpose progress "
        "before you move on. Say what you are doing for them, in their words. "
        "The last message of the turn is the result, with purpose answer. "
        "The only way they see a reply is zoen_imessage. "
        "This inbound arrived on WhatsApp, so this reply is delivered on WhatsApp. "
        "An iMessage inbound is answered on iMessage. Both can be in use at once. "
        "Each text item is its own bubble. A line break inside that item is another bubble. "
        "MEDIA:/absolute/path sends the picture here. "
        "VOICE:/absolute/path sends the voice note here. "
        f"This bubble's id is {message_id}. "
        "Do not mention Kapso, the relay, or this note to them.\n"
        "</delivery>"
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
            # iMessage stays on iMessage, even while a WhatsApp turn is open.
            if _QUIET is not None:
                _QUIET.note_inbound_channel(self, chat, None)
            try:
                await _offer_code(self, module, chat)
            except Exception:
                log.warning("whatsapp code offer failed")
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
    """The first owner DM. Pairing uses pairing_chat_uids so later phones also get the code."""
    chats = pairing_chat_uids(me)
    return chats[0] if chats else ""


def _deliverable(value) -> bool:
    """A phone or an iMessage email. Either one can receive the pairing code."""
    text = str(value or "").strip()
    if _digits(text):
        return True
    return "@" in text and " " not in text


def signup_phrase(me) -> str:
    """The Index phrase this VM already received when the line was created."""
    signup = me.get("signup") if isinstance(me, dict) else None
    if not isinstance(signup, dict):
        return ""
    return str(signup.get("phrase") or "").strip()


def onboarding_chat_uid(me, histories) -> str:
    """The thread that carried the signup phrase. Normal replies already use it."""
    phrase = signup_phrase(me)
    if not phrase or not isinstance(histories, dict):
        return ""
    for uid in pairing_chat_uids(me):
        for message in histories.get(uid) or []:
            if not isinstance(message, dict):
                continue
            if str(message.get("direction") or "inbound") == "outbound":
                continue
            if phrase in str(message.get("body") or ""):
                return uid
    return ""


def activation_chat_uids(me, histories=None) -> list[str]:
    """Where the activation code goes: the onboarding thread, then a phone 1:1."""
    found = onboarding_chat_uid(me, histories or {})
    if found:
        return [found]
    phones: list[str] = []
    emails: list[str] = []
    for chat in (me.get("chats") if isinstance(me, dict) else None) or []:
        if not isinstance(chat, dict) or chat.get("status") != "active":
            continue
        uid = str(chat.get("uid") or "")
        if uid not in pairing_chat_uids(me):
            continue
        members = [
            person for person in chat.get("participants") or []
            if isinstance(person, dict) and person.get("type") == "member"
        ]
        key = str(members[0].get("provider_key") or "") if len(members) == 1 else ""
        if _digits(key):
            phones.append(uid)
        elif _deliverable(key):
            emails.append(uid)
    return phones or emails


def pairing_chat_uids(me) -> list[str]:
    """Every active 1:1 with a phone or iMessage email."""
    if not isinstance(me, dict):
        return []
    found: list[str] = []
    for chat in me.get("chats") or []:
        if not isinstance(chat, dict) or chat.get("status") != "active":
            continue
        uid = str(chat.get("uid") or "")
        if not uid.startswith("cht_"):
            continue
        members = [
            person for person in chat.get("participants") or []
            if isinstance(person, dict) and person.get("type") == "member"
        ]
        if len(members) != 1:
            continue
        if not _deliverable(members[0].get("provider_key")):
            continue
        if uid not in found:
            found.append(uid)
    return found


def phone_from_contacts(rows) -> str:
    """Owner handle from the agent's contact book, when the home chat is not up yet."""
    phones = owner_phones(rows)
    return phones[0] if phones else ""


def owner_phones(rows) -> list[str]:
    """Every owner phone in the book. The line texts each of them the pairing code."""
    return [handle for handle in owner_handles(rows) if _digits(handle)]


def owner_handles(rows) -> list[str]:
    """Owner phones, then owner iMessage emails. Either can receive the first text."""
    if not isinstance(rows, list):
        return []
    phones: list[str] = []
    emails: list[str] = []
    for person in rows:
        if not isinstance(person, dict) or person.get("role") != "owner":
            continue
        key = str(person.get("provider_key") or "").strip()
        phone = _digits(key)
        if phone and phone not in phones:
            phones.append(phone)
        elif _deliverable(key) and key.lower() not in emails:
            emails.append(key)
    return phones + emails


def phones_in_chats(me) -> set[str]:
    found: set[str] = set()
    if not isinstance(me, dict):
        return found
    for chat in me.get("chats") or []:
        if not isinstance(chat, dict):
            continue
        for person in chat.get("participants") or []:
            if not isinstance(person, dict) or person.get("type") != "member":
                continue
            phone = _digits(person.get("provider_key"))
            if phone:
                found.add(phone)
    return found


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


def pairing_bubbles(code: str, door: str = WHATSAPP_DOOR) -> list[str]:
    """One iMessage bubble per line. Blank lines in one body would stay a single text."""
    return [
        "oi, eu sou o zoen",
        "pode continuar conversando comigo por aqui",
        "ou conversar comigo pelo whatsapp, clicando no link e enviando o código",
        f"https://wa.me/{door}?text={code}",
        "Enzo me criou. consigo conectar seus apps, mais de mil, onde você precisar",
    ]


def pairing_message(code: str, door: str = WHATSAPP_DOOR) -> str:
    """The same choice as one body, for a chat that is created by its first message."""
    return "\n\n".join(pairing_bubbles(code, door))


def _code_path() -> str:
    return os.path.join(os.path.dirname(_token_path()), "whatsapp.code")


def _pairing_code() -> str:
    """Stable on this volume so a retry keeps the same code."""
    path = _code_path()
    try:
        current = open(path, encoding="utf-8").read().strip()
    except OSError:
        current = ""
    if re.fullmatch(r"\d{6}", current):
        return current
    current = str(secrets.randbelow(900000) + 100000)
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(current + "\n")
    return current


def _install_path() -> str:
    return os.path.join(os.path.dirname(_token_path()), "whatsapp.install")


def _agent_uid(me) -> str:
    if not isinstance(me, dict):
        return ""
    uid = str((me.get("agent") or {}).get("uid") or me.get("uid") or "")
    return uid if re.fullmatch(r"[A-Za-z0-9_-]{4,128}", uid) else ""


def _install_lines() -> list[str]:
    try:
        return [line.strip() for line in open(_install_path(), encoding="utf-8").read().splitlines()]
    except OSError:
        return []


def _read_install() -> str:
    lines = _install_lines()
    return lines[0] if lines else ""


def _read_image() -> str:
    lines = _install_lines()
    return lines[1] if len(lines) > 1 else ""


def _image_stamp() -> str:
    """Identity of the image that is running. The volume remembers this, not a hand-bumped number."""
    override = os.environ.get("ZOEN_IMAGE_ID", "").strip()
    if re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", override):
        return override
    try:
        baked = open(_IMAGE_STAMP, encoding="utf-8").read().strip()
    except OSError:
        baked = ""
    return baked if re.fullmatch(r"[a-f0-9]{64}", baked) else ""


def _image_changed() -> bool:
    stamp = _image_stamp()
    return bool(stamp) and _read_image() != stamp


def _write_install(uid: str) -> None:
    path = _install_path()
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(uid + "\n" + _image_stamp() + "\n")


def _pairing_settled() -> bool:
    """This image already texted the code on this volume."""
    return not _image_changed() and bool(_sent_chats())


def _clear_sent_claims() -> None:
    path = _code_path() + ".lock"
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        for suffix in (".sent", ".progress"):
            try:
                os.remove(_code_path() + suffix)
            except OSError:
                pass
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _onboarded_path() -> str:
    return os.path.join(os.path.dirname(_token_path()), "whatsapp.onboarded")


def _whatsapp_onboarded() -> bool:
    return os.path.isfile(_onboarded_path())


def _mark_whatsapp_onboarded() -> None:
    path = _onboarded_path()
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.close(descriptor)


def pairing_turn(messages, code: str) -> bool:
    """True when WhatsApp has only the pairing code, so that code opens the chat."""
    if not re.fullmatch(r"\d{6}", str(code or "")):
        return False
    saw = False
    for item in messages or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("media_id") or "").strip():
            return False
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        if text != code:
            return False
        saw = True
    return saw


def _release_previous_install(uid: str) -> None:
    """One-click keeps the line volume. A new agent, or a new image, texts the code once."""
    if not uid:
        return
    same_agent = _read_install() == uid
    if same_agent and not _image_changed():
        return
    _clear_sent_claims()
    if not same_agent:
        try:
            os.remove(_token_path())
        except OSError:
            pass
        try:
            os.remove(_onboarded_path())
        except OSError:
            pass
    _write_install(uid)


def _forget_code() -> None:
    """The collided code is dead. Its replacement has to be texted once."""
    try:
        os.remove(_code_path())
    except OSError:
        pass
    _clear_sent_claims()


def _sent_chats() -> set[str]:
    try:
        lines = open(_code_path() + ".sent", encoding="utf-8").read().splitlines()
    except OSError:
        return set()
    return {
        line.strip() for line in lines
        if line.strip().startswith(("cht_", "tel:", "mail:"))
    }


def _write_sent(chats: set[str]) -> None:
    path = _code_path() + ".sent"
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        for uid in sorted(chats):
            handle.write(uid + "\n")


def _claim_chat(chat: str) -> bool:
    """True only the first time. Recorded before the POST so the 2s poll cannot send twice."""
    if not chat:
        return False
    path = _code_path() + ".lock"
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        chats = _sent_chats()
        if chat in chats:
            return False
        chats.add(chat)
        _write_sent(chats)
        return True
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _release_chat(chat: str) -> None:
    path = _code_path() + ".lock"
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        chats = _sent_chats()
        chats.discard(chat)
        _write_sent(chats)
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _code_announced(code: str, chat: str = "") -> bool:
    sent = _sent_chats()
    if chat:
        return chat in sent
    return bool(sent)


def _progress_path() -> str:
    return _code_path() + ".progress"


def _read_progress() -> dict[str, int]:
    try:
        lines = open(_progress_path(), encoding="utf-8").read().splitlines()
    except OSError:
        return {}
    found: dict[str, int] = {}
    for line in lines:
        chat, _, count = line.partition("\t")
        chat = chat.strip()
        if chat.startswith(("cht_", "tel:", "mail:")) and count.strip().isdigit():
            found[chat] = int(count.strip())
    return found


def _write_progress(rows: dict[str, int]) -> None:
    path = _progress_path()
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        for chat, count in sorted(rows.items()):
            handle.write(f"{chat}\t{count}\n")


def _mark_chat_sent(chat: str) -> None:
    """Caller holds the announce lock. A chat lands here only after every bubble."""
    chats = _sent_chats()
    chats.add(chat)
    _write_sent(chats)


def _cards_sync(chat: str, deadline: float) -> dict:
    """Send both vCards on this chat. Stops when the onboarding budget is gone."""
    base = os.environ.get("PLOW_API_BASE", "")
    if _face is None or "plow.example" in base or not os.environ.get("PLOW_AGENT_TOKEN", "").strip():
        return {"ok": False, "skipped": "no live token"}
    return _face.cards(chat=chat, deadline=deadline)


async def _attach_cards(chat: str, deadline: float) -> None:
    """Both contact cards, inside the time still left of the 10 second burst."""
    if not str(chat).startswith("cht_"):
        return
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        log.warning("onboarding cards missed the 10s budget")
        return
    try:
        await asyncio.wait_for(
            asyncio.to_thread(_cards_sync, chat, deadline),
            timeout=remaining,
        )
    except (Exception, SystemExit, asyncio.TimeoutError):
        log.warning("onboarding cards stopped inside the 10s budget")


async def _announce_code(agent: str, chat: str, code: str) -> None:
    """Every prebuilt bubble, before cards. A short budget must not drop the link."""
    if not agent or not chat:
        return
    api = os.environ.get("PLOW_API_BASE", "").strip().rstrip("/")
    if not api:
        return
    bubbles = pairing_bubbles(code)
    send_cards = False
    async with _announce_lock():
        path = _code_path() + ".lock"
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            if chat in _sent_chats():
                return
            progress = _read_progress()
            done = progress.get(chat, 0)
            url = f"{api}/v1/chats/{quote(chat, safe='')}/messages"
            for bubble in bubbles[done:]:
                try:
                    await _request("POST", url, agent, {"body": bubble, "format": "none"})
                except _Uncertain:
                    log.warning("onboarding bubble uncertain; continuing")
                except RuntimeError as exc:
                    if done == 0 and str(exc).startswith("whatsapp_http_"):
                        raise
                    log.warning("onboarding text stopped")
                    break
                done += 1
                progress[chat] = done
                _write_progress(progress)
            if done >= len(bubbles):
                progress.pop(chat, None)
                _write_progress(progress)
                _mark_chat_sent(chat)
                send_cards = True
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)
    if send_cards:
        await _attach_cards(chat, time.monotonic() + ONBOARD_SECONDS)


async def _announce_chats(agent: str, chats: list[str], code: str) -> None:
    for chat in chats:
        try:
            await _announce_code(agent, chat, code)
        except Exception:
            log.warning("whatsapp code announce failed")


def _tel_key(phone: str) -> str:
    return "tel:" + phone


def _handle_claim(handle: str) -> tuple[str, str, str]:
    """Claim key, chat member, and idempotency stamp for a phone. Email is not a destination."""
    phone = _digits(handle)
    if not phone:
        return "", "", ""
    return _tel_key(phone), f"+{phone}", phone


async def _open_pairing(agent: str, line_uid: str, handle: str, code: str) -> None:
    """Start the 1:1 by sending the code once. The owner does not have to text first."""
    key, member, stamp = _handle_claim(handle)
    if not agent or not line_uid or not member:
        return
    api = os.environ.get("PLOW_API_BASE", "").strip().rstrip("/")
    if not api or not _claim_chat(key):
        return
    deadline = time.monotonic() + ONBOARD_SECONDS
    try:
        data = await _request(
            "POST",
            f"{api}/v1/chats",
            agent,
            {
                "line_uid": line_uid,
                "members": [member],
                "body": pairing_message(code),
                "idempotency_key": f"zoen-wa-{code}-{stamp}",
            },
        )
    except RuntimeError as exc:
        if str(exc).startswith("whatsapp_http_"):
            _release_chat(key)
        raise
    uid = str((data or {}).get("uid") or "") if isinstance(data, dict) else ""
    if uid.startswith("cht_"):
        _claim_chat(uid)
        await _attach_cards(uid, deadline)


async def _chat_history(agent: str, uid: str) -> list:
    try:
        found = await _plow_json(agent, f"/v1/chats/{quote(uid, safe='')}/messages?limit=30")
    except Exception:
        return []
    rows = found.get("data") if isinstance(found, dict) else found if isinstance(found, list) else []
    return rows if isinstance(rows, list) else []


async def _push_pairing(agent: str, me: dict) -> None:
    """Text the code into the onboarding chat, the same send a normal reply uses."""
    _release_previous_install(_agent_uid(me))
    code = _pairing_code()
    uids = pairing_chat_uids(me)
    histories: dict = {}
    if len(uids) > 1:
        loaded = await asyncio.gather(*(_chat_history(agent, uid) for uid in uids))
        histories = dict(zip(uids, loaded))
    targets = activation_chat_uids(me, histories)
    if len(uids) == 1 and not targets:
        targets = list(uids)
    await _announce_chats(agent, targets or ([_HOME] if _HOME else []), code)
    if targets:
        return
    line = me.get("line") if isinstance(me, dict) and isinstance(me.get("line"), dict) else {}
    line_uid = str(line.get("uid") or "")
    own = _digits(line.get("provider_key"))
    known = phones_in_chats(me)
    rows: list = []
    try:
        found = await _plow_json(agent, "/v1/contacts")
        if isinstance(found, list):
            rows = found
    except Exception:
        rows = []
    for handle in owner_phones(rows):
        if handle == own or handle in known:
            continue
        try:
            await _open_pairing(agent, line_uid, handle, code)
        except Exception as exc:
            log.warning("whatsapp code open failed: %s", exc)


async def _offer_code(adapter, module, chat) -> None:
    """A new SMS or iMessage 1:1 also gets the pairing code, not only the first owner."""
    if _TOKEN:
        return
    uid = chat if isinstance(chat, str) else str((chat or {}).get("uid") or "")
    if not uid.startswith("cht_"):
        return
    info = (getattr(adapter, "_chats", None) or {}).get(uid) or {}
    if adapter._send_guard(uid) is not None:
        return
    handle = module._owner_handle(info) if info and hasattr(module, "_owner_handle") else ""
    if info and not module._owner_dm(info) and not _digits(handle):
        return
    agent = os.environ.get("PLOW_AGENT_TOKEN", "").strip()
    if not agent:
        return
    await _announce_code(agent, uid, _pairing_code())


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


class _Uncertain(Exception):
    """The phone may already have this bubble. A retry would duplicate it."""


_RECENT: dict[str, float] = {}
_RECENT_TTL = 180.0


def _text_key(body: dict) -> str:
    text = body.get("text")
    if not isinstance(text, str) or not text.strip():
        return ""
    return f"{body.get('to') or body.get('recipient')}\n{text.strip()}"


def _claim_text(key: str) -> bool:
    """True when this exact bubble is already in flight or already counted as sent."""
    now = time.monotonic()
    stale = [item for item, at in _RECENT.items() if now - at > _RECENT_TTL]
    for item in stale:
        del _RECENT[item]
    if key in _RECENT:
        return True
    _RECENT[key] = now
    return False


def _release_text(key: str) -> None:
    _RECENT.pop(key, None)


async def _request(method, url, token, body=None):
    import aiohttp
    headers = {"Authorization": f"Bearer {token}"}
    timeout = aiohttp.ClientTimeout(total=20)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as http:
            async with http.request(method, url, json=body, headers=headers, allow_redirects=False) as result:
                if result.status in (408, 409, 429) or result.status >= 500:
                    raise _Uncertain()
                if result.status >= 300:
                    error = ""
                    try:
                        payload = await result.json()
                        if isinstance(payload, dict):
                            error = str(payload.get("error") or "")
                    except Exception:
                        error = ""
                    raise RuntimeError(f"whatsapp_http_{result.status}" + (f"_{error}" if error else ""))
                data = await result.json()
                if not isinstance(data, (dict, list)):
                    raise RuntimeError("whatsapp_response_invalid")
                return data
    except _Uncertain:
        raise
    except (asyncio.TimeoutError, TimeoutError, aiohttp.ClientError):
        raise _Uncertain() from None


_MIME = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp",
    ".gif": "image/gif", ".mp4": "video/mp4", ".m4a": "audio/mp4", ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg", ".opus": "audio/ogg", ".pdf": "application/pdf",
}


def _address(message) -> dict:
    if isinstance(message, dict) and message.get("to"):
        return {"to": message["to"]}
    if isinstance(message, dict) and message.get("recipient"):
        return {"recipient": message["recipient"]}
    return {}


async def _send(base, payload) -> bool:
    if not _TOKEN:
        return False
    if isinstance(payload, str):
        body = {"text": payload[:4096]}
    elif isinstance(payload, dict):
        body = dict(payload)
    else:
        return False
    if not body.get("to") and not body.get("recipient"):
        target = _QUIET.WHATSAPP.get() if _QUIET is not None else None
        body.update(_address(target if isinstance(target, dict) else None))
    if not body.get("to") and not body.get("recipient"):
        return False
    if not body.get("text") and not body.get("media") and not body.get("reaction") and body.get("typing") is not True:
        return False
    key = _text_key(body)
    if key and _claim_text(key):
        return True
    try:
        await _request("POST", base + "/whatsapp/send", _TOKEN, body)
    except _Uncertain:
        log.warning("whatsapp send uncertain; not retrying")
        return True
    except Exception:
        if key:
            _release_text(key)
        log.warning("whatsapp send failed")
        return False
    if body.get("text") or body.get("media"):
        _stop_typing()
    return True


_TYPING_TASK = None


def _stop_typing() -> None:
    global _TYPING_TASK
    task = _TYPING_TASK
    _TYPING_TASK = None
    if task is not None:
        task.cancel()


async def _typing(base, message) -> None:
    message_id = str((message or {}).get("id") or "").strip()
    if not message_id:
        return
    await _send(base, {"typing": True, "message_id": message_id[:256], **_address(message)})


async def _typing_session(base, message) -> None:
    try:
        await _typing(base, message)
        for _ in range(8):
            await asyncio.sleep(20)
            await _typing(base, message)
    except asyncio.CancelledError:
        return


def _arm_typing(base, message) -> None:
    global _TYPING_TASK
    _stop_typing()
    _TYPING_TASK = asyncio.create_task(_typing_session(base, message))


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
    _release_previous_install(_agent_uid(me))
    code = _pairing_code()
    payload = {"code": code}
    if agent == "proxied":
        uid = _agent_uid(me)
        if not re.fullmatch(r"[a-f0-9]{32}", uid):
            return ""
        payload = {"agent_uid": uid, "secret": _agent_secret(), "code": code}
    try:
        data = await _request("POST", base + "/whatsapp/register", agent, payload)
    except RuntimeError as exc:
        if str(exc) == "whatsapp_http_409_code_taken":
            _forget_code()
            return ""
        if str(exc).startswith("whatsapp_http_404") or str(exc).startswith("whatsapp_http_409"):
            return ""
        raise
    if data.get("waiting"):
        return ""
    token = str(data.get("token") or "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{43,256}", token):
        raise RuntimeError("whatsapp_response_invalid")
    _write_token(token)
    return token


async def _adopt_install(agent: str) -> bool:
    """True once this volume is known to belong to the running agent."""
    global _TOKEN
    if not agent:
        return False
    try:
        found = await _plow_json(agent, "/v1/agents/me")
    except Exception:
        return False
    uid = _agent_uid(found if isinstance(found, dict) else {})
    if not uid:
        return False
    previous = _read_install()
    if previous != uid or _image_changed():
        _release_previous_install(uid)
        if previous != uid:
            _TOKEN = ""
    elif not _TOKEN:
        _TOKEN = _read_token()
    return True


def _chats_answered() -> bool:
    """A mailed claim is not the reply. Only a chat that already got the bubbles counts."""
    return not _image_changed() and any(uid.startswith("cht_") for uid in _sent_chats())


async def _ensure_pairing(agent: str) -> bool:
    """Send the prebuilt bubbles to a chat the user's text already created.

    Returns True once every such chat has the full reply. No chat yet means
    wait: do not open one and do not email.
    """
    if not agent:
        return False
    if _chats_answered():
        return True
    try:
        found = await _plow_json(agent, "/v1/agents/me")
    except Exception:
        return False
    if not isinstance(found, dict):
        return False
    _release_previous_install(_agent_uid(found))
    uids = pairing_chat_uids(found)
    if not uids:
        return False
    pending = [uid for uid in uids if uid not in _sent_chats()]
    if pending:
        await _announce_chats(agent, pending, _pairing_code())
    return all(uid in _sent_chats() for uid in uids)


def poll_pause(idle: int) -> float:
    """Seconds until the next inbox check. A delivery passes 0 and checks again in a second."""
    if idle <= 0:
        return 1
    return (2, 5, 15, 30)[min(idle, 4) - 1]


async def _run(adapter_cls, module, base) -> None:
    global _TOKEN
    _TOKEN = ""
    adopted = False
    idle = 0
    while True:
        found = False
        try:
            agent = os.environ.get("PLOW_AGENT_TOKEN", "").strip()
            if not adopted:
                adopted = await _adopt_install(agent)
                if not adopted and not _TOKEN:
                    _TOKEN = _read_token()
            if not _TOKEN:
                _TOKEN = await _register(adapter_cls, module, base)
            await _ensure_pairing(agent)
            if _TOKEN:
                data = await _request("GET", base + "/whatsapp/inbox", _TOKEN)
                code = ""
                try:
                    code = open(_code_path(), encoding="utf-8").read().strip()
                except OSError:
                    code = ""
                real, codes = [], []
                for message in data.get("messages") or []:
                    if code and str(message.get("text") or "").strip() == code:
                        codes.append(message)
                    else:
                        real.append(message)
                for message in real:
                    if await _accept(adapter_cls, module, message, base):
                        await _request("POST", base + "/whatsapp/inbox/ack", _TOKEN, {"ids": [message.get("id")]})
                # The code opens WhatsApp. That turn introduces Zoen. It is not a question.
                if pairing_turn(data.get("messages") or [], code) and not _whatsapp_onboarded():
                    if await _accept(adapter_cls, module, codes[-1], base, pairing=True):
                        _mark_whatsapp_onboarded()
                    else:
                        codes = codes[:-1]
                for message in codes:
                    await _request("POST", base + "/whatsapp/inbox/ack", _TOKEN, {"ids": [message.get("id")]})
                found = bool(real or codes)
        except Exception:
            log.warning("whatsapp poll failed")
        idle = 0 if found else idle + 1
        await asyncio.sleep(poll_pause(0 if found else idle))


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


def _clean_inbound(text: str) -> str:
    cleaned = str(text or "").strip()
    if cleaned == "[object Object]":
        return ""
    return cleaned


async def _hear(text: str, urls: list, kinds: list) -> str:
    """The spoken words, the same way an iMessage voice memo reaches the turn."""
    cleaned = _clean_inbound(text)
    if not urls:
        return cleaned
    try:
        from listen import with_transcripts
    except ImportError:
        return cleaned or "(attachment)"
    try:
        heard = await asyncio.to_thread(with_transcripts, urls, kinds, cleaned or "(attachment)")
    except Exception:
        log.warning("whatsapp transcript missed")
        return cleaned or "(attachment)"
    if isinstance(heard, str) and heard.strip() and heard.strip() != "[object Object]":
        return heard.strip()
    return cleaned or "(attachment)"


def _inbound_suffix(kind: str, mime: str) -> str:
    lowered = (mime or "").lower()
    if kind == "image" or lowered.startswith("image/"):
        if "png" in lowered:
            return ".png"
        if "webp" in lowered:
            return ".webp"
        return ".jpg"
    if kind == "audio" or lowered.startswith("audio/"):
        if "mpeg" in lowered or "mp3" in lowered:
            return ".mp3"
        if "mp4" in lowered or "m4a" in lowered or "aac" in lowered:
            return ".m4a"
        return ".ogg"
    if kind == "video" or lowered.startswith("video/"):
        return ".mp4"
    return ""


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
    path = folder / f"inbound-{secrets.token_hex(8)}{_inbound_suffix(kind, mime)}"
    path.write_bytes(data)
    return str(path)


def _event_type(module, kind: str):
    name = {"image": "PHOTO", "audio": "VOICE", "video": "VIDEO", "document": "DOCUMENT", "sticker": "STICKER"}.get(kind)
    enum = getattr(module, "MessageType", None)
    if name and enum is not None and hasattr(enum, name):
        return getattr(enum, name)
    return module._message_type([])


async def _accept(adapter_cls, module, message, base, pairing: bool = False) -> bool:
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
            kind = str(message.get("kind") or "")
            path = await _cache_inbound(module, kind, data, mime)
            media_urls.append(path)
            if mime:
                media_types.append(mime)
            elif kind == "audio":
                media_types.append("audio/ogg")
        except Exception:
            log.warning("whatsapp media missed")
    if media_urls or text == "[object Object]":
        text = await _hear(text, media_urls, media_types)
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
    event.zoen_pairing_code = pairing
    event.channel_prompt = (event.channel_prompt or "") + "\n" + _prompt(
        str(message["id"])[:200],
        first=pairing or not _voice_written(),
        pairing=pairing,
        quoted_id=str(message.get("reply_to") or ""),
        quoted_text=str(message.get("reply_text") or ""),
    )
    event.internal = False
    event.authority, event.recall_everywhere = authority, False
    event.reply_to_message_id = message.get("reply_to") or None
    event.reply_to_text = message.get("reply_text") or None
    # Steer the talker. An interrupt would abort the turn and the task with it.
    event.interrupts_run = False
    _arm_typing(base, message)
    event.zoen_whatsapp = {
        "to": message.get("to"),
        "recipient": message.get("recipient"),
        "message_id": str(message["id"])[:256],
        "reply_to": str(message.get("reply_to") or "")[:256],
    }
    if _QUIET is not None:
        _QUIET.note_inbound_channel(live, chat_uid, event.zoen_whatsapp)
    await live._handoff_message(event)
    return bool(getattr(event, "_gateway_accepted", True))


def boot_announce() -> int:
    """Answer the chat the user already opened. Their text creates it; this only sends."""
    agent = os.environ.get("PLOW_AGENT_TOKEN", "").strip()
    if not agent:
        return 1
    while True:
        try:
            if asyncio.run(_ensure_pairing(agent)):
                return 0
        except Exception:
            log.warning("whatsapp boot announce failed")
        time.sleep(0.2)


if __name__ == "__main__":
    raise SystemExit(boot_announce())
