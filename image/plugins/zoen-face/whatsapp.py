"""Kapso moves WhatsApp bytes. Hermes still runs the turn, so usage stays on the agent."""
from __future__ import annotations

import asyncio
import fcntl
import logging
import os
import re
import secrets
import time
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

log = logging.getLogger("zoen-whatsapp")
WHATSAPP_DOOR = "553798136141"
ONBOARD_SECONDS = 10.0
try:
    import face as _face
except ImportError:
    # Tests load this file before /opt/plow/zoen is on sys.path.
    _face = None
_IMAGE_STAMP = "/etc/zoen-image-id"
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








_HOME = ""












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


def pairing_link(code: str, door: str = WHATSAPP_DOOR, uid: str = "") -> str:
    """The tap arms this install, then opens WhatsApp with the code filled in."""
    if re.fullmatch(r"[a-f0-9]{32}", uid) and re.fullmatch(r"\d{6}", code):
        return f"https://auth.tryzoen.com/whatsapp/go/{uid}/{code}"
    return f"https://wa.me/{door}?text={code}"


def pairing_bubbles(code: str, door: str = WHATSAPP_DOOR, uid: str = "") -> list[str]:
    """One iMessage bubble per line. Blank lines in one body would stay a single text."""
    return [
        "oi, eu sou o zoen",
        "pode continuar conversando comigo por aqui",
        "ou conversar comigo pelo whatsapp, clicando no link e enviando o código",
        pairing_link(code, door, uid),
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
        # The previous install already published this code. A new agent needs its own.
        try:
            os.remove(_code_path())
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


async def _announce_code(agent: str, chat: str, code: str, uid: str = "") -> None:
    """Every prebuilt bubble, before cards. A short budget must not drop the link."""
    if not agent or not chat:
        return
    api = os.environ.get("PLOW_API_BASE", "").strip().rstrip("/")
    if not api:
        return
    bubbles = pairing_bubbles(code, uid=uid)
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


async def _announce_chats(agent: str, chats: list[str], code: str, uid: str = "") -> None:
    for chat in chats:
        try:
            await _announce_code(agent, chat, code, uid)
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




def _token_path() -> str:
    root = (os.environ.get("HERMES_HOME") or "/var/lib/hermes").strip() or "/var/lib/hermes"
    return os.path.join(root, "zoen", "whatsapp.token")


def _share_zoen() -> None:
    """Pairing runs as root and the gateway runs as hermes. Both read this directory."""
    root = os.path.dirname(_token_path())
    try:
        os.makedirs(root, mode=0o777, exist_ok=True)
        os.chmod(root, 0o777)
    except OSError:
        return
    for current, dirnames, filenames in os.walk(root):
        for name in dirnames:
            try:
                os.chmod(os.path.join(current, name), 0o777)
            except OSError:
                pass
        for name in filenames:
            try:
                os.chmod(os.path.join(current, name), 0o666)
            except OSError:
                pass


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










async def _request(method, url, token, body=None, headers=None):
    import aiohttp
    sent = {}
    if token:
        sent["Authorization"] = f"Bearer {token}"
    if headers:
        sent.update(headers)
    timeout = aiohttp.ClientTimeout(total=20)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as http:
            async with http.request(method, url, json=body, headers=sent, allow_redirects=False) as result:
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





















async def _plow_json(agent: str, path: str):
    api = os.environ.get("PLOW_API_BASE", "").strip().rstrip("/")
    if not api or not agent:
        return None
    return await _request("GET", api + path, agent)


async def _register(base) -> str:
    global _HOME, _LAST_BIND
    _ping_relay(base)
    agent = os.environ.get("PLOW_AGENT_TOKEN", "").strip()
    if not agent:
        _LAST_BIND = "noagent"
        return ""
    me = {}
    try:
        found = await _plow_json(agent, "/v1/agents/me")
        if isinstance(found, dict):
            me = found
    except Exception as exc:
        me = {}
        _LAST_BIND = "me" + type(exc).__name__
    _HOME = home_chat_uid(me) or _HOME
    _release_previous_install(_agent_uid(me))
    code = _pairing_code()
    payload = {"code": code, "pair": code}
    if agent == "proxied":
        uid = _agent_uid(me)
        if not re.fullmatch(r"[a-f0-9]{32}", uid):
            if not _LAST_BIND.startswith("me"):
                _LAST_BIND = "nouid"
            return ""
        secret = _agent_secret()
        # Three fields, the same shape the exe proxy already forwards. A field
        # named pair, a longer path, or a rewritten secret never arrives.
        # The pairing link is what tells the relay which code the phone sent.
        payload = {"agent_uid": uid, "secret": secret, "code": code}
    try:
        data = await _request(
            "POST",
            base + "/whatsapp/register",
            agent,
            payload,
        )
    except _Uncertain:
        _LAST_BIND = "uncertain"
        return ""
    except RuntimeError as exc:
        _LAST_BIND = re.sub(r"[^a-z0-9]", "", str(exc).lower())[:24] or "http"
        if str(exc) == "whatsapp_http_409_code_taken":
            _forget_code()
            try:
                await _ensure_pairing(agent)
            except Exception:
                log.warning("whatsapp code refresh failed")
            return ""
        if str(exc).startswith("whatsapp_http_404") or str(exc).startswith("whatsapp_http_409"):
            return ""
        raise
    if data.get("waiting"):
        _LAST_BIND = "waiting"
        return ""
    token = str(data.get("token") or "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{43,256}", token):
        _LAST_BIND = "badtoken"
        raise RuntimeError("whatsapp_response_invalid")
    _write_token(token)
    _LAST_BIND = "bound"
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
    agent_uid = _agent_uid(found)
    _release_previous_install(agent_uid)
    uids = pairing_chat_uids(found)
    if not uids:
        return False
    pending = [uid for uid in uids if uid not in _sent_chats()]
    if pending:
        await _announce_chats(agent, pending, _pairing_code(), agent_uid)
    return all(uid in _sent_chats() for uid in uids)






















_PINGED = False
_LAST_BIND = "none"


def _ping_relay(base: str) -> None:
    """One GET per process, so a poll that reaches the relay shows up once."""
    global _PINGED, _LAST_BIND
    if _PINGED:
        return
    _PINGED = True
    root = (base or "https://zoen-oauth-relay.agenttironi.workers.dev").rstrip("/")
    token = os.environ.get("PLOW_AGENT_TOKEN", "").strip()
    request = Request(
        root + "/whatsapp/ping",
        headers={"User-Agent": "Zoen", "Authorization": f"Bearer {token}"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=4) as result:
            _LAST_BIND = f"ping{result.status}"
            result.read()
    except (OSError, URLError) as exc:
        _LAST_BIND = "ping" + type(exc).__name__
        log.warning("whatsapp ping failed")


def boot_announce() -> int:
    """Answer the chat the user already opened. Their text creates it; this only sends."""
    agent = os.environ.get("PLOW_AGENT_TOKEN", "").strip()
    if not agent:
        return 1
    while True:
        try:
            if asyncio.run(_ensure_pairing(agent)):
                relay = (os.environ.get("ZOEN_OAUTH_RELAY_URL") or "https://zoen-oauth-relay.agenttironi.workers.dev").strip().rstrip("/")
                try:
                    asyncio.run(_register(relay))
                except Exception:
                    log.warning("whatsapp boot register failed")
                finally:
                    _share_zoen()
                return 0
        except Exception:
            log.warning("whatsapp boot announce failed")
        time.sleep(0.2)


if __name__ == "__main__":
    raise SystemExit(boot_announce())
