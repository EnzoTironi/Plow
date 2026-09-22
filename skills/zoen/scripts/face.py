#!/usr/bin/env python3
"""Name the iMessage card Zoen and put the monster on it.

    face.py cards
    face.py rename
    face.py card --force
    face.py bake

Cards are the vCards. The image bakes them; send only fills Zoen's number.
The line sends both cards with onboarding, inside 10 seconds.
The agent does not send them again.
Rename is install. `intro` is a retired alias and sends nothing.
Auth: PLOW_API_BASE + PLOW_AGENT_TOKEN, optional PLOW_ACCOUNT_TOKEN
or ~/.config/plow/token.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
from memory import remember  # noqa: E402
from net import request  # noqa: E402

NAME = "Zoen"
CARD_NAME = "Zoen.vcf"
ENZO_NAME = "Enzo"
ENZO_CARD_NAME = "Enzo.vcf"
ENZO_TEL = "+5531999941160"
ENZO_TEL_DISPLAY = "+55 31 99994-1160"
BAKED_TEL = "__ZOEN_TEL__"
CARD_DIR = Path("/usr/share/doc/zoen")
HELLO = {
    "en": (
        "hey, I'm Zoen, your little monster that makes your dreams come true",
        "save my card so you know it's me",
        "Enzo made me. save his card for questions or trouble",
    ),
    "pt": (
        "oi, eu sou o Zoen, o monstrinho que faz seus sonhos acontecerem",
        "salva meu cartão pra você saber que sou eu",
        "Enzo me criou. salva o cartão dele pra dúvida ou problema",
    ),
}
SETUP_NAMES = {"plow setup"}
SETUP_PREFIX = "plow, not your owner"
HELLO_MARKERS = (
    "I'm Zoen",
    "eu sou o Zoen",
    "a gente te ajuda",
    "we'll help.",
    "+55 31 99994-1160",
)
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


_OPENERS = frozenset({
    "oi", "oii", "oie", "olá", "ola", "alo", "alô", "aloo",
    "hey", "hi", "hello", "eai", "e ai", "e aí",
    "fala", "salve", "opa", "yo", "bom dia", "boa tarde", "boa noite",
    "tudo bem", "tudo bom", "td bem",
})


def normalized_line(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower()).rstrip(".!?,")


def real_request(text: str) -> bool:
    """A first message that already asks for work. A hello or the Index phrase does not."""
    spoken = (text or "").strip()
    if not spoken or spoken.startswith("/"):
        return False
    if re.fullmatch(r"\d{6}", spoken):
        return False
    folded = normalized_line(spoken)
    if folded in _OPENERS:
        return False
    if "agent-index/" in folded or folded.startswith("set this up for me"):
        return False
    return True


def _inbound_bodies(history: Any) -> list[str]:
    bodies = []
    for item in newest_rows(history):
        if str(item.get("direction") or "inbound") == "outbound" or is_noise_row(item):
            continue
        body = str(item.get("body") or "").strip()
        if body:
            bodies.append(body)
    return bodies


def earlier_owner_messages(event: Any, http: Http | None = None) -> int:
    """Owner texts already in the chat before this one. Zero when this is the first."""
    try:
        history = chat_history(event, http)
    except (SystemExit, OSError, TypeError, ValueError, KeyError):
        return 0
    if not history:
        return 0
    current = normalized_line(spoken_text(event) or str(getattr(event, "text", None) or ""))
    bodies = _inbound_bodies(history)
    if not bodies:
        return 0
    if current and normalized_line(bodies[0]) == current:
        return max(0, len(bodies) - 1)
    return len(bodies)


def greeting_due(event: Any, http: Http | None = None) -> bool:
    """Greet on a real first request or on the second message. The pairing code is not a turn."""
    text = spoken_text(event) or str(getattr(event, "text", None) or "")
    if real_request(text):
        return True
    return earlier_owner_messages(event, http) >= 1


def resolve_language(event: Any, http: Http | None = None) -> str:
    """Language already written in VOICE.md. Empty until that file exists."""
    del event, http
    return voice_language() or ""


def saved_pairing_code() -> str:
    """The code this volume already claimed. Empty until WhatsApp pairing writes it."""
    root = (os.environ.get("HERMES_HOME") or "").strip()
    if not root:
        return ""
    try:
        code = (Path(root) / "zoen" / "whatsapp.code").read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return code if re.fullmatch(r"\d{6}", code) else ""


def pairing_intro_prompt(language: str = "") -> str:
    """Context for the WhatsApp turn that is only the pairing code."""
    tongue = (
        "Write in the language of their words. "
        "The pairing code is not a language signal. "
        "Write VOICE.md with the language you chose. "
    )
    if language:
        tongue += f"VOICE.md already says language: {language}. Keep it. "
    return (
        "\n<first_contact>\n"
        "They just linked WhatsApp by sending the pairing code. "
        "That code is not a question and not a request. "
        "Do not ask what the code is. Do not repeat the code. "
        "They have not met you on WhatsApp. Introduce yourself: who you are "
        "and what you can do. You are Zoen, their personal agent. Enzo made you. "
        "You can connect their apps, more than a thousand, wherever they need. "
        "One short introduction in their language. Do not send contact cards. "
        "Do not run face.py cards. Do not send a phone number or 'a gente te ajuda'. "
        + tongue
        + "This session, learn what to call them with plow_name_contact. "
        "Write VOICE.md this turn if it is missing. If it already exists, still "
        "introduce yourself on WhatsApp.\n"
        "</first_contact>"
    )


def first_contact_prompt(
    whatsapp: bool = False,
    *,
    offer_whatsapp: bool | None = None,
    language: str = "",
) -> str:
    if whatsapp:
        tongue = (
            "Write in the language of their words. "
            "The pairing code is not a language signal. "
            "Write VOICE.md with the language you chose. "
        )
        if language:
            tongue += f"VOICE.md already says language: {language}. Keep it. "
        return (
            "\n<first_contact>\n"
            "VOICE.md is missing. They just linked WhatsApp. The iMessage "
            "onboarding already finished within 10 seconds, including both "
            "contact cards, that Enzo made you, and that you can connect "
            "their apps — more than a thousand connections and MCPs — "
            "wherever they need. Do not send cards on WhatsApp. Do not run "
            "face.py cards. Do not repeat that intro. Answer them via "
            "zoen_imessage, which delivers on WhatsApp, in their language, "
            "like @tryZoen: one short line, then their request. "
            + tongue
            + "Do not copy an older intro from this chat. Never send a phone "
            "number or 'a gente te ajuda'. If their message is only the "
            "pairing code, do not repeat it. Handle their request. This "
            "session, learn what to call them with plow_name_contact. "
            "Write VOICE.md this turn.\n"
            "</first_contact>"
        )
    offer = not whatsapp if offer_whatsapp is None else offer_whatsapp
    choice = ""
    if offer:
        code = saved_pairing_code()
        if code:
            choice = (
                "These bubbles already went out on this chat, with both "
                "contact cards, within 10 seconds: oi, eu sou o zoen; stay "
                "here; or send the code on WhatsApp; then the link with "
                f"{code}. Do not send those lines again. Do not invent "
                "another code or another link.\n"
            )
    return (
        "\n<first_contact>\n"
        "VOICE.md is missing. The onboarding burst already went out on "
        "iMessage within 10 seconds: who you are, staying here or WhatsApp, "
        "both contact cards, that Enzo made you, and that you can connect "
        "their apps — more than a thousand connections and MCPs — wherever "
        "they need. Do not send that burst again. Do not run face.py cards. "
        "Answer them via zoen_imessage, like @tryZoen, in their language. "
        "Do not copy an older intro from this chat. Never send a phone "
        "number or 'a gente te ajuda'. "
        + choice
        + "Handle their request. This session, learn what to call them with "
        "plow_name_contact. Write VOICE.md this turn.\n"
        "</first_contact>"
    )
CARD_AFTER = 2
DIRECTED = (
    "Zoen is a software-factory agent in this iMessage group. "
    "People may also use another contact name for the same number. "
    "Is the latest message for Zoen to act on or answer? "
    "Reply with one token only: yes or no. "
    "yes if they name Zoen, reply to Zoen, assign Zoen work, ask Zoen, "
    "or continue a task Zoen was just doing with nobody else addressed since. "
    "no if they talk to each other, greet the room, name someone else, "
    "or say something merely interesting. Unsure: no."
)
MENTION = re.compile(r"(?<!\w)@?zoen(?!\w)", re.IGNORECASE)
GOAL_NAMES = {"goal check"}
PEEK = (
    (["id", "-F"], "full name"),
    (["id", "-un"], "mac username"),
    (["git", "config", "--global", "user.email"], "email"),
)
RENDER = (
    "Rewrite these iMessage bubbles in the same language as the user. "
    "Keep the meaning and the same number of bubbles. Max two lines each. "
    "No trailing period. JSON only: {\"hello\":[\"...\"]}"
)
Http = Callable[..., dict]
Put = Callable[[str, dict[str, str], bytes], dict]


def _out(payload: dict) -> int:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if payload.get("ok", True) else 1


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_credentials() -> None:
    here = Path(__file__).resolve()
    load_env_file(Path("plow-credentials"))
    load_env_file(here.parents[3] / "plow-credentials")


def account_token() -> str:
    if "PLOW_ACCOUNT_TOKEN" in os.environ:
        return os.environ["PLOW_ACCOUNT_TOKEN"].strip()
    xdg = (os.environ.get("XDG_CONFIG_HOME") or "").strip()
    candidates = []
    if xdg:
        candidates.append(Path(xdg) / "plow" / "token")
    candidates.append(Path.home() / ".config" / "plow" / "token")
    for path in candidates:
        if path.is_file():
            return path.read_text().strip()
    return ""


def credentials() -> tuple[str, dict[str, str]]:
    load_credentials()
    base = (os.environ.get("PLOW_API_BASE") or "").strip().rstrip("/")
    token = (os.environ.get("PLOW_AGENT_TOKEN") or "").strip()
    if not base or not token:
        raise SystemExit("face: set PLOW_API_BASE and PLOW_AGENT_TOKEN")
    return base, {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }


def card_root() -> Path:
    env = (os.environ.get("ZOEN_CARD_DIR") or "").strip()
    return Path(env) if env else CARD_DIR


def baked_card(filename: str) -> Path | None:
    here = Path(__file__).resolve()
    for root in (card_root(), CARD_DIR, here.parents[3] / "docs", here.parent):
        path = root / filename
        if path.is_file():
            return path
    return None


def card_bytes(name: str, tel: str, *, filename: str, photo: bool) -> bytes:
    path = baked_card(filename)
    if path is not None:
        data = path.read_bytes()
        if BAKED_TEL.encode("ascii") in data:
            return data.replace(BAKED_TEL.encode("ascii"), tel.encode("ascii"))
        return data
    jpeg = photo_path().read_bytes() if photo else None
    return vcard(name, tel, jpeg)


def bake_cards(dest: str | Path | None = None) -> dict[str, Any]:
    root = Path(dest) if dest else card_root()
    root.mkdir(parents=True, exist_ok=True)
    zoen = vcard(NAME, BAKED_TEL, photo_path().read_bytes())
    enzo = vcard(ENZO_NAME, ENZO_TEL)
    (root / CARD_NAME).write_bytes(zoen)
    (root / ENZO_CARD_NAME).write_bytes(enzo)
    return {"ok": True, "dir": str(root), "cards": [CARD_NAME, ENZO_CARD_NAME]}


def photo_path() -> Path:
    env = (os.environ.get("ZOEN_CARD_PHOTO") or "").strip()
    if env:
        path = Path(env)
        if not path.is_file():
            raise SystemExit(f"face: photo not found: {path}")
        return path
    here = Path(__file__).resolve()
    for candidate in (
        Path("/usr/share/doc/zoen/zoen-card.jpg"),
        here.parents[3] / "docs" / "zoen-card.jpg",
        here.parent / "zoen-card.jpg",
    ):
        if candidate.is_file():
            return candidate
    raise SystemExit("face: no zoen-card.jpg")


def fold_line(line: str) -> str:
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    chunks: list[bytes] = []
    while raw:
        take = 75 if not chunks else 74
        piece = raw[:take]
        while piece.endswith(b"\n") or (len(piece) == take and (piece[-1] & 0xC0) == 0x80):
            piece = piece[:-1]
        if not piece:
            piece = raw[:1]
        chunks.append(piece)
        raw = raw[len(piece) :]
    first, *rest = (chunk.decode("utf-8") for chunk in chunks)
    return "\r\n ".join([first, *rest])


def vcard(name: str, tel: str, jpeg: bytes | None = None) -> bytes:
    lines = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        f"N:{name};;;;",
        f"FN:{name}",
        f"TEL;TYPE=CELL,VOICE,pref:{tel}",
    ]
    if jpeg:
        photo = base64.b64encode(jpeg).decode("ascii")
        lines.append(fold_line(f"PHOTO;ENCODING=b;TYPE=JPEG:{photo}"))
    lines.extend(["END:VCARD", ""])
    return "\r\n".join(lines).encode("utf-8")


def home_chat(me: dict, explicit: str | None = None) -> str:
    value = (explicit or os.environ.get("PLOW_HOME_CHANNEL") or "").strip()
    if value.startswith("cht_"):
        return value
    for chat in me.get("chats") or []:
        if not isinstance(chat, dict) or chat.get("status") != "active":
            continue
        uid = str(chat.get("uid") or "")
        members = [
            part
            for part in chat.get("participants") or []
            if isinstance(part, dict) and part.get("type") == "member"
        ]
        if uid.startswith("cht_") and len(members) == 1 and members[0].get("role") == "owner":
            return uid
    raise SystemExit("face: no home chat")


def message_rows(messages: Any) -> list[dict]:
    rows = messages.get("data") if isinstance(messages, dict) else None
    if not isinstance(rows, list):
        return []
    return [item for item in rows if isinstance(item, dict)]


def already_sent(messages: Any, filename: str = CARD_NAME) -> bool:
    for item in message_rows(messages):
        if item.get("direction") != "outbound":
            continue
        for att in item.get("attachments") or []:
            if isinstance(att, dict) and att.get("filename") == filename:
                return True
    return False


def hello_sent(messages: Any) -> bool:
    for item in message_rows(messages):
        if item.get("direction") != "outbound":
            continue
        body = str(item.get("body") or "")
        if any(marker in body for marker in HELLO_MARKERS):
            return True
    return False


def latest_inbound(messages: Any) -> str:
    for item in message_rows(messages):
        if item.get("direction") == "inbound":
            return str(item.get("body") or "")
    return ""


def newest_rows(messages: Any) -> list[dict]:
    rows = message_rows(messages)
    if any(item.get("created_at") or item.get("sent_at") for item in rows):
        return sorted(
            rows,
            key=lambda item: str(item.get("created_at") or item.get("sent_at") or ""),
            reverse=True,
        )
    return list(rows)


def is_noise_row(item: dict) -> bool:
    if item.get("attachments"):
        return False
    body = str(item.get("body") or "")
    if not body.strip():
        return True
    lower = body.lower()
    return is_setup_text(body) or "gateway shutting down" in lower


def newest_is_inbound(messages: Any) -> bool:
    for item in newest_rows(messages):
        if is_noise_row(item):
            continue
        return item.get("direction") == "inbound"
    return False


def _completion_text(body: Any) -> str:
    if not isinstance(body, dict):
        return str(body or "")
    choices = body.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message")
        if isinstance(message, dict) and message.get("content"):
            return str(message["content"])
        if first.get("text"):
            return str(first["text"])
    return str(body.get("output") or "")


def complete_http(
    system: str,
    user: str,
    *,
    http: Http,
    base: str,
    headers: dict[str, str] | None = None,
    max_tokens: int = 8,
    model: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if model:
        payload["model"] = model
    return http(
        "POST",
        f"{base}/v1/chat/completions",
        headers=headers,
        body=payload,
    )


def complete(
    system: str,
    user: str,
    *,
    http: Http,
    base: str,
    headers: dict[str, str] | None = None,
    max_tokens: int = 8,
    model: str | None = None,
) -> str | None:
    result = complete_http(
        system,
        user,
        http=http,
        base=base,
        headers=headers,
        max_tokens=max_tokens,
        model=model,
    )
    if not result.get("ok"):
        return None
    return _completion_text(result.get("body"))


def render_hello(
    text: str,
    *,
    http: Http,
    base: str,
    headers: dict[str, str] | None,
) -> list[str]:
    source = "\n---\n".join(HELLO["en"])
    result = http(
        "POST",
        f"{base}/v1/chat/completions",
        headers=headers,
        body={
            "max_tokens": 240,
            "messages": [
                {"role": "system", "content": RENDER},
                {"role": "user", "content": f"{text}\n---\n{source}"},
            ],
        },
    )
    if not result.get("ok"):
        return list(HELLO["en"])
    raw = _completion_text(result.get("body")).strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            return list(HELLO["en"])
        try:
            parsed = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return list(HELLO["en"])
    bubbles = parsed.get("hello") if isinstance(parsed, dict) else parsed
    if not isinstance(bubbles, list) or len(bubbles) != len(HELLO["en"]):
        return list(HELLO["en"])
    out = [str(item).strip() for item in bubbles]
    if any(not item or len(item.splitlines()) > 2 for item in out):
        return list(HELLO["en"])
    return out


def hello_for(
    lang: str,
    spoken: str,
    *,
    http: Http | None = None,
    base: str = "",
    headers: dict[str, str] | None = None,
) -> list[str]:
    if lang in HELLO:
        return list(HELLO[lang])
    if http is None or not base:
        return list(HELLO["en"])
    return render_hello(spoken, http=http, base=base, headers=headers)


def is_group(event: Any) -> bool:
    source = getattr(event, "source", None)
    kind = getattr(source, "chat_type", None) if source is not None else None
    return bool(kind) and kind != "dm"


def spoken_text(event: Any) -> str:
    recall = str(getattr(event, "recall_text", None) or "").strip()
    if recall:
        return recall
    return str(getattr(event, "text", None) or "").strip()


def mentioned(text: str) -> bool:
    return bool(MENTION.search(text or ""))


def group_transcript(
    event: Any,
    *,
    http: Http | None = None,
) -> str:
    client = http or request
    try:
        base, headers = credentials()
    except SystemExit:
        return ""
    source = getattr(event, "source", None)
    chat_uid = str(getattr(source, "chat_id", None) or "").strip() if source else ""
    if not chat_uid.startswith("cht_"):
        return ""
    listed = client(
        "GET",
        f"{base}/v1/chats/{quote(chat_uid)}/messages?limit=12",
        headers=headers,
    )
    if not listed.get("ok"):
        return ""
    return format_transcript(listed.get("body"))


def group_cue(
    event: Any,
    spoken: str,
    *,
    http: Http | None = None,
) -> str:
    if not spoken:
        return "skip"
    name = str(getattr(event, "user_name", None) or "").strip().lower()
    if name in GOAL_NAMES:
        return "allow"
    if spoken.startswith("/"):
        return "allow"
    if mentioned(spoken):
        return "allow"
    lowered = spoken.strip().lower()
    if re.search(r"\b(almo[cç]ar|jantar|kk+|haha+|rsrs+|lol)\b", lowered):
        return "skip"
    if re.fullmatch(r"(oi|olá|opa|hey|hi)\W*", lowered):
        return "skip"
    transcript = group_transcript(event, http=http)
    lines = [line for line in transcript.splitlines() if line.strip()]
    if any(line.startswith("you:") for line in lines[-6:]):
        return "allow"
    return "tie"


def normalize_yes(token: str) -> bool:
    word = token.strip().lower().replace("-", " ").split()[0] if token else ""
    return word in {"yes", "y", "sim"}


def format_transcript(messages: Any, cap: int = 8) -> str:
    rows = message_rows(messages)
    if any(item.get("created_at") or item.get("sent_at") for item in rows):
        rows = sorted(
            rows,
            key=lambda item: str(item.get("created_at") or item.get("sent_at") or ""),
        )
    else:
        rows = list(reversed(rows))
    lines: list[str] = []
    for item in rows[-cap:]:
        body = str(item.get("body") or "").strip()
        if not body:
            continue
        who = "you" if item.get("direction") == "outbound" else "them"
        lines.append(f"{who}: {body}")
    return "\n".join(lines)


def directed_at_zoen(
    event: Any,
    spoken: str,
    *,
    http: Http | None = None,
) -> bool:
    if not spoken:
        return False
    client = http or request
    try:
        base, headers = credentials()
    except SystemExit:
        return False
    source = getattr(event, "source", None)
    chat_uid = str(getattr(source, "chat_id", None) or "").strip() if source else ""
    transcript = ""
    if chat_uid.startswith("cht_"):
        listed = client(
            "GET",
            f"{base}/v1/chats/{quote(chat_uid)}/messages?limit=12",
            headers=headers,
        )
        if listed.get("ok"):
            transcript = format_transcript(listed.get("body"))
    user = f"{transcript}\n\nLatest:\n{spoken}" if transcript else spoken
    try:
        token = complete(
            DIRECTED, user, http=client, base=base, headers=headers, max_tokens=4
        )
    except Exception:
        return False
    if not token:
        return False
    return normalize_yes(token)


def latch_call(
    name: str,
    arguments: dict[str, Any] | None = None,
    timeout: int = 12,
) -> dict | None:
    url = (os.environ.get("PLOW_MCP_URL") or "").strip()
    token = (os.environ.get("PLOW_AGENT_TOKEN") or "").strip()
    if not url or not token:
        return None
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        }
    ).encode()
    req = Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        return None
    if raw.lstrip().startswith("event:") or "\ndata:" in raw or raw.startswith("data:"):
        raw = "\n".join(
            line[5:].strip() for line in raw.splitlines() if line.startswith("data:")
        )
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    result = parsed.get("result") if isinstance(parsed, dict) else None
    if not isinstance(result, dict) or result.get("isError"):
        return None
    payload = result.get("structuredContent")
    if payload is None:
        texts = [
            item.get("text")
            for item in (result.get("content") or [])
            if isinstance(item, dict) and item.get("type") == "text"
        ]
        if not texts:
            return None
        try:
            payload = json.loads(texts[0])
        except json.JSONDecodeError:
            return None
    if not isinstance(payload, dict):
        return None
    if payload.get("status", "completed") != "completed":
        return None
    return payload


def fact_from_output(label: str, output: str) -> str | None:
    value = (output or "").strip().splitlines()
    value = value[0].strip() if value else ""
    if not value or len(value) > 120 or value.lower() in {"none", "null"}:
        return None
    return f"{label}: {value}"


def facts_from_latch() -> list[str]:
    facts: list[str] = []
    for argv, label in PEEK:
        payload = latch_call("plow_run_command", {"argv": argv})
        if not payload or payload.get("exit_code") not in (0, None):
            continue
        fact = fact_from_output(label, str(payload.get("output") or ""))
        if fact:
            facts.append(fact)
    return facts


def peek_owner(
    *,
    home: str | None = None,
    latch: Callable[[], list[str]] | None = None,
    remember_facts: Callable[..., Any] | None = None,
    wait: bool = False,
) -> None:
    def run() -> None:
        try:
            facts = (latch or facts_from_latch)()
            if facts:
                (remember_facts or remember)(facts, home=home)
        except Exception:
            return

    if wait:
        run()
        return
    threading.Thread(target=run, daemon=True, name="zoen-latch-peek").start()


def group_on_dispatch(
    event: Any,
    *,
    http: Http | None = None,
) -> dict[str, str]:
    text = spoken_text(event)
    cue = group_cue(event, text, http=http)
    if cue == "allow":
        return {"action": "allow"}
    if cue == "skip":
        return {"action": "skip", "reason": "group silence"}
    try:
        if directed_at_zoen(event, text, http=http):
            return {"action": "allow"}
    except Exception:
        return {"action": "skip", "reason": "group silence"}
    return {"action": "skip", "reason": "group silence"}


def put_bytes(url: str, headers: dict[str, str], data: bytes, timeout: float = 30) -> dict:
    req = Request(url, data=data, method="PUT", headers=headers)
    try:
        with urlopen(req, timeout=timeout) as resp:
            resp.read()
            return {"ok": True, "status": resp.status, "error": None}
    except HTTPError as exc:
        exc.read()
        return {"ok": False, "status": exc.code, "error": str(exc.reason)}
    except (URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "status": 0, "error": str(exc)}


def load_me(http: Http) -> tuple[str, dict[str, str], dict]:
    base, headers = credentials()
    me = http("GET", f"{base}/v1/agents/me", headers=headers)
    body = me.get("body") if me.get("ok") else None
    if not isinstance(body, dict):
        raise SystemExit(f"face: could not read identity: {me.get('error') or me.get('status')}")
    return base, headers, body


def rename_agent(base: str, me: dict, http: Http) -> dict[str, Any] | None:
    agent = me.get("agent") if isinstance(me.get("agent"), dict) else {}
    uid = str(agent.get("uid") or "")
    token = account_token()
    if not token or not uid:
        return None
    result = http(
        "PATCH",
        f"{base}/v1/agents/{quote(uid, safe='')}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
        body={"name": NAME},
    )
    renamed = {
        "ok": bool(result.get("ok")),
        "status": result.get("status"),
        "error": result.get("error"),
        "name": NAME,
    }
    return renamed


def upload_card(
    base: str,
    headers: dict[str, str],
    chat_uid: str,
    tel: str,
    http: Http,
    put: Put,
    *,
    name: str = NAME,
    filename: str = CARD_NAME,
    photo: bool = True,
) -> dict[str, Any]:
    card = card_bytes(name, tel, filename=filename, photo=photo)
    declared = http(
        "POST",
        f"{base}/v1/chats/{quote(chat_uid)}/attachments",
        headers=headers,
        body={
            "filename": filename,
            "content_type": "text/vcard",
            "size_bytes": len(card),
        },
    )
    upload = declared.get("body") if declared.get("ok") else None
    if not isinstance(upload, dict) or not upload.get("uid") or not upload.get("upload_url"):
        return {
            "ok": False,
            "error": declared.get("error") or "could not declare the card",
            "status": declared.get("status"),
        }
    stored = put(str(upload["upload_url"]), dict(upload.get("upload_headers") or {}), card)
    if not stored.get("ok"):
        return {
            "ok": False,
            "error": stored.get("error") or "card upload failed",
            "status": stored.get("status"),
        }
    return {"ok": True, "uid": upload["uid"], "status": stored.get("status")}


def attach_card(
    base: str,
    headers: dict[str, str],
    chat_uid: str,
    uid: str,
    http: Http,
) -> dict[str, Any]:
    sent = http(
        "POST",
        f"{base}/v1/chats/{quote(chat_uid)}/messages",
        headers=headers,
        body={"body": "", "attachment_uids": [uid]},
    )
    return {
        "ok": bool(sent.get("ok")),
        "status": sent.get("status"),
        "error": sent.get("error"),
        "attachment": uid,
    }


def send_card(
    base: str,
    headers: dict[str, str],
    chat_uid: str,
    tel: str,
    http: Http,
    put: Put,
) -> dict[str, Any]:
    uploaded = upload_card(base, headers, chat_uid, tel, http, put)
    if not uploaded.get("ok"):
        return uploaded
    return attach_card(base, headers, chat_uid, str(uploaded["uid"]), http)


def voice_path(home: str | None = None) -> Path | None:
    root = (home or os.environ.get("HERMES_HOME") or "").strip()
    if not root:
        return None
    return Path(root) / "zoen" / "VOICE.md"


def voice_exists(home: str | None = None) -> bool:
    path = voice_path(home)
    return bool(path and path.is_file() and path.read_text(encoding="utf-8").strip())


def voice_language(home: str | None = None) -> str | None:
    path = voice_path(home)
    if path is None or not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.lower().startswith("language:"):
            token = line.split(":", 1)[1].strip().split()[0].lower()
            if len(token) >= 2 and token[:2].isalpha():
                return token[:2]
    return None


def send_text(
    base: str,
    headers: dict[str, str],
    chat_uid: str,
    body: str,
    http: Http,
) -> dict[str, Any]:
    if any(needle in (body or "").lower() for needle in _RETIRED_HELLO):
        return {"ok": True, "status": 200, "error": None, "skipped": "retired hello"}
    sent = http(
        "POST",
        f"{base}/v1/chats/{quote(chat_uid)}/messages",
        headers=headers,
        body={"body": body, "format": "none"},
    )
    return {
        "ok": bool(sent.get("ok")),
        "status": sent.get("status"),
        "error": sent.get("error"),
    }


def apply(
    force: bool = False,
    chat: str | None = None,
    http: Http = request,
    put: Put = put_bytes,
) -> dict[str, Any]:
    base, headers, me = load_me(http)
    line = me.get("line") if isinstance(me.get("line"), dict) else {}
    tel = str(line.get("provider_key") or "").strip()
    if not tel:
        raise SystemExit("face: line has no number")
    renamed = rename_agent(base, me, http)
    chat_uid = home_chat(me, chat)
    listed = http(
        "GET",
        f"{base}/v1/chats/{quote(chat_uid)}/messages?limit=20",
        headers=headers,
    )
    if listed.get("ok") and already_sent(listed.get("body")) and not force:
        return {
            "ok": True,
            "skipped": "already sent",
            "chat": chat_uid,
            "name": NAME,
            "rename": renamed,
        }
    sent = send_card(base, headers, chat_uid, tel, http, put)
    sent.update({"chat": chat_uid, "name": NAME, "rename": renamed})
    return sent


def _within_budget(deadline: float | None) -> bool:
    return deadline is None or time.monotonic() < deadline


def _budget_http(http: Http, deadline: float | None) -> Http:
    if deadline is None:
        return http

    def call(method: str, url: str, headers: dict[str, str] | None = None, body: Any = None) -> dict:
        if not _within_budget(deadline):
            return {"ok": False, "status": None, "error": "onboarding budget"}
        remaining = max(0.2, deadline - time.monotonic())
        if http is request:
            return request(method, url, headers=headers, body=body, timeout=remaining)
        return http(method, url, headers=headers, body=body)

    return call


def _budget_put(put: Put, deadline: float | None) -> Put:
    if deadline is None:
        return put

    def call(url: str, headers: dict[str, str], data: bytes) -> dict:
        if not _within_budget(deadline):
            return {"ok": False, "status": None, "error": "onboarding budget"}
        remaining = max(0.2, deadline - time.monotonic())
        if put is put_bytes:
            return put_bytes(url, headers, data, timeout=remaining)
        return put(url, headers, data)

    return call


def cards(
    force: bool = False,
    chat: str | None = None,
    http: Http = request,
    put: Put = put_bytes,
    deadline: float | None = None,
) -> dict[str, Any]:
    if deadline is not None and not _within_budget(deadline):
        return {"ok": True, "cards": [], "budget": "spent"}
    http = _budget_http(http, deadline)
    put = _budget_put(put, deadline)
    base, headers, me = load_me(http)
    line = me.get("line") if isinstance(me.get("line"), dict) else {}
    tel = str(line.get("provider_key") or "").strip()
    if not tel:
        raise SystemExit("face: line has no number")
    renamed = rename_agent(base, me, http)
    chat_uid = home_chat(me, chat)
    listed = http(
        "GET",
        f"{base}/v1/chats/{quote(chat_uid)}/messages?limit=20",
        headers=headers,
    )
    history = listed.get("body") if listed.get("ok") else {}
    sent: list[str] = []
    for number, name, filename, photo in (
        (tel, NAME, CARD_NAME, True),
        (ENZO_TEL, ENZO_NAME, ENZO_CARD_NAME, False),
    ):
        if not force and already_sent(history, filename):
            continue
        uploaded = upload_card(
            base, headers, chat_uid, number, http, put,
            name=name, filename=filename, photo=photo,
        )
        if not uploaded.get("ok"):
            uploaded.update({"chat": chat_uid, "name": NAME, "cards": sent, "rename": renamed})
            return uploaded
        posted = attach_card(base, headers, chat_uid, str(uploaded["uid"]), http)
        if not posted.get("ok"):
            posted.update({"chat": chat_uid, "name": NAME, "cards": sent, "rename": renamed})
            return posted
        sent.append(filename)
    return {
        "ok": True,
        "chat": chat_uid,
        "name": NAME,
        "cards": sent,
        "rename": renamed,
    }


def intro(
    force: bool = False,
    chat: str | None = None,
    inbound: str | None = None,
    http: Http = request,
    put: Put = put_bytes,
) -> dict[str, Any]:
    del force, chat, inbound, http, put
    return {"ok": True, "skipped": "retired hello", "hello": []}


def is_setup_text(text: str) -> bool:
    return (text or "").strip().lower().startswith(SETUP_PREFIX)


def is_plow_setup(event: Any) -> bool:
    spoken = spoken_text(event)
    if is_setup_text(spoken):
        return True
    if spoken:
        return False
    name = str(getattr(event, "user_name", None) or "").strip().lower()
    text = str(getattr(event, "text", None) or "")
    if is_setup_text(text):
        return True
    return name in SETUP_NAMES or name.startswith("plow setup")


def _call_intro(
    send: Callable[..., dict[str, Any]] | None,
    http: Http | None,
    put: Put | None,
    inbound: str | None = None,
) -> dict[str, Any]:
    if send is not None:
        return send(**({} if inbound is None else {"inbound": inbound}))
    kwargs: dict[str, Any] = {}
    if inbound is not None:
        kwargs["inbound"] = inbound
    if http is not None:
        kwargs["http"] = http
    if put is not None:
        kwargs["put"] = put
    return intro(**kwargs)


def chat_history(event: Any, http: Http | None = None) -> Any:
    for attr in ("messages", "history"):
        rows = getattr(event, attr, None)
        if rows:
            return rows
    client = http or request
    try:
        base, headers = credentials()
    except SystemExit:
        return None
    source = getattr(event, "source", None)
    chat_uid = str(getattr(source, "chat_id", None) or "").strip() if source else ""
    if not chat_uid.startswith("cht_"):
        try:
            _base, _headers, me = load_me(client)
            chat_uid = home_chat(me)
        except (SystemExit, KeyError, TypeError, ValueError):
            return None
    if not chat_uid.startswith("cht_"):
        return None
    listed = client(
        "GET",
        f"{base}/v1/chats/{quote(chat_uid)}/messages?limit=20",
        headers=headers,
    )
    return listed.get("body") if listed.get("ok") else None


def already_introduced(event: Any, http: Http | None = None) -> bool:
    try:
        history = chat_history(event, http)
    except (SystemExit, OSError, TypeError, ValueError, KeyError):
        return False
    return bool(history) and hello_sent(history)


def greet_on_dispatch(
    event: Any = None,
    *,
    voiced: bool | None = None,
    send: Callable[..., dict[str, Any]] | None = None,
    http: Http | None = None,
    put: Put | None = None,
    **_: Any,
) -> dict[str, str]:
    if getattr(event, "internal", False):
        return {"action": "allow"}
    if is_plow_setup(event):
        # The native setup hook is synchronous and can race the real inbound
        # handoff. Only that handoff owns the intro, off the receive loop.
        return {"action": "skip", "reason": "plow setup"}
    if is_group(event):
        return group_on_dispatch(event, http=http)
    if getattr(event, "zoen_whatsapp", None):
        opening = str(getattr(event, "message_id", "") or "")
        quote = (
            f"The opening bubble wamid is {opening}. "
            "Set text reply_to to that wamid when the answer belongs to this bubble.\n"
            if opening.startswith("wamid.")
            else ""
        )
        event.channel_prompt = (getattr(event, "channel_prompt", "") or "") + (
            "\n<whatsapp>\n"
            "This message arrived on WhatsApp. One zoen_imessage call sends it. "
            "The eye is already on this bubble and typing is already on. "
            "Do not send a reaction. Send the reply as text. "
            "Items: text with reply_to set to the wamid, image, video, audio, contact. "
            + quote
            + "zoen_connections connect posts the authorization link in this chat. Do not paste that URL yourself. "
            "This thread stays free. Long work is one delegate_task spawn, then this turn ends. "
            "A status question or progress check is one short bubble here. Do not take over the child's tools. "
            "The sandbox shell is root. It does the work. It does not text this chat. "
            "After zoen_imessage succeeds, the final reply is [NO_REPLY].\n"
            "</whatsapp>\n"
        )
    if getattr(event, "zoen_pairing_code", False):
        language = resolve_language(event, http)
        event.channel_prompt = (
            (getattr(event, "channel_prompt", "") or "")
            + pairing_intro_prompt(language)
        )
        return {"action": "allow", "reason": "zoen onboarding"}
    live = voice_exists() if voiced is None else voiced
    if not live and already_introduced(event, http):
        return {"action": "allow"}
    if live:
        return {"action": "allow"}
    text = spoken_text(event) or str(getattr(event, "text", None) or "").strip()
    if not text or text.startswith("/"):
        return {"action": "allow"}
    if not greeting_due(event, http):
        return {"action": "skip", "reason": "prebuilt hello"}
    whatsapp = bool(getattr(event, "zoen_whatsapp", None))
    language = resolve_language(event, http) if whatsapp else ""
    note = first_contact_prompt(
        whatsapp=whatsapp, offer_whatsapp=not whatsapp, language=language,
    )
    event.channel_prompt = (getattr(event, "channel_prompt", "") or "") + note
    return {"action": "allow", "reason": "zoen onboarding"}


def rename(
    http: Http = request,
) -> dict[str, Any]:
    base, _headers, me = load_me(http)
    renamed = rename_agent(base, me, http)
    if renamed is None:
        return {"ok": False, "error": "no account token", "name": NAME}
    if not renamed.get("ok"):
        return {
            "ok": False,
            "error": renamed.get("error") or "rename failed",
            "name": NAME,
            "rename": renamed,
        }
    return {"ok": True, "name": NAME, "rename": renamed}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        nargs="?",
        default="cards",
        choices=("intro", "cards", "rename", "card", "bake"),
        help="cards are the vCards, intro is the retired scripted hello, rename is install",
    )
    parser.add_argument("--force", action="store_true", help="send even if one already went")
    parser.add_argument("--chat", help="cht_... (default home DM)")
    parser.add_argument("--dest", help="directory for bake (default /usr/share/doc/zoen)")
    return parser


def main(
    argv: list[str] | None = None,
    http: Http = request,
    put: Put = put_bytes,
) -> int:
    args = build_parser().parse_args(argv)
    if args.mode == "bake":
        return _out(bake_cards(args.dest))
    if args.mode == "rename":
        return _out(rename(http=http))
    if args.mode == "card":
        return _out(apply(force=args.force, chat=args.chat, http=http, put=put))
    if args.mode == "cards":
        return _out(cards(force=args.force, chat=args.chat, http=http, put=put))
    return _out(intro(force=args.force, chat=args.chat, http=http, put=put))


if __name__ == "__main__":
    raise SystemExit(main())
